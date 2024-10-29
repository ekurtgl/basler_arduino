# import PySpin
import EasyPySpin
import cv2
import sys
import time

# Number of images to be grabbed.
countOfImagesToGrab = 120
cam_id = 0
# The exit code of the sample application.
exitCode = 0
start_t = time.perf_counter()

# try:
cap = EasyPySpin.VideoCapture(cam_id)

# cap.set_pyspin_value("AdcBitDepth", "Bit12")
cap.set_pyspin_value("PixelFormat", "Mono8")
cap.set_pyspin_value("Height", 1280)
cap.set_pyspin_value("Width", 1280)
cap.set_pyspin_value("frame_rate_auto", 'Off')
cap.set_pyspin_value("AcquisitionFrameRateEnable", True)
cap.set_pyspin_value("AcquisitionFrameRate", 70)
# cap.set_pyspin_value("Frame Rate", 120)
# fps = cap.set(cv2.CAP_PROP_FPS, 60)

width  = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
# width = cap.get_pyspin_value("Width")
height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
fps = cap.get(cv2.CAP_PROP_FPS)

# cap.get_pyspin_value("GammaEnable")
name = cap.get_pyspin_value("DeviceModelName")
fps = cap.get_pyspin_value("AcquisitionFrameRate")
print(f'name: {name}, width: {width}, height: {height}, fps: {fps}')

for i in range(countOfImagesToGrab):
    ret, frame = cap.read()
    cv2.imshow('flir cam', frame)
    k = cv2.waitKey(1)
    if i % 30 == 0:
        print(f'name: {name}, width: {width}, height: {height}, fps: {fps}')

    if k in [27, ord('q')]:
        break

print(f'elapsed time: {time.perf_counter() - start_t}')

cap.release()
