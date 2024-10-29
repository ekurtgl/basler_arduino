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
start_t = time.perf_counter()

# Setup the system and camera
system = PySpin.System.GetInstance()
version = system.GetLibraryVersion()
print('Library version: %d.%d.%d.%d' % (version.major, version.minor, version.type, version.build))
cam_list = system.GetCameras()
cam = cam_list[cam_id]
nodemap_tldevice = cam.GetTLDeviceNodeMap()
sNodemap = cam.GetTLStreamNodeMap()

cam.Init()
nodemap = cam.GetNodeMap()

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

configure_custom_image_settings(cam)

# cam.FrameRateAuto.SetValue('Off')
# cam.AcquisitionFrameRate.SetValue(30)


print('Acquiring images...')
fps = cam.AcquisitionFrameRate.GetValue()
print(f'fps: {fps}')

is_wrtable = PySpin.IsWritable(cam.AcquisitionFrameRate)
des_fps = 30
des_width = 1280
des_height = 1258

cam.AcquisitionMode.SetIntValue(PySpin.AcquisitionMode_Continuous)
# cam.AcquisitionFrameRateEnable(True)
cam.AcquisitionFrameRate.SetValue(des_fps)
cam.Width.SetValue(des_width)
print(f'new fps: {cam.AcquisitionFrameRate.GetValue()}')

# print(dir(cam))


print(f'width: {cam.Width.GetValue()}, height: {cam.Height.GetValue()}, fps: {fps}')

cam.BeginAcquisition()
for i in range(countOfImagesToGrab):
    ret, frame = cap.read()
    cv2.imshow('flir cam', frame)
    k = cv2.waitKey(1)
    if i % 30 == 0:
        print(f'name: {name}, width: {width}, height: {height}, fps: {fps}')

    if k in [27, ord('q')]:
        break

print(f'elapsed time: {time.perf_counter() - start_t}')

cam.DeInit()
cam_list.Clear()
system.ReleaseInstance()