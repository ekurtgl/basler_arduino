import os
import time
import cv2
from pynput import keyboard
from threading import Thread
from queue import LifoQueue, Queue
import threading
from concurrent.futures import ThreadPoolExecutor

tp = ThreadPoolExecutor(50)  # max 10 threads

def threaded(fn):
    def wrapper(*args, **kwargs):
        return tp.submit(fn, *args, **kwargs)  # returns Future object
    return wrapper

def non_blocking_wait(delay=1):
    time.sleep(delay / 1000.0)
    return -1  # Simulate "no key pressed"

class DisplayManager:
    """Centralized display manager for multiple camera streams"""
    def __init__(self):
        self.displays = {}
        self.stopped = False
        self.display_thread = None
        self.display_lock = threading.Lock()
        # cv2.setNumThreads(1)

        # prediction preview params
        self.circle_radius = 5
        self.thickness = -1  # fill the circle
        self.colors = [(255, 0, 0), (0, 255, 0), (33, 222, 255), (0, 0, 255)] # BGR
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.pos = (50, 50)
        self.fontScale = 1
        # self.fontcolor = (255, 255, 255) # white
        self.fontcolor = (255, 0, 0) # blue
        self.fontthickness = 2
        
    def add_display(self, name, width=500, height=500, pred_preview_button=None):
        """Add a new display for a camera stream"""
        if name not in self.displays:
            self.displays[name] = {
                'queue': LifoQueue(maxsize=5),
                'window_size': (width, height),
                'frame_count': 0,
                'last_time': time.perf_counter(),
                'pred_preview_button': pred_preview_button
            }
            # cv2.startWindowThread()
            # cv2.namedWindow(name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
            # cv2.namedWindow(name, cv2.WINDOW_NORMAL)
            # cv2.resizeWindow(name, width, height)
    
    def update_frame(self, name, frame):
        """Update frame for a specific display"""
        if name not in self.displays.keys() or frame is None:
            print(f'Display Err: {name} not in displays OR frame is None.')
            return
            
        try:
            self.displays[name]['queue'].put_nowait(frame)
            # print(f'{name}: put new frame')
        except Exception as e:
            # If queue is full, drop the oldest frame
            try:
                self.displays[name]['queue'].get_nowait()
                self.displays[name]['queue'].put_nowait(frame)
                # print(f'{name}: put new frame2')
            except Exception as nested_e:
                print(f'Display Err2: {str(nested_e)}')
            
    def start(self):
        """Start the display thread"""
        # self.display_loop()
        if self.display_thread is None:
            self.display_thread = threading.Thread(target=self.display_loop, daemon=True)
            self.display_thread.start()
            print('Display thread started.')
        else:
            print('Display thread already running.')
        
    def stop(self, window_name=None):
        """Stop all displays"""
        if window_name is None:
            self.stopped = True
            cv2.destroyAllWindows()
            if self.display_thread is not None:
                self.display_thread.join(timeout=1.0)
                self.display_thread = None
        else:
            cv2.destroyWindow(window_name)
    
    # @threaded
    def display_loop(self):
        """Main display loop"""
        cnt = 0

        while not self.stopped:
            # print(f'cnt: {cnt}')
            cnt += 1
            # for name, display in self.displays.items():
            for name, display in self.displays.items():
                try:
                    # print(f'name: {name}, display: {display}')

                    if display['queue'].empty():
                        # print(f'{name}: empty q')
                        continue

                    # Try to get a frame with a short timeout
                    frame = display['queue'].get()
                    
                    if frame is None:
                        # print(f'{name}: None frame')
                        continue

                    if display['frame_count'] == 0:
                        print(f'Creating display window for: {name}')
                        # cv2.startWindowThread()
                        cv2.namedWindow(name, cv2.WINDOW_NORMAL)
                        cv2.resizeWindow(name, 500, 500)

                    # print(f'frame: {frame.shape}')
                    if len(frame.shape) == 2:
                        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                    
                    # Calculate and display FPS
                    current_time = time.perf_counter()
                    # fps = 1.0 / (current_time - self.displays[name]['last_time'])
                    self.displays[name]['last_time'] = current_time                    
                    frame = cv2.putText(frame, f'Frame: {display["frame_count"]}', self.pos, self.font, # , FPS: {fps:.1f}
                                        self.fontScale, self.fontcolor, self.fontthickness, cv2.LINE_AA)
                    # Short lock only for imshow
                    with self.display_lock:
                        try:
                            cv2.imshow(name, frame)
                            if cv2.waitKey(1) == ord("q"):
                                self.stopped = True
                                break
                        except Exception as e:
                            print(f"Error displaying frame for {name}: {e}")
                            continue

                    self.displays[name]['frame_count'] += 1
                    
                except Exception as e:
                    print(f"Display error in {name}: {str(e)}")
                    continue
                    

class VideoShow2:
    def __init__(self, name, show_pred=False, frame=None, preview_button='q', 
                 pred_preview_button='p', prev_width=500, prev_height=500, 
                 display_manager=None):
        self.name = name
        self.show_pred = show_pred
        self.stopped = False
        self.n_frame = 0
        self.pred_result = None
        self.pred_preview_button = pred_preview_button
        self.preview_button = preview_button

        self.listener = keyboard.Listener(on_press=self.on_key_event)
        self.listener.start()
        
        # Use provided display manager or create new one
        self.display_manager = display_manager
        if self.display_manager is None:
            self.display_manager = DisplayManager()
            
        self.display_manager.add_display(name, prev_width, prev_height, pred_preview_button)
        
    def start(self):
        if self.display_manager.display_thread is None:
            self.display_manager.start()
        
    def update(self, frame):
        if not self.stopped:
            if self.pred_result is not None and self.show_pred:
                for target_number, target in enumerate(self.pred_result):
                    for key_point in target:
                        frame = cv2.circle(frame, (key_point[1], key_point[0]), self.display_manager.circle_radius,
                                            self.display_manager.colors[target_number], self.display_manager.thickness)

            self.display_manager.update_frame(self.name, frame)
            self.n_frame += 1
    
    @threaded
    def on_key_event(self, event):
        if event.char == self.pred_preview_button:  # Check if the pressed key is pred_preview_button
            print("You toggled keypoint preview!")
            self.show_pred = not self.show_pred
        if event.char == self.preview_button:  # Check if the pressed key is preview_button
            print("You closed the preview!")
            self.stopped = True
            self.display_manager.stop(self.name)

    def stop(self):
        self.stopped = True
        self.display_manager.stop()


class VideoShow:
    """
    Class that continuously shows a frame using a dedicated thread.
    """

    def __init__(self, name, show_pred=False, frame=None, preview_button='q', pred_preview_button='p',
                 prev_width=500, prev_height=500, display_lock=None):
        self.frame = frame
        self.name = name
        self.show_pred = show_pred
        self.pred_preview_button = pred_preview_button
        self.preview_button = preview_button
        self.prev_width = prev_width
        self.prev_height = prev_height
        self.display_lock = display_lock
        self.pred_result = None
        self.stopped = False
        self.n_frame = 0

        # prediction preview params
        self.circle_radius = 5
        self.thickness = -1  # fill the circle
        self.colors = [(255, 0, 0), (0, 255, 0), (33, 222, 255), (0, 0, 255)] # BGR
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.pos = (50, 50)
        self.fontScale = 1
        # self.fontcolor = (255, 255, 255) # white
        self.fontcolor = (255, 0, 0) # blue
        self.fontthickness = 2

        # self.queue = LifoQueue(maxsize=2)
        self.queue = Queue(maxsize=2)
        self.queue.put(frame)
        self.lock = threading.Lock()
        self.listener = keyboard.Listener(on_press=self.on_key_event)
        self.listener.start()
        # cv2.setNumThreads(1)
        self.preview_thread = Thread(target=self.preview_worker, daemon=True)

    def start(self):
        # self.show()
        self.preview_thread.start()

    
    @threaded
    def on_key_event(self, event):
        if event.char == self.pred_preview_button:  # Check if the pressed key is 'p'
            print("You toggled keypoint preview!")
            self.show_pred = not self.show_pred
        if event.char == self.preview_button:  # Check if the pressed key is 'p'
            print("You closed the preview!")
            self.stopped = True
    
    def preview_worker(self):

        cv2.namedWindow(self.name, cv2.WINDOW_NORMAL) 
        cv2.resizeWindow(self.name, self.prev_width, self.prev_height) 
        while not self.stopped:
            if self.queue.empty():
                continue
            # self.frame = self.queue.get_nowait()
            self.frame = self.queue.get(timeout=0.1)
            if self.frame is None:
                continue
            
            if len(self.frame.shape) == 2:
                self.frame = cv2.cvtColor(self.frame, cv2.COLOR_GRAY2BGR) 
            if self.show_pred:
                for target_number, target in enumerate(self.pred_result):
                    for key_point in target:
                        self.frame = cv2.circle(self.frame, (key_point[1], key_point[0]), self.circle_radius, self.colors[target_number], self.thickness)
            
            self.frame = cv2.putText(self.frame, f'Frame: {self.n_frame}', self.pos, self.font, 
                                    self.fontScale, self.fontcolor, self.fontthickness, cv2.LINE_AA)
            
            if self.display_lock is not None:
                with self.display_lock:
                    cv2.imshow(self.name, self.frame)

                    if cv2.waitKey(1) == ord("q"):
                        self.stopped = True
            else:
                cv2.imshow(self.name, self.frame)
                
                if cv2.waitKey(1) == ord("q"):
                    self.stopped = True
            
            # print(f'{self.name}: frame: {self.frame.shape}')
        cv2.destroyWindow(self.name)

    @threaded
    def show(self):
        # with self.lock:
            # os.sched_setaffinity(0, [1, 2, 3, 4])
        cv2.namedWindow(self.name, cv2.WINDOW_NORMAL) 
        cv2.resizeWindow(self.name, self.prev_width, self.prev_height) 
        while not self.stopped:
            # print(f'q: {self.queue.qsize()}') 
            # if self.queue.empty():
            #     print('here3')
            #     continue
            # else:
            #     print('here2')
            #     self.frame = self.queue.get()
            #     print(f'p_frame: {self.frame}')

            self.frame = self.queue.get()
            if self.frame is None:
                continue

            if len(self.frame.shape) == 2:
                self.frame = cv2.cvtColor(self.frame, cv2.COLOR_GRAY2BGR) 
            if self.show_pred:
                for target_number, target in enumerate(self.pred_result):
                    for key_point in target:
                        self.frame = cv2.circle(self.frame, (key_point[1], key_point[0]), self.circle_radius, self.colors[target_number], self.thickness)
            
            self.frame = cv2.putText(self.frame, f'Frame: {self.n_frame}', self.pos, self.font, 
                                    self.fontScale, self.fontcolor, self.fontthickness, cv2.LINE_AA)
            
            if self.display_lock is not None:
                with self.display_lock:
                    cv2.imshow(self.name, self.frame)

                    if cv2.waitKey(1) == ord("q"):
                        self.stopped = True
            else:
                cv2.imshow(self.name, self.frame)
                
                if cv2.waitKey(1) == ord("q"):
                    self.stopped = True
                
        cv2.destroyWindow(self.name)

    def stop(self):
        self.stopped = True