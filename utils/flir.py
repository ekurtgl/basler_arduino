import os
import cv2
import json
import time
import PySpin
# import EasyPySpin
import numpy as np
from datetime import datetime
from .preview import VideoShow
from .prediction import Predictor
from .helpers import str_to_bool
from queue import LifoQueue, Queue
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
        
        self.vid_cod = cv2.VideoWriter_fourcc('m', 'p', '4', 'v')
        self.nframes = 0
        self.logger = logger
        self.logger.info('Connecting to the FLIR camera...')

        # Setup the system and camera
        # system = PySpin.System.GetInstance()
        # cam_list = system.GetCameras()
        # self.camera = cam_list[cam_id]
        # self.camera.Init()

        self.camera = EasyPySpin.VideoCapture(cam_id)

        self.update_settings()

        if self.predict:
            self.predictor = Predictor(self.logger, self.args.model_path)
        
        if self.preview:
            self.vid_show = VideoShow(self.name, self.preview_predict, pred_preview_button='f')
            self.vid_show.frame = np.zeros((self.cam['options']['Height'], self.cam['options']['Width']), dtype=np.uint8)
            if self.vid_show.show_pred:
                self.vid_show.pred_result = self.predictor.pred_result
            self.vid_show.start()

        if self.save:
            self.init_video_writer()


    def update_settings(self):
        self.camera.set_pyspin_value("AcquisitionMode", self.cam['options']['AcquisitionMode'])
        self.camera.set_pyspin_value("AcquisitionFrameRateEnable", self.cam['options']['AcquisitionFrameRateEnable'])
        self.camera.set_pyspin_value("AcquisitionFrameRate", self.cam['options']['AcquisitionFrameRate'])
        self.camera.set_pyspin_value("PixelFormat", self.cam['options']['PixelFormat'])
        self.camera.set_pyspin_value("Height", self.cam['options']['Height'])
        self.camera.set_pyspin_value("Width", self.cam['options']['Width'])
        self.camera.set_pyspin_value("FrameRateAuto", self.cam['options']['FrameRateAuto'])
        
        self.name = self.camera.get_pyspin_value("DeviceModelName")
        # self.fps = self.camera.get_pyspin_value("AcquisitionResultingFrameRate")
        self.logger.info(f'FLIR camera {self.cam_id} settings updated.')
    
    def close(self):
        self.camera.release()
    
    def init_video_writer(self):
        self.writer_obj = cv2.VideoWriter(os.path.join(self.config['savedir'], self.experiment, f"video_flir_{self.cam_id}.mp4"), self.vid_cod, self.args.videowrite_fps,
                                    (self.cam['options']['Width'], self.cam['options']['Height']))
        self.write_frames = True
        self.frame_write_queue = Queue()
        self.frame_writer()
    
    @threaded
    def frame_writer(self):
        while self.write_frames:
            if self.frame_write_queue.empty():
                continue
            self.writer_obj.write(self.frame_write_queue.get_nowait())

    def save_vid_metadata(self, metadata=None):
        if metadata is not None:
            with open(os.path.join(self.config['savedir'], self.experiment, f'metadata_flir_{self.cam_id}.json'), 'w') as file:
                json.dump(metadata, file)
        self.writer_obj.release()


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

