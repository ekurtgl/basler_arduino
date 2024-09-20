import os
import time
import numpy as np
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

tp = ThreadPoolExecutor(5)  # max 10 threads

def threaded(fn):
    def wrapper(*args, **kwargs):
        return tp.submit(fn, *args, **kwargs)  # returns Future object
    return wrapper

class Predictor():
    def __init__(self, model_path='', save_dir=None):
        self.n_frame = 0
        self.prev_n_frame = 0
        self.frame = None
        self.pred_result = None
        self.save_dir = save_dir
        self.model_path = model_path
        self.stopped = False
        # self.get_random_prediction()
        self.pred_result = np.random.randint(50, 300, size=(3, 5, 2))

        if self.model_path == '':
            print('model_path is not provided, drawing random predictions')
        else:
            self.load_model()

    def start(self):        
        # Thread(target=self.predict, args=()).start()
        self.predict()
        return self
    
    @threaded
    def get_random_prediction(self):
        # self.pred_result = np.random.randint(100, 500, size=(3, 5, 2))
        centers = np.random.randint(100, 1000, size=(4, 2))
        pos = [[[center[0] - 40, center[1]], # head
                [center[0], center[1] + 20], # lwing
                [center[0], center[1] - 20], # rwing
                [center[0] + 40, center[1] + 15], # lleg
                [center[0] + 40, center[1] - 15]] # rleg
                for center in centers]
        self.pred_result = pos
        time.sleep(0.01)
        # self.pred_result = np.array([[[10, 20], [30, 40], [50, 60], [70, 80], [90, 100]],
        #                              [[200, 220], [210, 230], [240, 250], [250, 240], [270, 270]]])
    
    @threaded
    def predict(self):
        # os.sched_setaffinity(0, [5, 6, 7, 8])
        while not self.stopped:
            # make prediction for only new frames
            if self.n_frame != self.prev_n_frame:
                if self.model_path == '':
                    self.get_random_prediction()
                else:
                    raise NotImplementedError
                
                self.prev_n_frame = self.n_frame
        
    def load_model(self):
        # load model
        pass

    def save_predictions(self):
        pass
    
    def stop(self):
        self.stopped = True


