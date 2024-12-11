import os
import cv2
import json
import time
import PySpin
import pprint
import numpy as np
import utils.pointgrey_utils as pg
from datetime import datetime
from .preview import VideoShow
from .prediction import Predictor
from .helpers import str_to_bool
from queue import Queue
from concurrent.futures import ThreadPoolExecutor

# PySpin.System.SetCTIFile("/opt/spinnaker/lib/spinnaker-gentl/Spinnaker_GenTL.cti")

tp = ThreadPoolExecutor(100)  # max 10 threads

def threaded(fn):
    def wrapper(*args, **kwargs):
        return tp.submit(fn, *args, **kwargs)  # returns Future object
    return wrapper


class FLIR():

    def __init__(self, args, cam, camname, experiment, config, start_t, logger, cam_id=0, max_cams=2, connect_retries=20) -> None:
        print('Searching for camera...')

        self.start_t = start_t
        self.args = args
        self.cam = cam
        self.camname = camname
        self.experiment = experiment
        self.config = config
        self.cam_id = cam_id
        self.frame_timer = None
        # self.preview = str_to_bool(self.args.preview)
        self.preview = cam['preview']
        self.save = str_to_bool(self.args.save)
        self.predict = cam['predict']
        self.preview_predict = cam['preview_predict']
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
            self.vid_show = VideoShow(f'{self.camname}', self.preview_predict, pred_preview_button=cam['pred_preview_toggle_button'])
            self.vid_show.frame = np.zeros((self.cam['options']['Height'], self.cam['options']['Width']), dtype=np.uint8)
            if self.vid_show.show_pred:
                self.vid_show.pred_result = self.predictor.pred_result
            self.vid_show.start()

        if self.save:
            self.init_video_writer()

    def init_camera(self):
        self.system = PySpin.System.GetInstance()
        self.cam_list = self.system.GetCameras()

        if len(self.cam_list) == 0:
            raise Exception(f'{self.camname} is not detected.')
        
        self.camera = self.cam_list.GetBySerial(str(self.cam['serial']))
        # self.camera = self.cam_list[self.cam_id]
        self.camera.Init()
        # self.compute_timestamp_offset()
        self.nodemap = self.camera.GetNodeMap()
        self.nodemap_tldevice = self.camera.GetTLDeviceNodeMap()
        self.device_serial_number = PySpin.CStringPtr(self.nodemap_tldevice.GetNode('DeviceSerialNumber')).GetValue()
        self.set_default_params()
        self.logger.info(f'{self.camname} is initialized.')
    
    def set_hw_trigger(self):
        # Ensure acquisition is stopped before changing settings
        self.camera.AcquisitionStop.Execute()

        # Set acquisition mode to single frame
        self.camera.AcquisitionMode.SetValue(PySpin.AcquisitionMode_SingleFrame)

        # Set trigger mode off to configure trigger source
        self.camera.TriggerMode.SetValue(PySpin.TriggerMode_Off)

        # Select the trigger source
        self.camera.TriggerSource.SetValue(PySpin.TriggerSource_Line0)  # Or your desired trigger source

        # Set trigger activation to rising edge (or as needed)
        self.camera.TriggerActivation.SetValue(PySpin.TriggerActivation_RisingEdge)

        # Enable trigger mode
        self.camera.TriggerMode.SetValue(PySpin.TriggerMode_On)

        self.logger.info(f"{self.camname}: Trigger configured successfully.")

    def configure_camera_for_trigger(self):
        # try:

        # Set acquisition mode to single frame
        self.camera.AcquisitionMode.SetValue(PySpin.AcquisitionMode_Continuous)

        # Set the camera to use an external trigger
        # self.camera.TriggerMode.SetValue(PySpin.TriggerMode_Off)
        self.camera.TriggerMode.SetValue(PySpin.TriggerSelector_FrameStart)
        self.camera.TriggerMode.SetValue(PySpin.TriggerMode_On)
        self.camera.TriggerSource.SetValue(PySpin.TriggerSource_Line3)
        self.camera.TriggerActivation.SetValue(PySpin.TriggerActivation_RisingEdge)
        self.camera.TriggerOverlap.SetValue(PySpin.TriggerOverlap_ReadOut)
        self.camera.AcquisitionMode.SetValue(PySpin.AcquisitionMode_Continuous)
        self.camera.AcquisitionStatusSelector.SetValue(PySpin.AcquisitionStatusSelector_FrameTriggerWait)
        # self.camera.TriggerMode.SetValue(PySpin.TriggerMode_On)

        # Set trigger overlap if required (e.g., for hardware overlap)
        # if PySpin.TriggerOverlap_Active != -1:
        #     self.camera.TriggerOverlap.SetValue(PySpin.TriggerOverlap_Active)
        # self.camera.TriggerOverlap.SetValue(PySpin.TriggerOverlap_ReadOut)
                    
        # Adjust other camera settings (exposure, gain, etc.) as needed
        # self.camera.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)
        # self.camera.ExposureTime.SetValue(5000)  # example exposure time in microseconds
        
        self.logger.info(f"{self.camname}: Camera configured for external trigger.")
        # except PySpin.SpinnakerException as e:
        #     self.logger.info(f"FLIR {self.cam_id}: Error: {e}")

    def configure_trigger(self):
        """
        Configures the camera for hardware triggering.
        """
        try:
            nodemap = self.camera.GetNodeMap()

            # set trigger selector
            trigger_selector = PySpin.CEnumerationPtr(nodemap.GetNode("TriggerSelector"))
            trigger_selector.SetIntValue(trigger_selector.GetEntryByName("FrameStart").GetValue())

            # Set trigger mode to On
            trigger_mode = PySpin.CEnumerationPtr(nodemap.GetNode("TriggerMode"))
            trigger_mode.SetIntValue(trigger_mode.GetEntryByName("On").GetValue())

            trigger_source = PySpin.CEnumerationPtr(nodemap.GetNode("TriggerSource"))
            trigger_source.SetIntValue(trigger_source.GetEntryByName("Line3").GetValue())

            trigger_activation = PySpin.CEnumerationPtr(nodemap.GetNode("TriggerActivation"))
            trigger_activation.SetIntValue(trigger_activation.GetEntryByName("RisingEdge").GetValue())

            # Set trigger overlap to ReadOut (optional)
            trigger_overlap = PySpin.CEnumerationPtr(nodemap.GetNode("TriggerOverlap"))
            trigger_overlap.SetIntValue(trigger_overlap.GetEntryByName("ReadOut").GetValue())

            # Ensure frame rate control is disabled
            frame_rate_enable = PySpin.CBooleanPtr(nodemap.GetNode("AcquisitionFrameRateEnable"))
            if PySpin.IsAvailable(frame_rate_enable) and PySpin.IsWritable(frame_rate_enable):
                frame_rate_enable.SetValue(False)
                
            pg.set_value(nodemap, 'ExposureMode', self.cam['options']['ExposureMode'])
            pg.set_value(nodemap, 'ExposureAuto', self.cam['options']['ExposureAuto'])
            pg.set_value(nodemap, 'ExposureTime', self.cam['options']['ExposureTime'])
            
            acquisition_mode = PySpin.CEnumerationPtr(nodemap.GetNode("AcquisitionMode"))
            acquisition_mode.SetIntValue(acquisition_mode.GetEntryByName("Continuous").GetValue())

            # set trigger selector
            acq_status_selector = PySpin.CEnumerationPtr(nodemap.GetNode("AcquisitionStatusSelector"))
            acq_status_selector.SetIntValue(acq_status_selector.GetEntryByName("FrameTriggerWait").GetValue())

            self.logger.info(f"{self.camname}: Trigger configured successfully.")
        except PySpin.SpinnakerException as e:
            self.logger.info(f"{self.camname}: Error configuring trigger: {e}")
            
    def update_settings(self):
        # node_acquisition_mode = PySpin.CEnumerationPtr(self.nodemap.GetNode('AcquisitionMode'))
        # if not str_to_bool(self.args.trigger_with_arduino):
        #     self.reset()
        # else:
        if str_to_bool(self.args.trigger_with_arduino):
            # pg.turn_strobe_on(self.nodemap, self.cam['strobe']['line'], strobe_duration=self.cam['strobe']['duration'])
            self.configure_camera_for_trigger()
            # self.configure_trigger()
            # self.set_hw_trigger()
            # self.camera.AcquisitionMode.SetIntValue(PySpin.AcquisitionMode_SingleFrame)
        for key, value in self.cam['options'].items():
        # for key, value in options.items():
            # if key in ['AcquisitionFrameRate', 'AcquisitionFrameRateAuto', 'AcquisitionMode']:
            #     continue
            if key in ['Height', 'Width']:
                pg.set_value(self.nodemap, key, value)
        
        # if str_to_bool(self.args.trigger_with_arduino):
        #     # self.camera.AcquisitionMode.SetIntValue(PySpin.AcquisitionMode_Continuous)
        #     # configure_trigger(self.camera, TriggerType.HARDWARE)
        #     # self.camera.AcquisitionMode.SetIntValue(PySpin.AcquisitionMode_SingleFrame)
        #     # node_single_frame = PySpin.CEnumerationPtr(self.nodemap.GetNode("SingleFrameAcquisitionMode"))
        #     # single_frame_enable = node_single_frame.GetEntryByName("Triggered").GetValue()
        #     # node_single_frame.SetIntValue(single_frame_enable)
            
            
        #     # self.camera.LineSelector.SetValue(PySpin.LineSelector_Line0)
        #     # self.camera.V3_3Enable.SetValue(True)
        #     # self.camera.AcquisitionMode.SetIntValue(PySpin.AcquisitionMode_MultiFrame)

        #     # node_acquisition_mode_val = node_acquisition_mode.GetEntryByName('Single Frame')

        #     for key, value in self.cam['options'].items():
        #     # for key, value in options.items():
        #         if key == 'AcquisitionFrameRate':
        #             continue
        #         pg.set_value(self.nodemap, key, value)
        #     pg.turn_strobe_on(self.nodemap, self.cam['strobe']['line'], strobe_duration=self.cam['strobe']['duration'])
        #     # pg.turn_strobe_on(self.nodemap, strobe['line'], strobe_duration=strobe['duration'])

        #     # Set acquisition mode to single-frame
        #     # self.camera.AcquisitionMode.SetValue(PySpin.AcquisitionMode_MultiFrame)
        #     # # Set trigger mode to On
        #     # self.camera.TriggerMode.SetValue(PySpin.TriggerMode_Off)  # Disable trigger mode first to configure settings
        #     # self.camera.TriggerSource.SetValue(PySpin.TriggerSource_Line0)  # Set to external trigger line (usually Line0)
        #     # self.camera.TriggerSelector.SetValue(PySpin.TriggerSelector_FrameStart)  # Trigger each frame
        #     # self.camera.TriggerActivation.SetValue(PySpin.TriggerActivation_RisingEdge)  # Trigger on rising edge of pulse
        #     # # Enable Trigger mode
        #     # self.camera.TriggerMode.SetValue(PySpin.TriggerMode_On)

        # else:
        #     self.camera.AcquisitionMode.SetIntValue(PySpin.AcquisitionMode_Continuous)
        #     # node_acquisition_mode_val = node_acquisition_mode.GetEntryByName('Continuous')

        # # acquisition_mode = node_acquisition_mode_val.GetValue()
        # # node_acquisition_mode.SetIntValue(acquisition_mode)
        # self.logger.info(f'FLIR {self.cam_id} acquisition mode is set to {"continuous" if not str_to_bool(self.args.trigger_with_arduino) else "single frame"}.')
        
        # if self.cam['options']['PixelFormat'] == 'Mono8':
        #     self.camera.PixelFormat.SetValue(PySpin.PixelFormat_Mono8) 

        # self.camera.Width.SetValue(self.cam['options']['Width'])
        # self.camera.Height.SetValue(self.cam['options']['Height'])
        
        # disable auto frame rate

        if not str_to_bool(self.args.trigger_with_arduino):
            node_frame_rate_auto = PySpin.CEnumerationPtr(self.nodemap.GetNode("AcquisitionFrameRateAuto"))
            node_frame_rate_auto_off = node_frame_rate_auto.GetEntryByName("Off")
            frame_rate_auto_off = node_frame_rate_auto_off.GetValue()
            node_frame_rate_auto.SetIntValue(frame_rate_auto_off)
            node_frame_rate_enable = PySpin.CBooleanPtr(self.nodemap.GetNode("AcquisitionFrameRateEnabled"))
            node_frame_rate_enable.SetValue(True)
            self.camera.AcquisitionFrameRate.SetValue(self.cam['options']['AcquisitionFrameRate'])
        # else:
        #     node_frame_rate_enable = PySpin.CBooleanPtr(self.nodemap.GetNode("AcquisitionFrameRateEnabled"))
        #     node_frame_rate_enable.SetValue(False)
        
        width = self.camera.Width.GetValue()
        height = self.camera.Height.GetValue()

        self.logger.info(f'{self.camname}: width: {width}, height: {height}')
        # self.updated_nodemap = self.camera.GetNodeMap()
        # pprint.pprint(self.updated_nodemap)
        # print_device_info(self.camera)
        # self.print_all_camera_settings()
        self.logger.info(f'{self.camname}: settings updated.')
    
    def print_all_camera_settings(self):
        """
        Print all available settings of a FLIR camera using PySpin.
        """
        try:
            # Access the camera's NodeMap
            nodemap = self.camera.GetNodeMap()

            self.logger.info(f"{self.camname}: All Available Camera Settings:")

            # Iterate through all nodes in the NodeMap
            for node in nodemap.GetNodes():
                try:
                    name = node.GetName()  # Get the name of the setting
                    if PySpin.IsReadable(node):  # Check if the node is readable
                        value = node.ToString()
                    else:
                        value = "Not readable"
                    print(f"  {name}: {value}")
                except PySpin.SpinnakerException as e:
                    print(f"  {node.GetName()}: Error - {e}")
                except AttributeError:
                    continue  # Skip nodes that don't have the expected attributes

        except PySpin.SpinnakerException as e:
            self.logger.info(f"{self.camname}: Error: {e}")
            
    def set_default_params(self):
        self.logger.info(f"FLIR {self.cam_id}: Setting default params...")
        self.camera.UserSetSelector.SetValue(PySpin.UserSetSelector_Default)
        self.camera.UserSetLoad.Execute()

    def reconnect(self):
        self.logger.info(f"FLIR {self.cam_id}: Reconnecting...")
        ### disconnect - reconnect
        reset_node = PySpin.CCommandPtr(self.nodemap.GetNode('DeviceReset'))
        reset_node.Execute()
        time.sleep(2)

        self.cam_list.Clear()   # Clear the camera list
        self.system.ReleaseInstance()  # Release the system instance
        self.logger.info(f"FLIR {self.cam_id} disconnected.")

        self.system = PySpin.System.GetInstance()
        self.cam_list = self.system.GetCameras()
        self.camera = self.cam_list[0]
        self.camera.Init()
        self.nodemap_tldevice = self.camera.GetTLDeviceNodeMap()
        self.nodemap = self.camera.GetNodeMap()
        self.device_serial_number = PySpin.CStringPtr(self.nodemap_tldevice.GetNode('DeviceSerialNumber')).GetValue()

        self.logger.info(f"{self.camname} reconnected.")

    def close(self):
        
        try:
            self.camera.DeInit()
            self.cam_list.Clear()
            system = PySpin.System.GetInstance()
            system.ReleaseInstance()
            self.logger.info(f"{self.camname}: Closed.")
        except PySpin.SpinnakerException as e:
            self.logger.info(f"{self.camname}: Error during cleanup: {e}")
    
    def init_video_writer(self):

        chosenAviType = AviType.MJPG  # change me!

        self.avi_recorder = PySpin.SpinVideo()
        avi_filename = os.path.join(self.config['savedir'], self.experiment, f"video_{self.camname}")

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
        self.fram_writer_future = self.frame_writer()
    
    @threaded
    def frame_writer(self):
        while self.write_frames:
            if self.frame_write_queue.empty():
                continue
            self.avi_recorder.Append(self.frame_write_queue.get_nowait())
        
        while not self.frame_write_queue.empty():
            self.avi_recorder.Append(self.frame_write_queue.get_nowait())

    def save_vid_metadata(self, metadata=None):
        if metadata is not None:
            with open(os.path.join(self.config['savedir'], self.experiment, f'metadata_{self.camname}.json'), 'w') as file:
                json.dump(metadata, file)
        # self.writer_obj.release()
        self.avi_recorder.Close()

    # def compute_timestamp_offset(self):
    #     self.camera.TimestampLatch.Execute()
    #     self.timestamp_offset = time.perf_counter() - self.camera.TimestampLatchValue.GetValue()*1e-9 - self.start_t
            
    def get_n_frames(self, n_frames, timeout_time=1000, report_period=10):

        # print(f"Started cam {self.name} acquisition")
        self.logger.info(f"{self.camname}: Started acquisition.")
        self.start_timer = time.perf_counter()

        self.camera.BeginAcquisition()

        try:
            metadata = {}
            prev_timestamp = None

            while self.camera.IsStreaming():
            # while self.nframes < n_frames:
            #     self.camera.BeginAcquisition()

                if self.nframes == 0:
                    elapsed_time = 0
                    self.frame_timer = time.perf_counter()

                if self.nframes % round(report_period * self.cam['options']['AcquisitionFrameRate']) == 0:
                    # print("[fps %.2f] grabbing (%ith frame) | elapsed %.2f" % (self.cam['options']['AcquisitionFrameRate'], self.nframes, elapsed_time))
                    self.logger.info("%s: [fps %.2f] grabbing (%ith frame) | elapsed %.2f" % (self.camname, self.cam['options']['AcquisitionFrameRate'], self.nframes, elapsed_time))

                image_result = self.camera.GetNextImage(timeout_time) # timeout_time == buffer size, for the arg name consistency

                #  Ensure image completion
                if image_result.IsIncomplete():
                    self.logger.info(f'{self.camname}: incomplete with image status %d ...' % image_result.GetImageStatus())
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
                    metadata[image_result.GetFrameID() + 1]['fps'] = self.cam['options']['AcquisitionFrameRate'] if prev_timestamp is None else 1e9 / (last_time_stamp - prev_timestamp) 
                    metadata[image_result.GetFrameID() + 1]['frame_number'] = self.nframes + 1
                    metadata[image_result.GetFrameID() + 1]['time_stamp_w_offset'] = (last_time_stamp + init_time_stamp) * 1e-9
                    metadata[image_result.GetFrameID() + 1]['cam_clock_time_stamp'] = last_time_stamp      

                    prev_timestamp = last_time_stamp

                    image_result.Release()

                    elapsed_time = time.perf_counter() - self.frame_timer
                    if self.nframes >= n_frames:
                        if self.preview:
                            self.vid_show.stop()
                        self.logger.info(f"{self.camname}: Breaking...")
                        # print("Breaking...")
                        break

                    # if self.cam['options']['AcquisitionMode'] == 'SingleFrame':
                    #     self.camera.EndAcquisition()
                    #     self.camera.BeginAcquisition()

        except KeyboardInterrupt:
            self.logger.info(f"{self.camname}: Keyboard interrupt detected.")

        finally:
            self.camera.EndAcquisition()
            self.logger.info(f'{self.camname}: Ended acquisition.')
            self.logger.info(f'{self.camname}: Elapsed time (time.perf_counter()) for processing {self.nframes} frames at {self.cam["options"]["AcquisitionFrameRate"]} FPS: {time.perf_counter() - self.frame_timer} sec.')
            self.logger.info(f'{self.camname}: Time difference (grabResult.TimeStamp) between the first and the last frame timestamp: {(last_time_stamp - init_time_stamp) * 1e-9} sec.')
            if self.preview:
                self.vid_show.stop()
            if self.predict:
                self.predictor.stop()
            if self.save:
                self.logger.info(f'{self.camname}: Saving queued frames...')
                self.write_frames = False
                self.fram_writer_future.result()
                self.save_vid_metadata(metadata)
                self.logger.info(f'{self.camname}: Finished saving queued frames.')
            

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

# class TriggerType:
#     SOFTWARE = 1
#     HARDWARE = 2

# def configure_trigger(cam, CHOSEN_TRIGGER):
#     """
#     This function configures the camera to use a trigger. First, trigger mode is
#     set to off in order to select the trigger source. Once the trigger source
#     has been selected, trigger mode is then enabled, which has the camera
#     capture only a single image upon the execution of the chosen trigger.

#      :param cam: Camera to configure trigger for.
#      :type cam: CameraPtr
#      :return: True if successful, False otherwise.
#      :rtype: bool
#     """
#     result = True

#     # try:
#     # Ensure trigger mode off
#     # The trigger must be disabled in order to configure whether the source
#     # is software or hardware.
#     nodemap = cam.GetNodeMap()
#     node_trigger_mode = PySpin.CEnumerationPtr(nodemap.GetNode('TriggerMode'))
#     if not PySpin.IsReadable(node_trigger_mode) or not PySpin.IsWritable(node_trigger_mode):
#         print('Unable to disable trigger mode (node retrieval). Aborting...')
#         return False

#     node_trigger_mode_off = node_trigger_mode.GetEntryByName('Off')
#     if not PySpin.IsReadable(node_trigger_mode_off):
#         print('Unable to disable trigger mode (enum entry retrieval). Aborting...')
#         return False

#     node_trigger_mode.SetIntValue(node_trigger_mode_off.GetValue())

#     print('Trigger mode disabled...')

#     # Set TriggerSelector to FrameStart
#     # For this example, the trigger selector should be set to frame start.
#     # This is the default for most cameras.
#     node_trigger_selector= PySpin.CEnumerationPtr(nodemap.GetNode('TriggerSelector'))
#     if not PySpin.IsReadable(node_trigger_selector) or not PySpin.IsWritable(node_trigger_selector):
#         print('Unable to get trigger selector (node retrieval). Aborting...')
#         return False

#     node_trigger_selector_framestart = node_trigger_selector.GetEntryByName('FrameStart')
#     if not PySpin.IsReadable(node_trigger_selector_framestart):
#         print('Unable to set trigger selector (enum entry retrieval). Aborting...')
#         return False
#     node_trigger_selector.SetIntValue(node_trigger_selector_framestart.GetValue())

#     print('Trigger selector set to frame start...')

#     # Select trigger source
#     # The trigger source must be set to hardware or software while trigger
#     # mode is off.
#     node_trigger_source = PySpin.CEnumerationPtr(nodemap.GetNode('TriggerSource'))
#     if not PySpin.IsReadable(node_trigger_source) or not PySpin.IsWritable(node_trigger_source):
#         print('Unable to get trigger source (node retrieval). Aborting...')
#         return False

#     if CHOSEN_TRIGGER == TriggerType.SOFTWARE:
#         node_trigger_source_software = node_trigger_source.GetEntryByName('Software')
#         if not PySpin.IsReadable(node_trigger_source_software):
#             print('Unable to get trigger source (enum entry retrieval). Aborting...')
#             return False
#         node_trigger_source.SetIntValue(node_trigger_source_software.GetValue())
#         print('Trigger source set to software...')

#     elif CHOSEN_TRIGGER == TriggerType.HARDWARE:
#         node_trigger_source_hardware = node_trigger_source.GetEntryByName('Line0')
#         if not PySpin.IsReadable(node_trigger_source_hardware):
#             print('Unable to get trigger source (enum entry retrieval). Aborting...')
#             return False
#         node_trigger_source.SetIntValue(node_trigger_source_hardware.GetValue())
#         print('Trigger source set to hardware...')

#     # Turn trigger mode on
#     # Once the appropriate trigger source has been set, turn trigger mode
#     # on in order to retrieve images using the trigger.
#     node_trigger_mode_on = node_trigger_mode.GetEntryByName('On')
#     if not PySpin.IsReadable(node_trigger_mode_on):
#         print('Unable to enable trigger mode (enum entry retrieval). Aborting...')
#         return False

#     node_trigger_mode.SetIntValue(node_trigger_mode_on.GetValue())
#     print('Trigger mode turned back on...')

#     # except PySpin.SpinnakerException as ex:
#     #     print('Error: %s' % ex)
#     #     return False

#     return result