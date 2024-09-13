import os
import cv2
import time
import json
from datetime import datetime
import pypylon
import pprint
from pypylon import pylon, genicam
from concurrent.futures import ThreadPoolExecutor


tp = ThreadPoolExecutor(10)  # max 10 threads

def threaded(fn):
    def wrapper(*args, **kwargs):
        return tp.submit(fn, *args, **kwargs)  # returns Future object
    return wrapper


class Basler():

    def __init__(self, args, cam, cam_id=0, max_cams=2, connect_retries=20) -> None:
        print('Searching for camera...')

        self.args = args
        self.cam = cam
        self.cam_id = cam_id
        cameras = None
        # get transport layer factory
        self.tlFactory = pylon.TlFactory.GetInstance()
        # get the camera list 
        self.devices = self.tlFactory.EnumerateDevices()
        
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
                print('.')
                time.sleep(0.1)
                cameras = None
                n += 1

    def init_camera(self):
        
        # self.camera.Attach(self.tlFactory.CreateDevice(self.devices[self.cam_id]))
        
        self.camera.Open()
        # new_width = self.camera.Width.Value - self.camera.Width.Inc
        # if new_width >= self.camera.Width.Min:
        #     self.camera.Width.Value = new_width
        self.camera.MaxNumBuffer.Value = 20
        print(f"Cam {self.cam_id}, name: {self.camera.GetDeviceInfo().GetModelName()}, serial: {self.camera.DeviceInfo.GetSerialNumber()}")
        # self.camera.SetCameraContext(self.cam_id)
        print(f"Camera {self.cam_id} [{self.camera.GetDeviceInfo().GetModelName()}] successfully initialized!")
    
    @threaded
    def get_n_frames(self, n_frames, timeout=5000,
                     is_save_frames=False, is_save_metadata=False):
        
        # Start the grabbing of n_frames images.
        # The camera device is parameterized with a default configuration which
        # sets up free-running continuous acquisition.
        self.camera.StartGrabbingMax(n_frames)
        start_time = time.time()
        # Camera.StopGrabbing() is called automatically by the RetrieveResult() method
        # when n_frames images have been retrieved.
        frames = []
        metadata = {}
        n = 0
        while self.camera.IsGrabbing():
            # Wait for an image and then retrieve it. A timeout of 5000 ms is used.
            grabResult = self.camera.RetrieveResult(timeout, pylon.TimeoutHandling_ThrowException)
            # Image grabbed successfully?
            if grabResult.GrabSucceeded():
                # Access the image data.
                metadata['time_stamp'] = datetime.now().strftime("%Y%m%d_%H_%M_%S.%f")  # microsec precision
                frames.append(grabResult.Array)
                # print(f'Frame: {n}, time stamp: {metadata["time_stamp"]}')
                # print("Gray value of first pixel: ", frames[-1][0, 0])
                metadata['width'] = grabResult.Width
                metadata['height'] = grabResult.Height
                metadata['fps'] = self.camera.ResultingFrameRate.Value
                metadata['frame_number'] = grabResult.ImageNumber
                metadata['offset_x'] = grabResult.OffsetX
                metadata['offset_y'] = grabResult.OffsetY
                metadata['pylon_time_stamp'] = grabResult.TimeStamp
                # pprint.pprint(metadata)
            else:
                print(f"Error: {grabResult.ErrorCode} --> {grabResult.ErrorDescription}")
            grabResult.Release()
            n += 1
        print(f'Elapsed time for {n_frames} frames: {time.time() - start_time} sec.')
        return frames
    
    def close(self):
        self.camera.Close()

    

    