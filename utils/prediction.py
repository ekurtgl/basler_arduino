import numpy as np
from threading import Thread

class Predictor():
    def __init__(self, model_path='', save_dir=None):
        self.n_frame = 0
        self.prev_n_frame = 0
        self.frame = None
        self.pred_result = None
        self.save_dir = save_dir
        self.model_path = model_path
        self.stopped = False

    def start(self):
        if self.model_path is None:
            print('model_path is not provided, drawing random predictions')
        else:
            self.load_model()
        self.pred_result = np.random.random(size=(3, 5, 2), dtype=np.int) * 300
        Thread(target=self.predict, args=()).start()
        return self
        
        
    def predict(self):
        while not self.stopped:
            # make prediction for only new frames
            if self.n_frame != self.prev_n_frame:
                if self.model_path == '':
                    # random 2D coordinates between [0-300]
                    self.pred_result = np.random.random(size=(3, 5, 2), dtype=np.int) * 300
                else:
                    raise NotImplementedError
                
                self.prev_n_frame = self.n_frame
        
    def load_model(self):
        # load model
        pass

    def save_predictions(self):
        pass



