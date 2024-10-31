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
from pypylon import pylon
from queue import Queue
from concurrent.futures import ThreadPoolExecutor
from utils.helpers import str_to_bool
from utils.preview import VideoShow
from utils.prediction import Predictor

tp = ThreadPoolExecutor(100)  # max 10 threads

def threaded(fn):
    def wrapper(*args, **kwargs):
        return tp.submit(fn, *args, **kwargs)  # returns Future object
    return wrapper

class Basler():

    def __init__(self, args, cam, experiment, config, start_t, logger, cam_id=0, max_cams=2, connect_retries=20) -> None:

        self.start_t = start_t
        self.args = args
        self.cam = cam
        self.experiment = experiment
        self.config = config
        self.cam_id = cam_id
        self.frame_timer = None
        self.preview = str_to_bool(self.args.preview)
        self.save = str_to_bool(self.args.save)
        self.predict = str_to_bool(self.args.predict)
        self.preview_predict = str_to_bool(self.args.preview_prediction)
        self.logger = logger
        cameras = None
        # get transport layer factory
        self.tlFactory = pylon.TlFactory.GetInstance()
        # get the camera list 
        self.logger.info(f'Basler {self.cam_id}: Searching for camera...')
        self.devices = self.tlFactory.EnumerateDevices()
        self.vid_cod = cv2.VideoWriter_fourcc('m', 'p', '4', 'v')
        self.nframes = 0
        self.logger.info(f'Basler {self.cam_id}: Connecting to the Basler camera...')
        # print('Connecting to the camera...')

        n = 0
        while cameras is None and n < connect_retries:
            try:
                cameras = pylon.InstantCameraArray(min(len(self.devices), max_cams))
                self.camera = cameras[cam_id]
                self.camera = pylon.InstantCamera(self.tlFactory.CreateDevice(self.devices[self.cam_id]))
                # self.camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())
                # print(dir(self.camera))
                # self.camera.MaxNumBuffer.Value = 20
                self.logger.info(f"Basler {self.cam_id}: Num. of cameras detected: {cameras.GetSize()}, selected cam_ID: {cam_id}")
                # print(f"Num. of cameras detected: {cameras.GetSize()}, selected cam_ID: {cam_id}")
                self.init_camera()

            except Exception as e:
                # self.logger.info(f'Trying to detect camera, trial {n}/{connect_retries}...')
                print(f'Basler {self.cam_id}: Trying to detect camera, trial {n}/{connect_retries}...')
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
        self.camera.MaxNumBuffer.Value = int(self.cam['options']['AcquisitionFrameRate'])
        self.name = self.camera.GetDeviceInfo().GetModelName()
        self.logger.info(f"Cam {self.cam_id}, name: {self.name}, serial: {self.camera.DeviceInfo.GetSerialNumber()}")
        # print(f"Cam {self.cam_id}, name: {self.name}, serial: {self.camera.DeviceInfo.GetSerialNumber()}")
        # self.camera.SetCameraContext(self.cam_id)
        self.logger.info(f"Camera {self.cam_id} [{self.name}] successfully initialized!")
        # print(f"Camera {self.cam_id} [{self.name}] successfully initialized!")
        self.nodemap = self.camera.GetNodeMap()
        self.strobe = self.cam['strobe']
        if self.save:
            pylon.FeaturePersistence.Save(os.path.join(self.config['savedir'], self.experiment, "nodemap.txt"), self.nodemap)
        self.update_settings()
        # pylon.FeaturePersistence.Load("config/acA2040-120um_24516213.pfs", self.nodemap, True)
        
        self.converter = pylon.ImageFormatConverter()
        self.converter.OutputPixelFormat = pylon.PixelType_BGR8packed # converting to opencv bgr format
        self.converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
        
        if self.predict:
            self.predictor = Predictor(self.logger, self.args.model_path)
            # self.predictor.start()

        if self.preview:
            self.vid_show = VideoShow(self.name, self.preview_predict)
            self.vid_show.frame = np.zeros((self.cam['options']['Height'], self.cam['options']['Width']), dtype=np.uint8)
            if self.vid_show.show_pred:
                self.vid_show.pred_result = self.predictor.pred_result
            self.vid_show.start()

        if self.save:
            self.init_video_writer()

    def close(self):
        self.camera.Close()

    def init_video_writer(self):
        self.writer_obj = cv2.VideoWriter(os.path.join(self.config['savedir'], self.experiment, f"video_basler_{self.cam_id}.mp4"), self.vid_cod, self.args.videowrite_fps,
                                    (self.cam['options']['Width'], self.cam['options']['Height']))
        self.write_frames = True
        self.frame_write_queue = Queue()
        self.frame_writer()
    
    def convert_image(self, grabResult):
        return self.converter.Convert(grabResult).GetArray()
    
    def update_settings(self):
        """ Updates Basler camera settings.
        Attributes, types, and range of possible values for each attribute are available
        in the camera documentation. 
        These are extraordinarily tricky! Order matters! For exampple, ExposureAuto must be set
        to Off before ExposureTime can be set. 
        """
        self.logger.info("-updating settings-")
        # print("-updating settings-")

        if self.args.nodemap_path is not None:
            self.logger.info("Loading saved configs to camera")
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

    def set_value(self, nodemap, nodename, value):
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
                    self.logger.info('Valid entries: ')
                    entrylist = nodeval.GetEntries()
                    for entry in entrylist:
                        self.logger.info(entry)
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
            self.logger.info("ERROR setting:", nodename, value)
            # print("ERROR setting:", nodename, value)
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
 
    def compute_timestamp_offset(self):
        self.camera.TimestampLatch.Execute()
        self.timestamp_offset = time.perf_counter() - self.camera.TimestampLatchValue.GetValue()*1e-9 - self.start_t

    # @threaded
    def get_n_frames(self, n_frames, timeout_time=2000, report_period=10):
        if str_to_bool(self.args.trigger_with_arduino):
            self.camera.StartGrabbing(pylon.GrabStrategy_OneByOne)
        else:
            self.camera.StartGrabbingMax(n_frames)

        # print(f"Started cam {self.name} acquisition")
        self.logger.info(f"Basler {self.cam_id}: Started acquisition")
        self.start_timer = time.perf_counter()

        # self.logger.info("Looping - %s" % self.name)
        # print("Looping - %s" % self.name)
        
        try:
            if self.camera.GetGrabResultWaitObject().Wait(0):
                # print("grab results waiting")
                self.logger.info(f"Basler {self.cam_id}: grab results waiting")

            self.logger.info(f'Basler {self.cam_id}: Checking for results')
            # print('Checking for results')
            last_report = 0

            while not self.camera.GetGrabResultWaitObject().Wait(0):
                elapsed_pre = time.perf_counter() - self.start_timer #exp_start_tim     
                if round(elapsed_pre) % 5 == 0 and round(elapsed_pre) != last_report:
                    # print("...waiting grabbing", round(elapsed_pre))
                    self.logger.info(f"Basler {self.cam_id}: ...waiting grabbing", round(elapsed_pre))
                    
                last_report = round(elapsed_pre)

            metadata = {}

            while self.camera.IsGrabbing():

                if self.nframes == 0:
                    elapsed_time = 0
                    self.frame_timer = time.perf_counter()

                if self.nframes % round(report_period * self.cam['options']['AcquisitionFrameRate']) == 0:
                    # print("[fps %.2f] grabbing (%ith frame) | elapsed %.2f" % (self.cam['options']['AcquisitionFrameRate'], self.nframes, elapsed_time))
                    self.logger.info("Basler %d: [fps %.2f] grabbing (%ith frame) | elapsed %.2f" % (self.cam_id, self.cam['options']['AcquisitionFrameRate'], self.nframes, elapsed_time))

                image_result = self.camera.RetrieveResult(timeout_time, pylon.TimeoutHandling_Return) #, pylon.TimeoutHandling_ThrowException)
                #if (image_result.GetNumberOfSkippedImages()):
                #    print("Skipped ", image_result.GetNumberOfSkippedImages(), " image.")
                if image_result is None and int(elapsed_time) % 5 == 0: #not image_result.GrabSucceeded():
                    self.logger.info(f"Basler {self.cam_id}:... waiting frame")
                    # print("... waiting frame")
                    continue

                if image_result.GrabSucceeded():
                    if self.nframes == 0:
                        init_time_stamp = image_result.TimeStamp
                    last_time_stamp = image_result.TimeStamp

                    self.nframes += 1
                    # if self.nframes % self.cam['options']['AcquisitionFrameRate'] == 0:
                        # print(f'Frame: {self.nframes} / {n_frames}')
                        # self.logger.info(f'Frame: {self.nframes} / {n_frames}')
                        
                    frame = self.convert_image(image_result)
                    self.last_frame = frame.copy()
                    
                    if self.save:
                        self.frame_write_queue.put_nowait(self.last_frame)

                    if self.predict:
                        self.predictor.frame = frame
                        self.predictor.n_frame = self.nframes
                        self.predictor.get_random_prediction()

                    if self.preview:
                        self.vid_show.frame = frame
                        self.vid_show.n_frame = self.nframes
                        if self.preview_predict:
                            self.vid_show.pred_result = self.predictor.pred_result

                    metadata[image_result.ID] = {}
                    metadata[image_result.ID]['date_time_stamp'] = datetime.now().strftime("%Y%m%d_%H_%M_%S.%f")  # microsec precision
                    metadata[image_result.ID]['fps'] = self.camera.ResultingFrameRate.Value
                    # metadata[grabResult.ID]['frame_ID'] = grabResult.ID
                    metadata[image_result.ID]['frame_number'] = image_result.ImageNumber
                    metadata[image_result.ID]['time_stamp_w_offset'] = image_result.GetTimeStamp()*1e-9 + self.timestamp_offset
                    metadata[image_result.ID]['cam_clock_time_stamp'] = image_result.TimeStamp                    

                    image_result.Release()

                    elapsed_time = time.perf_counter() - self.frame_timer
                    if self.nframes >= n_frames:
                        if self.preview:
                            self.vid_show.stop()
                        self.logger.info(f"Basler {self.cam_id}: Breaking...")
                        # print("Breaking...")
                        break 

        except KeyboardInterrupt:
            self.logger.info(f"Basler {self.cam_id}: Keyboard interrupt detected.")
            # print("ABORT loop")
            
        finally:
            
            if self.preview:
                self.vid_show.stop()
            if self.predict:
                self.predictor.stop()
            if self.save:
                self.write_frames = False
                self.save_vid_metadata(metadata)
            self.logger.info(f'Basler {self.cam_id}: Elapsed time (time.perf_counter()) for processing {self.nframes} frames at {self.cam["options"]["AcquisitionFrameRate"]} FPS: {time.perf_counter() - self.frame_timer} sec.')
            self.logger.info(f'Basler {self.cam_id}: Time difference (grabResult.TimeStamp) between the first and the last frame timestamp: {(last_time_stamp - init_time_stamp) * 1e-9} sec.')
            # print(f'Elapsed time (time.perf_counter()) for processing {n_frames} frames at {self.cam["options"]["AcquisitionFrameRate"]} FPS: {time.perf_counter() - self.frame_timer} sec.')
            # print(f'Time difference (grabResult.TimeStamp) between the first and the last frame timestamp: {(last_time_stamp - init_time_stamp) * 1e-9} sec.')
    
    @threaded
    def frame_writer(self):
        while self.write_frames:
            if self.frame_write_queue.empty():
                continue
            self.writer_obj.write(self.frame_write_queue.get_nowait())

    def save_vid_metadata(self, metadata=None):
        if metadata is not None:
            with open(os.path.join(self.config['savedir'], self.experiment, f'metadata_basler_{self.cam_id}.json'), 'w') as file:
                json.dump(metadata, file)
                # with open(os.path.join(self.config['savedir'], self.experiment, f'metadata.pickle'), 'wb') as file:
                #     pickle.dump(metadata, file, pickle.HIGHEST_PROTOCOL)
        self.writer_obj.release()
    