import pypylon
from pypylon import pylon, genicam


class Basler():

    def __init__(self, max_cams=2, connect_retries=50) -> None:
        print('Searching for camera...')

        self.cameras = None
        # get transport layer factory
        self.tlFactory = pylon.TlFactory.GetInstance()

        # get the camera list 
        self.devices = self.tlFactory.EnumerateDevices()
        print('Connecting to cameras...')   

        # Create array of cameras
        n = 0
        while self.cameras is None and n < connect_retries:
            try:
                self.cameras = pylon.InstantCameraArray(min(len(self.devices), max_cams))
                l = self.cameras.GetSize()
                #pylon.TlFactory.GetInstance().CreateFirstDevice())
                print(f"Num. of cameras detected: {l}, cameras: {self.cameras}")
                #time.sleep(0.5)
                #camera.Open()
                #print("Bound to device:" % (camera.GetDeviceInfo().GetModelName()))

            except Exception as e:
                print('.')
                # time.sleep(0.1)
                # camera = None
                n += 1

    def init_cameras(self):
        for ix, cam in enumerate(self.cameras):
            cam.Attach(self.tlFactory.CreateDevice(self.devices[ix]))
            #camera.Open()
            print("Bound to device: %s" % (cam.GetDeviceInfo().GetModelName()))

        # open camera 
        self.cameras.Open()
        # store a unique number for each camera to identify the incoming images
        for idx, cam in enumerate(self.cameras):
            camera_serial = cam.DeviceInfo.GetSerialNumber()
            print(f"set context {idx} for camera {camera_serial}")
            cam.SetCameraContext(idx)
        print("Cameras successfully initialized!")
    

    