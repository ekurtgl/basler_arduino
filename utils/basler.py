import os
import cv2
import time
import json
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import pypylon
import pprint
from pypylon import pylon, genicam
from threading import Thread
from queue import LifoQueue
from concurrent.futures import ThreadPoolExecutor
from .helpers import str_to_bool
from tqdm import tqdm

tp = ThreadPoolExecutor(10)  # max 10 threads

def threaded(fn):
    def wrapper(*args, **kwargs):
        return tp.submit(fn, *args, **kwargs)  # returns Future object
    return wrapper


class Basler():

    def __init__(self, args, cam, experiment, config, cam_id=0, max_cams=2, connect_retries=20) -> None:
        print('Searching for camera...')

        self.args = args
        self.cam = cam
        self.experiment = experiment
        self.config = config
        self.cam_id = cam_id
        self.preview = str_to_bool(self.args.preview)
        cameras = None
        # get transport layer factory
        self.tlFactory = pylon.TlFactory.GetInstance()
        # get the camera list 
        self.devices = self.tlFactory.EnumerateDevices()
        self.vid_cod = cv2.VideoWriter_fourcc('m', 'p', '4', 'v')
        
        print('Connecting to the camera...')   

        n = 0
        while cameras is None and n < connect_retries:
            # try:
            cameras = pylon.InstantCameraArray(min(len(self.devices), max_cams))
            self.camera = cameras[cam_id]
            self.camera = pylon.InstantCamera(self.tlFactory.CreateDevice(self.devices[self.cam_id]))
            # self.camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())
            # print(dir(self.camera))
            # self.camera.MaxNumBuffer.Value = 20
            print(f"Num. of cameras detected: {cameras.GetSize()}, selected cam_ID: {cam_id}")
            self.init_camera()

            # except Exception as e:
            #     print('.')
            #     time.sleep(0.1)
            #     cameras = None
            #     n += 1

    def init_camera(self):
        
        # self.camera.Attach(self.tlFactory.CreateDevice(self.devices[self.cam_id]))
        
        self.camera.Open()
        # new_width = self.camera.Width.Value - self.camera.Width.Inc
        # if new_width >= self.camera.Width.Min:
        #     self.camera.Width.Value = new_width
        self.camera.MaxNumBuffer.Value = 100
        self.name = self.camera.GetDeviceInfo().GetModelName()
        print(f"Cam {self.cam_id}, name: {self.name}, serial: {self.camera.DeviceInfo.GetSerialNumber()}")
        # self.camera.SetCameraContext(self.cam_id)
        print(f"Camera {self.cam_id} [{self.name}] successfully initialized!")

        if self.preview:
            self.initialize_preview()

    def initialize_preview(self):
        plt.ion()
        empty_image = np.zeros((self.cam['options']['Height'], self.cam['options']['Width'], 1), dtype=np.uint8)
        ax1 = plt.subplot(1,1,1)
        self.fig = ax1.imshow(empty_image)
        # cv2.namedWindow(self.camera.GetDeviceInfo().GetModelName(), cv2.WINDOW_NORMAL)
        # self.font = cv2.FONT_HERSHEY_SIMPLEX
        # cv2.imshow(self.camera.GetDeviceInfo().GetModelName(), empty_image)
        # cv2.waitKey(0)
    
    # @threaded
    def update_preview(self):
        frame = np.expand_dims(self.frames[-1], -1)
        self.fig.set_data(frame)
        plt.pause(0.1)
        # string = '%s:%07d' %(self.camera.GetDeviceInfo().GetModelName(), count)
        # cv2.putText(frame, string,(10,out_height-20), self.font, 0.5,(0,0,255),2,cv2.LINE_AA)
        # cv2.imshow(self.camera.GetDeviceInfo().GetModelName(), frame)

    # def initialize_preview(self):
    #     # cv2.namedWindow(self.name, cv2.WINDOW_NORMAL)
    #     print("New window: %s" % self.name)
    #     cv2.namedWindow(self.name, cv2.WINDOW_NORMAL) #AUTOSIZE)
    #     self.font = cv2.FONT_HERSHEY_SIMPLEX
    #     self.latest_frame = None
    #     self.preview_queue = LifoQueue(maxsize=5) #, block=False)
    #     #self.preview_thread = mp.Process(target=self.preview_worker, args=(self.preview_queue,))
    #     self.preview_thread = Thread(target=self.preview_worker, args=(self.preview_queue,))
    #     self.preview_thread.daemon = True
    #     self.preview_thread.start()
    
#     def preview_worker(self, queue):
#         should_continue = True
#         while should_continue:
#             item = queue.get()
#             # print(item)
#             if item is None:
#                 if self.verbose:
#                     print('Preview stop signal received')
#                 should_continue=False
#                 break
#                 # break
#             # left, right, count = item
#             frame, count = item
#             # frame should be processed, so a single RGB image
#             # out = np.vstack((left,right))
#             print(f'frame: {frame.shape}')
#             # h, w, c = frame.shape
#             h, w = frame.shape
# #            if self.save:
# #                frame = cv2.resize(frame, (w//2,h//2),cv2.INTER_NEAREST)
# #                out_height = h//2
# #            else:
# #                frame = cv2.resize(frame, (w,h),cv2.INTER_NEAREST)
# #                out_height = h//3*2
# #            # frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
#             out_height=h                    
#             # string = '%.4f' %(time_acq*1000)
#             string = '%s:%07d' %(self.name, count)
#             cv2.putText(frame,string,(10,out_height-20), self.font, 0.5,(0,0,255),2,cv2.LINE_AA)
#             self.latest_frame = frame
#             queue.task_done()

    # @threaded
    def get_n_frames(self, n_frames, timeout=5000):
        is_save = str_to_bool(self.args.save)
        if is_save:
            directory = os.path.join(self.config['savedir'], self.experiment, 'metadata')
            if not os.path.isdir(directory):
                os.makedirs(directory)
        # Start the grabbing of n_frames images.
        # The camera device is parameterized with a default configuration which
        # sets up free-running continuous acquisition.
        self.camera.StartGrabbingMax(n_frames)
        start_time = time.time()
        # Camera.StopGrabbing() is called automatically by the RetrieveResult() method
        # when n_frames images have been retrieved.
        self.frames = []
        n = 0
        while self.camera.IsGrabbing():
            # Wait for an image and then retrieve it. A timeout of 5000 ms is used.
            grabResult = self.camera.RetrieveResult(timeout, pylon.TimeoutHandling_ThrowException)
            metadata = {}
            # Image grabbed successfully?
            if grabResult.GrabSucceeded():
                # Access the image data.
                metadata['time_stamp'] = datetime.now().strftime("%Y%m%d_%H_%M_%S.%f")  # microsec precision
                self.frames.append(grabResult.Array)
                if self.preview and grabResult.ImageNumber % 10 == 0:
                    self.update_preview()
                    # self.preview_queue.put_nowait((grabResult.Array, grabResult.ImageNumber))
                    # #self.preview_worker((frame, framecount))
                    # if grabResult.Array is not None:
                    #     cv2.imshow(self.name, grabResult.Array)
                print(f'Frame: {n}, time stamp: {metadata["time_stamp"]}')
                # print("Gray value of first pixel: ", frames[-1][0, 0])
                # print(f'frame: {grabResult.Array.dtype}, shape: {grabResult.Array.shape}')
                metadata['width'] = grabResult.Width
                metadata['height'] = grabResult.Height
                metadata['fps'] = self.camera.ResultingFrameRate.Value
                metadata['frame_number'] = grabResult.ImageNumber
                metadata['offset_x'] = grabResult.OffsetX
                metadata['offset_y'] = grabResult.OffsetY
                metadata['pylon_time_stamp'] = grabResult.TimeStamp
                if is_save:
                    directory = os.path.join(self.config['savedir'], self.experiment, 'metadata')
                    
                    with open(os.path.join(directory, f'frame_{str(metadata["frame_number"]).zfill(6)}.json'), 'w') as file:
                        json.dump(metadata, file)

                # pprint.pprint(metadata)
            else:
                print(f"Error: {grabResult.ErrorCode} --> {grabResult.ErrorDescription}")
            grabResult.Release()
            n += 1
        print(f'Elapsed time for {n_frames} frames: {time.time() - start_time} sec.')

        if self.preview:
            cv2.destroyAllWindows()
            plt.ioff()

        if is_save:
            self.export_video()
    
    def export_video(self):
        directory = os.path.join(self.config['savedir'], self.experiment)
        writer_obj = cv2.VideoWriter(os.path.join(directory, "video.mp4"), self.vid_cod, self.args.videowrite_fps,
                                     (self.cam['options']['Width'], self.cam['options']['Height']))

        for frame in tqdm(self.frames, desc='Exporting Video'):
            writer_obj.write(frame)
        
        writer_obj.release()
        
    def close(self):
        self.camera.Close()

    

    