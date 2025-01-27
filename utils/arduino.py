import sys
import time
import serial
from concurrent.futures import ThreadPoolExecutor


tp = ThreadPoolExecutor(10)  # max 10 threads

def threaded(fn):
    def wrapper(*args, **kwargs):
        return tp.submit(fn, *args, **kwargs)  # returns Future object
    return wrapper


class Arduino():
    def __init__(self, logger, port='/dev/ttyACM0', baudrate=115200, timeout=5) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.continuous_listen = False
        self.logger = logger
        
    def initialize(self):

        self.arduino = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
        time.sleep(1)
        sys.stdout.flush()
        self.logger.info(f"Arduino connected to the serial port: {self.port}")

    @threaded
    def listen(self):
        while self.continuous_listen:
            recv = self.arduino.readline().rstrip().decode('utf-8')
            # if recv[-1] == '\n':
            #     recv = recv[:-1]
            #     if recv == '':
            #         continue
            # if recv[-1] == '\n':
            #     recv = recv[:-1]
            #     if recv == '':
            #         continue
                
            self.logger.info("Arduino: {}".format(recv))
        
    def close(self):
        self.continuous_listen = False
        self.arduino.close()
    
