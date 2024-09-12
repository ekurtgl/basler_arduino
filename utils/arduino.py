import sys
import time
import serial


class Arduino():
    def __init__(self, port='/dev/ttyACM0', baudrate=115200, timeout=5) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        
    def initialize(self):

        self.arduino = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
        time.sleep(1)
        sys.stdout.flush()
        print(f"Arduino connected to the serial port: {self.port}")
    
