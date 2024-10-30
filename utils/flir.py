import os
import cv2
import json
import time
import PySpin
import numpy as np
from datetime import datetime
from .preview import VideoShow
from .prediction import Predictor
from .helpers import str_to_bool
from queue import Queue
from concurrent.futures import ThreadPoolExecutor


tp = ThreadPoolExecutor(100)  # max 10 threads

def threaded(fn):
    def wrapper(*args, **kwargs):
        return tp.submit(fn, *args, **kwargs)  # returns Future object
    return wrapper


class FLIR():

    def __init__(self, args, cam, experiment, config, start_t, logger, cam_id=0, max_cams=2, connect_retries=20) -> None:
        print('Searching for camera...')

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
        self.clock = 1e6 # from GS3-PGE-Technical-Reference.pdf (https://www.teledynevisionsolutions.com/learn/learning-center/machine-vision/mv-getting-started/)
        
        self.vid_cod = cv2.VideoWriter_fourcc('m', 'p', '4', 'v')
        self.nframes = 0
        self.logger = logger
        self.logger.info('Connecting to the FLIR camera...')

        self.processor = PySpin.ImageProcessor()
        self.processor.SetColorProcessing(PySpin.SPINNAKER_COLOR_PROCESSING_ALGORITHM_HQ_LINEAR)

        # Setup the system and camera
        self.init_camera()

        # self.camera = EasyPySpin.VideoCapture(cam_id)

        self.update_settings()

        if self.predict:
            self.predictor = Predictor(self.logger, self.args.model_path)
        
        if self.preview:
            self.vid_show = VideoShow(f'FLIR {self.cam_id}', self.preview_predict, pred_preview_button='f')
            self.vid_show.frame = np.zeros((self.cam['options']['Height'], self.cam['options']['Width']), dtype=np.uint8)
            if self.vid_show.show_pred:
                self.vid_show.pred_result = self.predictor.pred_result
            self.vid_show.start()

        if self.save:
            self.init_video_writer()

    def init_camera(self):
        self.system = PySpin.System.GetInstance()
        self.cam_list = self.system.GetCameras()
        self.camera = self.cam_list[self.cam_id]
        self.camera.Init()
        # self.compute_timestamp_offset()
        self.nodemap = self.camera.GetNodeMap()
        
        self.nodemap_tldevice = self.camera.GetTLDeviceNodeMap()
        self.device_serial_number = PySpin.CStringPtr(self.nodemap_tldevice.GetNode('DeviceSerialNumber')).GetValue()
        self.logger.info(f'FLIR {self.cam_id} is initialized.')
        
    def update_settings(self):
        # node_acquisition_mode = PySpin.CEnumerationPtr(self.nodemap.GetNode('AcquisitionMode'))

        if str_to_bool(self.args.trigger_with_arduino):
            self.camera.AcquisitionMode.SetIntValue(PySpin.AcquisitionMode_SingleFrame)
            # node_acquisition_mode_val = node_acquisition_mode.GetEntryByName('Single Frame')
        else:
            self.camera.AcquisitionMode.SetIntValue(PySpin.AcquisitionMode_Continuous)
            # node_acquisition_mode_val = node_acquisition_mode.GetEntryByName('Continuous')

        # acquisition_mode = node_acquisition_mode_val.GetValue()
        # node_acquisition_mode.SetIntValue(acquisition_mode)
        self.logger.info(f'FLIR {self.cam_id} acquisition mode is set to {"continuous" if not str_to_bool(self.args.trigger_with_arduino) else "single frame"}.')

        self.camera.PixelFormat.SetValue(PySpin.PixelFormat_Mono8) # replace with .yaml parameter
        self.camera.AcquisitionFrameRate.SetValue(self.cam['options']['AcquisitionFrameRate'])
        self.camera.Width.SetValue(self.cam['options']['Width'])
        self.camera.Height.SetValue(self.cam['options']['Height'])
        
        width = self.camera.Width.GetValue()
        height = self.camera.Height.GetValue()
        fps = self.camera.AcquisitionFrameRate.GetValue()
        self.logger.info(f'FLIR {self.cam_id}: width: {width}, height: {height}, fps: {fps}')

        self.logger.info(f'FLIR {self.cam_id} settings updated.')
    
    def close(self):
        
        self.camera.DeInit()
        self.cam_list.Clear()
        self.system.ReleaseInstance()
    
    def init_video_writer(self):

        chosenAviType = AviType.MJPG  # change me!

        self.avi_recorder = PySpin.SpinVideo()
        avi_filename = os.path.join(self.config['savedir'], self.experiment, f"video_flir_{self.cam_id}")

        if chosenAviType == AviType.UNCOMPRESSED:
            option = PySpin.AVIOption()
        elif chosenAviType == AviType.MJPG:
            option = PySpin.MJPGOption()
            option.quality = 75
        elif chosenAviType == AviType.H264:
            option = PySpin.H264Option()
            option.bitrate = 1000000

        option.frameRate = self.args.videowrite_fps
        option.height = self.cam['options']['Height']
        option.width = self.cam['options']['Width']

        self.avi_recorder.Open(avi_filename, option)


        # self.writer_obj = cv2.VideoWriter(os.path.join(self.config['savedir'], self.experiment, f"video_flir_{self.cam_id}.mp4"), self.vid_cod, self.args.videowrite_fps,
        #                             (self.cam['options']['Width'], self.cam['options']['Height']))
        self.write_frames = True
        self.frame_write_queue = Queue()
        self.frame_writer()
    
    @threaded
    def frame_writer(self):
        while self.write_frames:
            if self.frame_write_queue.empty():
                continue
            self.avi_recorder.Append(self.frame_write_queue.get_nowait())

    def save_vid_metadata(self, metadata=None):
        if metadata is not None:
            with open(os.path.join(self.config['savedir'], self.experiment, f'metadata_flir_{self.cam_id}.json'), 'w') as file:
                json.dump(metadata, file)
        # self.writer_obj.release()
        self.avi_recorder.Close()

    # def compute_timestamp_offset(self):
    #     self.camera.TimestampLatch.Execute()
    #     self.timestamp_offset = time.perf_counter() - self.camera.TimestampLatchValue.GetValue()*1e-9 - self.start_t

    def get_n_frames(self, n_frames, timeout_time=1000, report_period=10):

        # print(f"Started cam {self.name} acquisition")
        self.logger.info(f"FLIR {self.cam_id}: Started acquisition")
        self.start_timer = time.perf_counter()

        self.camera.BeginAcquisition()

        try:
            metadata = {}
            prev_timestamp = None

            while self.camera.IsStreaming():

                if self.nframes == 0:
                    elapsed_time = 0
                    self.frame_timer = time.perf_counter()

                if self.nframes % round(report_period * self.cam['options']['AcquisitionFrameRate']) == 0:
                    # print("[fps %.2f] grabbing (%ith frame) | elapsed %.2f" % (self.cam['options']['AcquisitionFrameRate'], self.nframes, elapsed_time))
                    self.logger.info("FLIR %d: [fps %.2f] grabbing (%ith frame) | elapsed %.2f" % (self.cam_id, self.cam['options']['AcquisitionFrameRate'], self.nframes, elapsed_time))

                image_result = self.camera.GetNextImage(timeout_time) # timeout_time == buffer size, for the arg name consistency

                #  Ensure image completion
                if image_result.IsIncomplete():
                    self.logger.info(f'FLIR {self.cam_id}: incomplete with image status %d ...' % image_result.GetImageStatus())
                    continue
                else:
                    if self.nframes == 0:
                        init_time_stamp = image_result.GetTimeStamp()
                    last_time_stamp = image_result.GetTimeStamp()

                    frame = image_result.GetNDArray()
                    self.last_frame = frame.copy()

                    self.nframes += 1
                    # if self.nframes % self.cam['options']['AcquisitionFrameRate'] == 0:
                        # print(f'Frame: {self.nframes} / {n_frames}')
                        # self.logger.info(f'Frame: {self.nframes} / {n_frames}')
                    
                    if self.save:
                        self.frame_write_queue.put_nowait(self.processor.Convert(image_result, PySpin.PixelFormat_Mono8))

                    if self.predict:
                        self.predictor.frame = frame
                        self.predictor.n_frame = self.nframes
                        self.predictor.get_random_prediction()

                    if self.preview:
                        self.vid_show.frame = frame.copy()
                        # self.vid_show.frame = np.expand_dims(frame.copy(), -1)
                        # print(f'fsum: {np.sum(self.vid_show.frame)}')
                        self.vid_show.n_frame = self.nframes
                        if self.preview_predict:
                            self.vid_show.pred_result = self.predictor.pred_result


                    metadata[image_result.GetFrameID() + 1] = {}
                    metadata[image_result.GetFrameID() + 1]['frame_ID'] = image_result.GetID()
                    metadata[image_result.GetFrameID() + 1]['date_time_stamp'] = datetime.now().strftime("%Y%m%d_%H_%M_%S.%f")  # microsec precision
                    metadata[image_result.GetFrameID() + 1]['fps'] = self.camera.AcquisitionFrameRate.GetValue() if prev_timestamp is None else 1e9 / (last_time_stamp - prev_timestamp) 
                    metadata[image_result.GetFrameID() + 1]['frame_number'] = self.nframes + 1
                    metadata[image_result.GetFrameID() + 1]['time_stamp_w_offset'] = (last_time_stamp + init_time_stamp) * 1e-9
                    metadata[image_result.GetFrameID() + 1]['cam_clock_time_stamp'] = last_time_stamp      

                    prev_timestamp = last_time_stamp

                    image_result.Release()

                    elapsed_time = time.perf_counter() - self.frame_timer
                    if self.nframes >= n_frames:
                        if self.preview:
                            self.vid_show.stop()
                        self.logger.info(f"FLIR {self.cam_id}: Breaking...")
                        # print("Breaking...")
                        break 

        except KeyboardInterrupt:
            self.logger.info(f"FLIR {self.cam_id}: Keyboard interrupt detected.")

        finally:
            self.camera.EndAcquisition()
            if self.preview:
                self.vid_show.stop()
            if self.predict:
                self.predictor.stop()
            if self.save:
                self.write_frames = False
                self.save_vid_metadata(metadata)
            self.logger.info(f'FLIR {self.cam_id}: Elapsed time (time.perf_counter()) for processing {self.nframes} frames at {self.cam["options"]["AcquisitionFrameRate"]} FPS: {time.perf_counter() - self.frame_timer} sec.')
            self.logger.info(f'FLIR {self.cam_id}: Time difference (grabResult.TimeStamp) between the first and the last frame timestamp: {(last_time_stamp - init_time_stamp) * 1e-9} sec.')
            

class AviType:
    """'Enum' to select AVI video type to be created and saved"""
    UNCOMPRESSED = 0
    MJPG = 1
    H264 = 2

def print_device_info(cam):
    """
    This function prints the device information of the camera from the transport
    layer; please see NodeMapInfo example for more in-depth comments on printing
    device information from the nodemap.

    :param cam: Camera to get device information from.
    :type cam: CameraPtr
    :return: True if successful, False otherwise.
    :rtype: bool
    """

    print('\n*** DEVICE INFORMATION ***\n')

    try:
        result = True
        nodemap = cam.GetTLDeviceNodeMap()

        node_device_information = PySpin.CCategoryPtr(nodemap.GetNode('DeviceInformation'))

        if PySpin.IsReadable(node_device_information):
            features = node_device_information.GetFeatures()
            for feature in features:
                node_feature = PySpin.CValuePtr(feature)
                print('%s: %s' % (node_feature.GetName(),
                                  node_feature.ToString() if PySpin.IsReadable(node_feature) else 'Node not readable'))

        else:
            print('Device control information not readable.')

    except PySpin.SpinnakerException as ex:
        print('Error: %s' % ex.message)
        return False

    return result

def configure_custom_image_settings(cam):
    """
    Configures a number of settings on the camera including offsets X and Y,
    width, height, and pixel format. These settings must be applied before
    BeginAcquisition() is called; otherwise, those nodes would be read only.
    Also, it is important to note that settings are applied immediately.
    This means if you plan to reduce the width and move the x offset accordingly,
    you need to apply such changes in the appropriate order.

    :param cam: Camera to configure settings on.
    :type cam: CameraPtr
    :return: True if successful, False otherwise.
    :rtype: bool
    """
    print('\n*** CONFIGURING CUSTOM IMAGE SETTINGS ***\n')

    try:
        result = True

        # Apply mono 8 pixel format
        #
        # *** NOTES ***
        # In QuickSpin, enumeration nodes are as easy to set as other node
        # types. This is because enum values representing each entry node
        # are added to the API.
        if cam.PixelFormat.GetAccessMode() == PySpin.RW:
            cam.PixelFormat.SetValue(PySpin.PixelFormat_Mono8)
            print('Pixel format set to %s...' % cam.PixelFormat.GetCurrentEntry().GetSymbolic())

        else:
            print('Pixel format not available...')
            result = False

        # Apply minimum to offset X
        #
        # *** NOTES ***
        # Numeric nodes have both a minimum and maximum. A minimum is retrieved
        # with the method GetMin(). Sometimes it can be important to check
        # minimums to ensure that your desired value is within range.
        if cam.OffsetX.GetAccessMode() == PySpin.RW:
            cam.OffsetX.SetValue(cam.OffsetX.GetMin())
            print('Offset X set to %d...' % cam.OffsetX.GetValue())

        else:
            print('Offset X not available...')
            result = False

        # Apply minimum to offset Y
        #
        # *** NOTES ***
        # It is often desirable to check the increment as well. The increment
        # is a number of which a desired value must be a multiple. Certain
        # nodes, such as those corresponding to offsets X and Y, have an
        # increment of 1, which basically means that any value within range
        # is appropriate. The increment is retrieved with the method GetInc().
        if cam.OffsetY.GetAccessMode() == PySpin.RW:
            cam.OffsetY.SetValue(cam.OffsetY.GetMin())
            print('Offset Y set to %d...' % cam.OffsetY.GetValue())

        else:
            print('Offset Y not available...')
            result = False

        # Set maximum width
        #
        # *** NOTES ***
        # Other nodes, such as those corresponding to image width and height,
        # might have an increment other than 1. In these cases, it can be
        # important to check that the desired value is a multiple of the
        # increment.
        #
        # This is often the case for width and height nodes. However, because
        # these nodes are being set to their maximums, there is no real reason
        # to check against the increment.
        if cam.Width.GetAccessMode() == PySpin.RW and cam.Width.GetInc() != 0 and cam.Width.GetMax != 0:
            cam.Width.SetValue(cam.Width.GetMax())
            print('Width set to %i...' % cam.Width.GetValue())

        else:
            print('Width not available...')
            result = False

        # Set maximum height
        #
        # *** NOTES ***
        # A maximum is retrieved with the method GetMax(). A node's minimum and
        # maximum should always be a multiple of its increment.
        if cam.Height.GetAccessMode() == PySpin.RW and cam.Height.GetInc() != 0 and cam.Height.GetMax != 0:
            cam.Height.SetValue(cam.Height.GetMax())
            print('Height set to %i...' % cam.Height.GetValue())

        else:
            print('Height not available...')
            result = False

    except PySpin.SpinnakerException as ex:
        print('Error: %s' % ex)
        return False

    return result
