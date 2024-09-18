import cv2
from threading import Thread

class VideoShow:
    """
    Class that continuously shows a frame using a dedicated thread.
    """

    def __init__(self, name, show_pred=False, frame=None):
        self.frame = frame
        self.name = name
        self.n_frame = 0
        self.stopped = False
        self.show_pred = show_pred
        self.pred_result = None
        self.circle_radius = 5
        self.thickness = -1  # fill the circle
        self.colors = ['r', 'b', 'g', 'y', 'm', 'c']
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.pos = (50, 50)
        self.fontScale = 1
        self.fontcolor = (255, 255, 255) # white
        self.fontthickness = 2

    def start(self):
        Thread(target=self.show, args=()).start()
        return self

    def show(self):
        while not self.stopped:
            if self.show_pred:
                for target_number, target in enumerate(self.pred_result):
                    for key_point in target:
                        self.frame = cv2.circle(self.frame, (key_point[0], key_point[1]), self.circle_radius, self.colors[target_number], self.thickness)
                self.frame = cv2.putText(self.frame, f'Frame: {self.n_frame}', self.pos, self.font, 
                                        self.fontScale, self.fontcolor, self.fontthickness, cv2.LINE_AA)
                cv2.imshow(self.name, self.frame)
            else:
                self.frame = cv2.putText(self.frame, f'Frame: {self.n_frame}', self.pos, self.font, 
                                        self.fontScale, self.fontcolor, self.fontthickness, cv2.LINE_AA)
                cv2.imshow(self.name, self.frame)
            # print(self.n_frame)
            if cv2.waitKey(1) == ord("q"):
                self.stopped = True

    def stop(self):
        self.stopped = True