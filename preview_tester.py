import logging
from utils.preview import VideoShow, VideoShow2, DisplayManager
from utils.prediction import Predictor
import numpy as np
import time


name = 'flir_0'
name2 = 'basler'
predict = True

log_level = logging.INFO
logging.basicConfig(level=log_level)
logger = logging.getLogger("logger")

if predict:
    predictor = Predictor(logger, '')

display_manager = DisplayManager()
display_manager.start()

vid_show = VideoShow2(name=name, display_manager=display_manager, show_pred=predict, pred_preview_button='c')
vid_show2 = VideoShow2(name=name2, display_manager=display_manager, show_pred=predict, pred_preview_button='b')


for i in range(100):
    print(f'{i}. frame')
    frame = (np.random.rand(1280, 1280, 3) * 255).astype(np.uint8)
    frame2 = (np.random.rand(1280, 1280, 3) * 255).astype(np.uint8)
    vid_show.update(frame)
    vid_show2.update(frame2)

    predictor.frame = frame
    predictor.n_frame = i
    predictor.get_random_prediction()
    vid_show.pred_result = predictor.pred_result
    predictor.get_random_prediction()
    vid_show2.pred_result = predictor.pred_result

    # if not display_manager.displays[name]['queue'].full():
    #     display_manager.displays[name]['queue'].put_nowait(frame)
    time.sleep(0.05)













