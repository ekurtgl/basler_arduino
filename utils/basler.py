import os
import cv2
import time
import json
import pickle
import traceback
import numpy as np
# import matplotlib.pyplot as plt
from datetime import datetime
import pypylon
import pprint
from pypylon import pylon, genicam
from threading import Thread
from queue import LifoQueue
from concurrent.futures import ThreadPoolExecutor
from .helpers import str_to_bool
from .preview import VideoShow
from tqdm import tqdm

tp = ThreadPoolExecutor(100)  # max 10 threads

def threaded(fn):
    def wrapper(*args, **kwargs):
        return tp.submit(fn, *args, **kwargs)  # returns Future object
    return wrapper


class Basler():

    def __init__(self, args, cam, experiment, config, start_t, cam_id=0, max_cams=2, connect_retries=20) -> None:
        print('Searching for camera...')

        self.start_t = start_t
        self.args = args
        self.cam = cam
        self.experiment = experiment
        self.config = config
        self.cam_id = cam_id
        self.preview = str_to_bool(self.args.preview)
        self.save = str_to_bool(self.args.save)
        cameras = None
        # get transport layer factory
        self.tlFactory = pylon.TlFactory.GetInstance()
        # get the camera list 
        self.devices = self.tlFactory.EnumerateDevices()
        self.vid_cod = cv2.VideoWriter_fourcc('m', 'p', '4', 'v')
        
        print('Connecting to the camera...')   

        n = 0
        while cameras is None and n < connect_retries:
            try:
                cameras = pylon.InstantCameraArray(min(len(self.devices), max_cams))
                self.camera = cameras[cam_id]
                self.camera = pylon.InstantCamera(self.tlFactory.CreateDevice(self.devices[self.cam_id]))
                # self.camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())
                # print(dir(self.camera))
                # self.camera.MaxNumBuffer.Value = 20
                print(f"Num. of cameras detected: {cameras.GetSize()}, selected cam_ID: {cam_id}")
                self.init_camera()

            except Exception as e:
                print(f'Trying to detect camera, trial {n}/{connect_retries}...')
                time.sleep(0.1)
                cameras = None
                n += 1

    def init_camera(self):
        
        # self.camera.Attach(self.tlFactory.CreateDevice(self.devices[self.cam_id]))
        
        self.camera.Open()
        self.compute_timestamp_offset()
        # new_width = self.camera.Width.Value - self.camera.Width.Inc
        # if new_width >= self.camera.Width.Min:
        #     self.camera.Width.Value = new_width
        self.camera.MaxNumBuffer.Value = 100
        self.name = self.camera.GetDeviceInfo().GetModelName()
        print(f"Cam {self.cam_id}, name: {self.name}, serial: {self.camera.DeviceInfo.GetSerialNumber()}")
        # self.camera.SetCameraContext(self.cam_id)
        print(f"Camera {self.cam_id} [{self.name}] successfully initialized!")
        self.nodemap = self.camera.GetNodeMap()
        self.strobe = self.cam['strobe']
        pylon.FeaturePersistence.Save(os.path.join(self.config['savedir'], self.experiment, "nodemap.txt"), self.nodemap)
        self.update_settings()
        # pylon.FeaturePersistence.Load("config/acA2040-120um_24516213.pfs", self.nodemap, True)
        
        self.converter = pylon.ImageFormatConverter()
        self.converter.OutputPixelFormat = pylon.PixelType_BGR8packed # converting to opencv bgr format
        self.converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

        if self.preview:
            # self.initialize_preview()
            self.vid_show = VideoShow()
        
        if self.save:
            self.init_video_writer()

    def init_video_writer(self):
        self.writer_obj = cv2.VideoWriter(os.path.join(self.config['savedir'], self.experiment, "video.mp4"), self.vid_cod, self.args.videowrite_fps,
                                    (self.cam['options']['Width'], self.cam['options']['Height']))
    
    def convert_image(self, grabResult):
        return self.converter.Convert(grabResult).GetArray()
    
    def update_settings(self):
        """ Updates Basler camera settings.
        Attributes, types, and range of possible values for each attribute are available
        in the camera documentation. 
        These are extraordinarily tricky! Order matters! For exampple, ExposureAuto must be set
        to Off before ExposureTime can be set. 
        """
        print("-updating settings-")

        if self.args.nodemap_path is not None:
            print("Loading saved configs to camera")
            pylon.FeaturePersistence.Load(self.args.nodemap_path, self.nodemap, True)
        else:
            for key, value in self.cam['options'].items():
                #print(key, value)
                self.set_value(self.nodemap, key, value)
            # changing strobe involves multiple variables in the correct order, so I've bundled
            # them into this function
            if str_to_bool(self.args.trigger_with_arduino):
                self.turn_strobe_on(self.nodemap, self.strobe['line'], 
                                trigger_selector=self.strobe['trigger_selector'], 
                                line_output=self.strobe['line_output'], 
                                line_source=self.strobe['line_source']) 

    @staticmethod
    def set_value(nodemap, nodename, value):
        try:
            node = nodemap.GetNode(nodename)
            nodeval, typestring = (node, type(node))

            if typestring in [pypylon.genicam.IFloat, pypylon.genicam.IInteger]:
                assert(value <= nodeval.GetMax() and value >= nodeval.GetMin())
                if typestring == pypylon.genicam.IInteger:
                    assert(type(value)==int)
                    if pypylon.genicam.IsAvailable(nodeval) and pypylon.genicam.IsWritable(nodeval):
                        nodeval.SetValue(value)
                    else:
                        raise ValueError('Node not writable or available: %s' %nodename)
                elif typestring == pypylon.genicam.IFloat:
                    assert(type(value) in [float, int])
                    if pypylon.genicam.IsAvailable(nodeval) and pypylon.genicam.IsWritable(nodeval):
                        nodeval.SetValue(float(value))
                    else:
                        raise ValueError('Node not writable or available: %s' %nodename)
            elif typestring == pypylon.genicam.IEnumeration:
                assert(type(value)==str)
                entry = nodeval.GetEntryByName(value)
                if entry is None:
                    print('Valid entries: ')
                    entrylist = nodeval.GetEntries()
                    for entry in entrylist:
                        print(entry)
                        #print(entry.GetName())
                    raise ValueError('Invalid entry!: %s' %value)
                    #else:
                    #entry = PySpin.CEnumEntryPtr(entry)
                if pypylon.genicam.IsAvailable(entry) and pypylon.genicam.IsReadable(entry):
                    nodeval.SetIntValue(entry.GetValue())
                else:
                    raise ValueError('Entry not readable!')
            elif typestring == pypylon.genicam.IBoolean:
                assert(type(value)==bool)
                if pypylon.genicam.IsAvailable(nodeval) and pypylon.genicam.IsWritable(nodeval):
                    nodeval.SetValue(value)
                else:
                    raise ValueError('Node not writable or available: %s' %nodename)

        except Exception as e:# PySpin.SpinnakerException as e:
            print("ERROR setting:", nodename, value)
            traceback.print_exc()
            raise ValueError('Error: %s' %e)
    
    def turn_strobe_on(self, nodemap, line, trigger_selector='FrameStart', line_output=None, line_source='ExposureActive'): # strobe_duration=0.0):
        '''
        # is using external hardware trigger, select line_output to record actual on times (LineSource = 'ExposureActive')
        # check camera model for which lines can be out/in

        # Set  trigger
        # get clean powerup state -- now in self.cleanup_powerup_state()
        cam.TriggerSelector = "FrameStart"
        cam.TriggerMode = "On"
        cam.TriggerDelay.SetValue(0)
        cam.TriggerActivation = 'RisingEdge' 
        #cam.AcquisitionMode.SetValue('SingleFrame')
        cam.AcquisitionMode.SetValue('Continuous')
        #cam.AcquisitionStatusSelector="FrameTriggerWait"

        # Set IO lines:
        cam.TriggerSource.SetValue("Line4")
        cam.LineSelector.SetValue("Line4") #acquisition_line) # select GPIO 1
        cam.LineMode.SetValue('Input')     # Set as input
        '''

        assert(type(line)==int)
        #assert(type(strobe_duration)==float)
        
        self.set_value(nodemap, 'TriggerSelector', trigger_selector)
        self.set_value(nodemap, 'TriggerMode', 'On')
        self.set_value(nodemap, 'TriggerSource', 'Line3')

        self.set_value(nodemap, 'TriggerDelay', 0)
        self.set_value(nodemap, 'TriggerActivation', 'RisingEdge')
        #set_value(nodemap, 'AcquisitionMode', 'Continuous') # must be continuous for external frame trigger
        self.set_value(nodemap, 'AcquisitionStatusSelector', 'FrameTriggerWait')
        self.set_value(nodemap, 'AcquisitionBurstFrameCount', 1)

        # Set trigger source 
        linestr = 'Line%d'%line
        # set the line selector to this line so that we change the following
        # values for Line2, for example, not Line0
        self.set_value(nodemap, 'LineSelector', linestr)
        # one of input, trigger, strobe, output
        self.set_value(nodemap, 'LineMode', 'Input') #'strobe')

        # set output
        if line_output is not None:
            linestr_out = 'Line%d' % line_output
            self.set_value(nodemap, 'LineSelector', linestr_out)
            self.set_value(nodemap, 'LineMode', 'Output')
            self.set_value(nodemap, 'LineSource', line_source)
            self.set_value(nodemap, 'LineInverter', True)

    def initialize_preview(self):
        # plt.ion()
        self.latest_frame = np.zeros((self.cam['options']['Height'], self.cam['options']['Width']), dtype=np.uint8)
        # ax1 = plt.subplot(1,1,1)
        # self.fig = ax1.imshow(empty_image)
        cv2.namedWindow(self.name, cv2.WINDOW_NORMAL)
        # self.font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.imshow(self.name, self.latest_frame)
        self.preview_queue = LifoQueue(maxsize=10)
        self.preview_thread()   
    
    def preview_worker(self):
        while self.preview:
            print('here ')
            cv2.imshow(self.name, self.latest_frame)
            cv2.putText(self.latest_frame, "{}. Fra,e".format(self.n),
                (10, 450), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255))
            
    def update_preview(self):
        # frame = np.expand_dims(self.frames[-1], -1)
        # self.fig.set_data(frame)
        # plt.pause(0.1)
        # string = '%s:%07d' %(self.camera.GetDeviceInfo().GetModelName(), count)
        # cv2.putText(frame, string,(10,out_height-20), self.font, 0.5,(0,0,255),2,cv2.LINE_AA)
        cv2.imshow(self.name, self.latest_frame)
        k = cv2.waitKey(1)
        return k
    
    def compute_timestamp_offset(self):
        self.camera.TimestampLatch.Execute()
        self.timestamp_offset = time.perf_counter() - self.camera.TimestampLatchValue.GetValue()*1e-9 - self.start_t

    @threaded  # threaded should be disabled when preview is set
    def get_n_frames(self, n_frames, save_vid=True, timeout=5000):
        
        # if save_vid:
        #     directory = os.path.join(self.config['savedir'], self.experiment, 'metadata')
        #     if not os.path.isdir(directory):
        #         os.makedirs(directory)
        # Start the grabbing of n_frames images.
        # The camera device is parameterized with a default configuration which
        # sets up free-running continuous acquisition.
        self.camera.StartGrabbingMax(n_frames)
        # Grabing Continusely (video) with minimal delay
        # self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
        
        # Camera.StopGrabbing() is called automatically by the RetrieveResult() method
        # when n_frames images have been retrieved.
        # self.frames = []
        self.n = 0
        metadata = {}
        start_time = time.perf_counter()

        while self.camera.IsGrabbing():
            # Wait for an image and then retrieve it. A timeout of 5000 ms is used.
            grabResult = self.camera.RetrieveResult(timeout, pylon.TimeoutHandling_ThrowException)
            
            # Image grabbed successfully?
            if grabResult.GrabSucceeded():
                metadata[grabResult.ID] = {}
                # image = self.converter.Convert(grabResult).GetArray()
                self.latest_frame = self.convert_image(grabResult)
                # Access the image data.
                metadata[grabResult.ID]['time_stamp'] = datetime.now().strftime("%Y%m%d_%H_%M_%S.%f")  # microsec precision
                # self.frames.append(image)
                # if self.preview and grabResult.ImageNumber % 10 == 0:
                #     self.preview_queue.put_nowait(self.latest_frame)
                    # self.vid_show.frame = self.latest_frame
                    # k = self.update_preview()
                    # if k == 27:  # ASCII value for “ESC”
                    #     break
                # print(f'Frame: {n}, time stamp: {metadata["time_stamp"]}')
                if self.n % 30 == 0:
                    print(f'Frame: {self.n} / {n_frames}')
                # print("Gray value of first pixel: ", frames[-1][0, 0])
                # print(f'frame: {grabResult.Array.dtype}, shape: {grabResult.Array.shape}')
                # metadata[grabResult.ID]['width'] = grabResult.Width
                # metadata[grabResult.ID]['height'] = grabResult.Height
                metadata[grabResult.ID]['fps'] = self.camera.ResultingFrameRate.Value
                # metadata[grabResult.ID]['frame_ID'] = grabResult.ID
                metadata[grabResult.ID]['frame_number'] = grabResult.ImageNumber
                metadata[grabResult.ID]['time_stamp_w_offset'] = grabResult.GetTimeStamp()*1e-9 + self.timestamp_offset
                metadata[grabResult.ID]['pylon_time_stamp'] = grabResult.TimeStamp
                last_time_stamp = grabResult.TimeStamp
                if self.n == 0:
                    init_time_stamp = grabResult.TimeStamp
                # pprint.pprint(metadata)
                if save_vid:
                    # self.save_frame(image, writer_obj)
                    self.writer_obj.write(self.latest_frame)
                    # with open(os.path.join(self.config['savedir'], 'metadata', f'frame_{str(metadata["frame_number"]).zfill(6)}.json'), 'w') as file:
                    #     json.dump(metadata, file)

            else:
                print(f"Error: {grabResult.ErrorCode} --> {grabResult.ErrorDescription}")
            grabResult.Release()
            self.n += 1

        print(f'Elapsed time (time.perf_counter()) for processing {n_frames} frames at {self.cam["options"]["AcquisitionFrameRate"]} FPS: {time.perf_counter() - start_time} sec.')
        print(f'Time difference (grabResult.TimeStamp) between the first and the last frame timestamp: {(last_time_stamp - init_time_stamp) * 1e-9} sec.')

        if self.preview:
            cv2.destroyAllWindows()

        if save_vid:                 
            with open(os.path.join(self.config['savedir'], self.experiment, f'metadata.json'), 'w') as file:
                json.dump(metadata, file)
            # with open(os.path.join(self.config['savedir'], self.experiment, f'metadata.pickle'), 'wb') as file:
            #     pickle.dump(metadata, file, pickle.HIGHEST_PROTOCOL)
            # self.export_video()
            self.writer_obj.release()
        
        # return self.frames
    
    def initialize_preview2(self):
        # cv2.namedWindow(self.name, cv2.WINDOW_NORMAL)
        print("New window: %s" % self.name)
        cv2.namedWindow(self.name, cv2.WINDOW_NORMAL) #AUTOSIZE)
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.latest_frame = None
        self.preview_queue = LifoQueue(maxsize=5) #, block=False)
        #self.preview_thread = mp.Process(target=self.preview_worker, args=(self.preview_queue,))
        self.preview_thread = Thread(target=self.preview_worker, args=(self.preview_queue,))
        self.preview_thread.daemon = True
        self.preview_thread.start()

    def preview_worker(self, queue):
        should_continue = True
        while should_continue:
            item = queue.get()
            # print(item)
            if item is None:
                if self.verbose:
                    print('Preview stop signal received')
                should_continue=False
                break
                # break
            # left, right, count = item
            frame, count = item
            # frame should be processed, so a single RGB image
            # out = np.vstack((left,right))
            # h, w, c = frame.shape
            h, w = frame.shape
#            if self.save:
#                frame = cv2.resize(frame, (w//2,h//2),cv2.INTER_NEAREST)
#                out_height = h//2
#            else:
#                frame = cv2.resize(frame, (w,h),cv2.INTER_NEAREST)
#                out_height = h//3*2
#            # frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
            out_height=h                    
            # string = '%.4f' %(time_acq*1000)
            string = '%s:%07d' %(self.name, count)
            cv2.putText(frame, string, (10,out_height-20), self.font, 0.5,(0,0,255), 2, cv2.LINE_AA)
            self.latest_frame = frame
            queue.task_done()

    def start(self):
        self.camera.StartGrabbing(pylon.GrabStrategy_OneByOne)
        print(f"Started cam {self.name} acquisition")
        if self.preview:
            self.initialize_preview()
        self.started= True
        self.start_timer = time.perf_counter()

    # @threaded
    # def save_frame(self, frame, writer_obj, metadata=None):
    #     writer_obj.write(frame)
    #     # with open(os.path.join(self.config['savedir'], 'metadata', f'frame_{str(metadata["frame_number"]).zfill(6)}.json'), 'w') as file:
    #     #     json.dump(metadata, file)

    # def export_video(self):
    #     directory = os.path.join(self.config['savedir'], self.experiment)
    #     writer_obj = cv2.VideoWriter(os.path.join(directory, "video.mp4"), self.vid_cod, self.args.videowrite_fps,
    #                                  (self.cam['options']['Width'], self.cam['options']['Height']))
        
    #     for frame in tqdm(self.frames, desc='Exporting Video'):
    #         writer_obj.write(frame)
        
    #     writer_obj.release()
        
    def close(self):
        self.camera.Close()

    

    