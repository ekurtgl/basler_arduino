import os
import cv2
from pynput import keyboard
from threading import Thread
import threading
from concurrent.futures import ThreadPoolExecutor

tp = ThreadPoolExecutor(50)  # max 10 threads

def threaded(fn):
    def wrapper(*args, **kwargs):
        return tp.submit(fn, *args, **kwargs)  # returns Future object
    return wrapper

class VideoShow:
    """
    Class that continuously shows a frame using a dedicated thread.
    """

    def __init__(self, name, show_pred=False, frame=None, preview_button='q', pred_preview_button='p',
                 prev_width=300, prev_height=300):
        self.frame = frame
        self.name = name
        self.show_pred = show_pred
        self.pred_preview_button = pred_preview_button
        self.preview_button = preview_button
        self.prev_width = prev_width
        self.prev_height = prev_height
        
        self.pred_result = None
        self.stopped = False
        self.n_frame = 0
        self.circle_radius = 5
        self.thickness = -1  # fill the circle
        self.colors = [(255, 0, 0), (0, 255, 0), (33, 222, 255), (0, 0, 255)] # BGR
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.pos = (50, 50)
        self.fontScale = 1
        # self.fontcolor = (255, 255, 255) # white
        self.fontcolor = (0, 0, 255) # blue
        self.fontthickness = 2

        self.lock = threading.Lock()
        self.listener = keyboard.Listener(on_press=self.on_key_event)
        self.listener.start()

    def start(self):
        self.show()
    
    @threaded
    def on_key_event(self, event):
        if event.char == self.pred_preview_button:  # Check if the pressed key is 'p'
            print("You toggled keypoint preview!")
            self.show_pred = not self.show_pred
        if event.char == self.preview_button:  # Check if the pressed key is 'p'
            print("You closed the preview!")
            self.stopped = True
            
    @threaded
    def show(self):
        # with self.lock:
            # os.sched_setaffinity(0, [1, 2, 3, 4])
        cv2.namedWindow(self.name, cv2.WINDOW_NORMAL) 
        cv2.resizeWindow(self.name, self.prev_width, self.prev_height) 
        while not self.stopped:
            if self.show_pred:
                for target_number, target in enumerate(self.pred_result):
                    for key_point in target:
                        self.frame = cv2.circle(self.frame, (key_point[1], key_point[0]), self.circle_radius, self.colors[target_number], self.thickness)
                self.frame = cv2.putText(self.frame, f'Frame: {self.n_frame}', self.pos, self.font, 
                                        self.fontScale, self.fontcolor, self.fontthickness, cv2.LINE_AA)
                cv2.imshow(self.name, self.frame)
            else:
                self.frame = cv2.putText(self.frame, f'Frame: {self.n_frame}', self.pos, self.font, 
                                        self.fontScale, self.fontcolor, self.fontthickness, cv2.LINE_AA)
                cv2.imshow(self.name, self.frame)
                
            if cv2.waitKey(1) == ord("q"):
                self.stopped = True
                
        cv2.destroyWindow(self.name)

    def stop(self):
        self.stopped = True