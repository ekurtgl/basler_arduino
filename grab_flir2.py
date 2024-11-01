import PySpin
import cv2
import sys
import time
from utils.flir import print_device_info, configure_custom_image_settings


# Number of images to be grabbed.
countOfImagesToGrab = 120
cam_id = 0
# The exit code of the sample application.
exitCode = 0

# Setup the system and camera
system = PySpin.System.GetInstance()
version = system.GetLibraryVersion()
print('Library version: %d.%d.%d.%d' % (version.major, version.minor, version.type, version.build))
cam_list = system.GetCameras()
cam = cam_list[cam_id]
nodemap_tldevice = cam.GetTLDeviceNodeMap()

# cam.UserSetSelector.SetValue(PySpin.UserSetSelector_Default)
# cam.UserSetSelector.SetValue(PySpin.UserSetSelector_UserSet0)
# cam.UserSetSave.Execute()

cam.Init()
nodemap = cam.GetNodeMap()

cam.UserSetSelector.SetValue(PySpin.UserSetSelector_Default)
cam.UserSetLoad.Execute()

############## reset
# reset_node = PySpin.CCommandPtr(nodemap.GetNode('DeviceReset'))
# reset_node.Execute()
# time.sleep(2)

# # cam.DeInit()
# cam_list.Clear()   # Clear the camera list
# system.ReleaseInstance()  # Release the system instance
# print("Camera disconnected.")

# system = PySpin.System.GetInstance()
# cam_list = system.GetCameras()
# cam = cam_list[0]
# cam.Init()
# nodemap_tldevice = cam.GetTLDeviceNodeMap()
# nodemap = cam.GetNodeMap()
# print("Camera reconnected.")

print_device_info(cam)
        
device_serial_number = ''
node_device_serial_number = PySpin.CStringPtr(nodemap_tldevice.GetNode('DeviceSerialNumber'))
if PySpin.IsReadable(node_device_serial_number):
    device_serial_number = node_device_serial_number.GetValue()
    print('Device serial number retrieved as %s...' % device_serial_number)


node_acquisition_mode = PySpin.CEnumerationPtr(nodemap.GetNode('AcquisitionMode'))
if not PySpin.IsReadable(node_acquisition_mode) or not PySpin.IsWritable(node_acquisition_mode):
    print('Unable to set acquisition mode to continuous (enum retrieval). Aborting...')

# Retrieve entry node from enumeration node
node_acquisition_mode_continuous = node_acquisition_mode.GetEntryByName('Continuous')
if not PySpin.IsReadable(node_acquisition_mode_continuous):
    print('Unable to set acquisition mode to continuous (entry retrieval). Aborting...')

# Retrieve integer value from entry node
acquisition_mode_continuous = node_acquisition_mode_continuous.GetValue()

# Set integer value from entry node as new value of enumeration node
node_acquisition_mode.SetIntValue(acquisition_mode_continuous)
print('Acquisition mode set to continuous...')

# configure_custom_image_settings(cam)


# disable auto frame rate
node_frame_rate_auto = PySpin.CEnumerationPtr(nodemap.GetNode("AcquisitionFrameRateAuto"))
node_frame_rate_auto_off = node_frame_rate_auto.GetEntryByName("Off")
frame_rate_auto_off = node_frame_rate_auto_off.GetValue()
node_frame_rate_auto.SetIntValue(frame_rate_auto_off)


node_frame_rate_enable = PySpin.CBooleanPtr(nodemap.GetNode("AcquisitionFrameRateEnabled"))
node_frame_rate_enable.SetValue(True)

# fps = cam.AcquisitionFrameRate.GetValue()
# print(f'fps: {fps}')

# is_wrtable = PySpin.IsWritable(cam.AcquisitionFrameRate)
des_fps = 40
des_width = 1280
des_height = 1258

cam.AcquisitionMode.SetIntValue(PySpin.AcquisitionMode_Continuous)

cam.AcquisitionFrameRate.SetValue(des_fps)
cam.Width.SetValue(des_width)
cam.Height.SetValue(des_height)

width = cam.Width.GetValue()
height = cam.Height.GetValue()
fps = cam.AcquisitionFrameRate.GetValue()


# print(dir(cam))

############## for hw trigger
node_single_frame = PySpin.CEnumerationPtr(nodemap.GetNode("SingleFrameAcquisitionMode"))
single_frame_enable = node_single_frame.GetEntryByName("Triggered").GetValue()
node_single_frame.SetIntValue(single_frame_enable)



# print(f'width: {width}, height: {height}, fps: {fps}')

cam.BeginAcquisition()
print('Acquiring images...')

cv2.namedWindow("flir cam", cv2.WINDOW_NORMAL) 
cv2.resizeWindow("flir cam", 500, 300) 

start_t = time.perf_counter()
for i in range(countOfImagesToGrab):
    try:
        image_result = cam.GetNextImage(1000)

        #  Ensure image completion
        if image_result.IsIncomplete():
            print('Image incomplete with image status %d ...' % image_result.GetImageStatus())
        else:
            frame = image_result.GetNDArray()

        image_result.Release()

        cv2.imshow('flir cam', frame)
        k = cv2.waitKey(1)
        # if i % 30 == 0:
            # print(f'width: {width}, height: {height}, fps: {fps}')

        if k in [27, ord('q')]:
            break

    except PySpin.SpinnakerException as ex:
        print('Error: %s' % ex)

cam.EndAcquisition()

print(f'elapsed time: {time.perf_counter() - start_t}')

cam.DeInit()
cam_list.Clear()
system.ReleaseInstance()
cv2.destroyAllWindows()
