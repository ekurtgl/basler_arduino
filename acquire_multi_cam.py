import os
import time
import yaml
import json
import pprint
import logging
import argparse
import multiprocessing as mp
from datetime import datetime
from utils.basler import Basler
from utils.flir import FLIR
from utils.arduino import Arduino
from utils.helpers import str_to_bool
from utils.stimulation import Stimulator
from concurrent.futures import ThreadPoolExecutor


tp = ThreadPoolExecutor(10)  # max 10 threads

def threaded(fn):
    def wrapper(*args, **kwargs):
        return tp.submit(fn, *args, **kwargs)  # returns Future object
    return wrapper

grab_start_t = None

@threaded
def initialize_and_loop(tuple_list_item, logger, report_period=10): #config, camname, cam, args, experiment, start_t): #, arduino):
    global grab_start_t
    config, camname, cam, args, experiment, start_t, trigger_with_arduino, arduino = tuple_list_item

    if trigger_with_arduino and arduino is None:
        raise ValueError('Trigger with Arduino is but not initialized.')
    
    acquisition_fps=cam['options']['AcquisitionFrameRate']
    videowrite_fps = acquisition_fps if args.videowrite_fps is None else args.videowrite_fps
    args.videowrite_fps = videowrite_fps

    if cam['type'] == 'Realsense':
        raise NotImplementedError
    elif cam['type'] == 'FLIR':
        device = FLIR(args, cam, camname, experiment, config, start_t, logger, cam_id=0)
    elif cam['type'] == 'Basler':
        device = Basler(args, cam, camname, experiment, config, start_t, logger, cam_id=0)
    else:
        raise ValueError('Invalid camera type: %s' % cam['type'])
        
    try:
        device.get_n_frames(args.n_total_frames, report_period=report_period)
        # future = device.get_n_frames(args.n_total_frames, report_period=report_period)
        
        grab_start_t = time.perf_counter()
        # future.result()
    except KeyboardInterrupt:
        logger.info(f"{camname}: Aborted in main")
    finally:
        device.close()
        logger.info(f"{camname}: Exited.")


    return f"{camname} done."

def main():
    parser = argparse.ArgumentParser(description='Multi-device acquisition in Python.')
    parser.add_argument('-n','--name', type=str, default='JB999',
        help='Base name for directories. Example: mouse ID')
    parser.add_argument('-c', '--config', type=str, default='config/config-basler_multi_cam.yaml', 
        help='Configuration for acquisition. Defines number of cameras, serial numbers, etc.')
    parser.add_argument('--model_path', default='', type=str, 
        help='Path to the prediction model')
    parser.add_argument('--stimulation_path', default='config/stimulation_config.json', type=str, # config/stimulation_config.json
        help='Path to the stimulation config file (.json)')
    parser.add_argument('-s', '--save', default="1", type=str, # action='store_true',
        help='Use this flag to save to disk. If not passed, will only view')
    parser.add_argument('--n_total_frames', default=840, type=int, # action='store_true',
        help='Total number of frames to be acquired if --acquisiton_mode == frames.')
    parser.add_argument('-t', '--trigger_with_arduino', default="1",
         type=str, help='Flag to use python software trigger (instead of arduino)')
    parser.add_argument('--port', default='/dev/ttyACM0', type=str,
         help='port for arduino (default: /dev/ttyACM0)')
    parser.add_argument('-a', '--acquisition_mode', default='frames', # action='store_true',
        help='Acquisition mode.')
    parser.add_argument('-w', '--videowrite_fps', default=30, type=float,
         help='Video save frame rate (default: acquisition rate)')
    # parser.add_argument('-p', '--preview', default='1',
    #     help='Show preview in opencv window')
    # parser.add_argument('--predict', default='1',
    #     help='Make detection inference from the trained model')
    # parser.add_argument('--preview_prediction', default='1',
    #     help='Show detections overlayed on preview in opencv window')
    
    # unused flags
    parser.add_argument('-v', '--verbose', default=False, action='store_true',
        help='Use this flag to print debugging commands.')
    parser.add_argument('--movie_format', default='opencv',
        choices=['hdf5','opencv', 'ffmpeg', 'directory'], type=str,
        help='Method to save files to movies. Dramatically affects performance and filesize')
    parser.add_argument('--metadata_format', default='hdf5',
        choices=['hdf5', 'txt', 'csv'], type=str,
        help='Metadata format for timestamps (default: hdf5)')
    parser.add_argument('-r', '--acquisition_fps', default=30, type=float,
         help='Acquisition frame rate (default: 30 Hz)')
    parser.add_argument('-d', '--experiment_duration', default=float('inf'), type=float,
         help='Experiment dur in minutes (default: inf.)')
    parser.add_argument('-f', '--nframes_per_file', default=108000, type=int,
         help='N frames per file (default: 108000, or 15min at 120Hz)')
    parser.add_argument('-N', '--nodemap_path', default=None,
         action='store', help='Path to nodemap (.txt)')

    args = parser.parse_args()

    log_level = logging.INFO
    logging.basicConfig(level=log_level)
    logger = logging.getLogger("logger")

    if os.path.isfile(args.config):
        with open(args.config) as f:
            config = yaml.load(f, Loader=yaml.SafeLoader)
    else:
        raise ValueError('Invalid config file: %s' %args.config)

    trigger_with_arduino = str_to_bool(args.trigger_with_arduino)
    # if trigger_with_arduino or len(config['cams'])>1:
    if trigger_with_arduino:
        arduino = Arduino(logger, port=args.port, baudrate=115200)
        arduino.initialize()
        time.sleep(0.5)
        arduino.continuous_listen = True
        arduino.listen()
    else:
        arduino = None

    # experiment = '%s_%s' % (time.strftime('%Y-%m-%d_%H%M%S', time.localtime()), args.name)
    experiment = datetime.now().strftime("%Y%m%d_%H_%M_%S_")  + args.name
    directory = os.path.join(config['savedir'], experiment)
    
    if str_to_bool(args.save):
        # update config to reflect runtime params
        args_dict = vars(args)
        config.update({'args': args_dict})
        if not os.path.isdir(directory):
            os.makedirs(directory)
            with open(os.path.join(directory, 'loaded_config_file.yaml'), 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        log_file = os.path.join(directory, 'logs.log')
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')    
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.info(f"Is Arduino: {trigger_with_arduino}")
    
    start_t = time.perf_counter()
    
    tuple_list=[]
    pwm_fps = config['recording_fps']
    for camname, cam in config['cams'].items():
        if not cam['use']:
            continue
        logger.info(f'camname: {camname} \n cam: {cam}')
        cam['options']['AcquisitionFrameRate'] = pwm_fps
        pprint.pprint(cam)
        # if cam['master']:
        #     if pwm_fps is not None:
        #         raise ValueError('More than one master device detected. Set one master device in the .yaml file.')
        #     pwm_fps = int(cam['options']['AcquisitionFrameRate'])

        tup = (config, camname, cam, args, experiment, start_t, trigger_with_arduino, arduino) #, serial_queue) #, arduino)
        tuple_list.append(tup)
    #     #p = mp.Process(target=initialize_and_loop, args=(tup,))
    #     #p.start()
    
    # if trigger_with_arduino:
    #     # if pwm_fps is None:
    #     #     raise ValueError('pwm_fps is not set. Set one master device in the .yaml file.')
    #     # cmd = "S,{}\r\n".format(pwm_fps)
    #     arduino.arduino.write(cmd.encode())
    #     logger.info("***Sent msg to Arduino: {} ***".format(cmd))
    #     time.sleep(0.5)

    futures = []

    for tup in tuple_list:
        if args.acquisition_mode == 'frames':
            future = initialize_and_loop(tup, logger, report_period=1)
            futures.append(future)

    if trigger_with_arduino:
        time.sleep(0.5)
        # if pwm_fps is None:
        #     raise ValueError('pwm_fps is not set. Set one master device in the .yaml file.')
        cmd = "S,{}\r\n".format(pwm_fps)
        arduino.arduino.write(cmd.encode())
        logger.info("***Sent msg to Arduino: {} ***".format(cmd))
        time.sleep(0.5)

    if args.stimulation_path != '':
        stimulator = Stimulator(args, arduino, cam, logger, os.path.join(directory, 'loaded_stimulation_config.json'))
        logger.info('\nStimulation parameters:')
        stimulator.print_params()
        stimulator.send_stim_config()
        time.sleep(0.1) # if stim doesn't work, sleep time may need to be adjusted based on computer's speed

    if args.stimulation_path != '':
        stimulator.send_stim_trigger()
        # time.sleep(0.1)
    
    for future in futures:
        future.result()
    
    if trigger_with_arduino:
        logger.info("Closing Arduino")
        arduino.arduino.write("Q\n".encode()) #b'Q\r\n')
        time.sleep(0.2)
        arduino.arduino.write("V\n".encode()) #b'Q\r\n')
        time.sleep(0.2)
        arduino.arduino.close()
        logger.info("Arduino is closed.")
    logger.info(f'Experiment is finished.')
        
if __name__=='__main__':
    # set_start_method("spawn")
    main()