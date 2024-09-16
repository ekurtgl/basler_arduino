import os
import time
import yaml
import pprint
import argparse
import multiprocessing as mp
from datetime import datetime
from utils.basler import Basler
from utils.arduino import Arduino
from utils.helpers import str_to_bool

def main():
    parser = argparse.ArgumentParser(description='Multi-device acquisition in Python.')
    parser.add_argument('-n','--name', type=str, default='JB999',
        help='Base name for directories. Example: mouse ID')
    parser.add_argument('-c', '--config', type=str, default='config/config-basler2040.yaml', 
        help='Configuration for acquisition. Defines number of cameras, serial numbers, etc.')
    parser.add_argument('-p', '--preview', default='False', # action='store_true',
        help='Show preview in opencv window')
    parser.add_argument('-s', '--save', default="True", type=str, # action='store_true',
        help='Use this flag to save to disk. If not passed, will only view')
    parser.add_argument('-v', '--verbose', default=False, action='store_true',
        help='Use this flag to print debugging commands.')
    parser.add_argument('-a', '--acquisition_mode', default='frames', # action='store_true',
        help='Acquisition mode.')
    parser.add_argument('--n_total_frames', default=3, type=int, # action='store_true',
        help='Total number of frames to be acquired if --acquisiton_mode == frames.')
    parser.add_argument('--movie_format', default='opencv',
        choices=['hdf5','opencv', 'ffmpeg', 'directory'], type=str,
        help='Method to save files to movies. Dramatically affects performance and filesize')
    parser.add_argument('--metadata_format', default='hdf5',
        choices=['hdf5', 'txt', 'csv'], type=str,
        help='Metadata format for timestamps (default: hdf5)')
    parser.add_argument('--port', default='/dev/ttyACM0', type=str,
         help='port for arduino (default: /dev/ttyACM0)')
    parser.add_argument('-r', '--acquisition_fps', default=30, type=float,
         help='Acquisition frame rate (default: 30 Hz)')
    parser.add_argument('-w', '--videowrite_fps', default=30, type=float,
         help='Video save frame rate (default: acquisition rate)')
    parser.add_argument('-d', '--experiment_duration', default=float('inf'), type=float,
         help='Experiment dur in minutes (default: inf.)')
    parser.add_argument('-f', '--nframes_per_file', default=108000, type=int,
         help='N frames per file (default: 108000, or 15min at 120Hz)')
    parser.add_argument('-t', '--trigger_with_arduino', default="True",
         type=str,
         help='Flag to use python software trigger (instead of arduino)')
    parser.add_argument('-N', '--nodemap_path', default=None,
         action='store',
         help='Path to nodemap (.txt)')

    args = parser.parse_args()

    if os.path.isfile(args.config):
        with open(args.config) as f:
            config = yaml.load(f, Loader=yaml.SafeLoader)
    else:
        raise ValueError('Invalid config file: %s' %args.config)

    trigger_with_arduino = str_to_bool(args.trigger_with_arduino)
    print(f"Is Arduino: {trigger_with_arduino}")
    # if trigger_with_arduino or len(config['cams'])>1:
    if trigger_with_arduino:
        arduino = Arduino()
        arduino.initialize(port=args.port, baudrate=115200)

    # experiment = '%s_%s' % (time.strftime('%Y-%m-%d_%H%M%S', time.localtime()), args.name)
    experiment = datetime.now().strftime("%Y%m%d_%H_%M_%S_")  + args.name# microsec precision
    
    if str_to_bool(args.save):
        # update config to reflect runtime params
        args_dict = vars(args)
        config.update({'args': args_dict})
        directory = os.path.join(config['savedir'], experiment)
        if not os.path.isdir(directory):
            os.makedirs(directory)
            with open(os.path.join(directory, 'loaded_config_file.yaml'), 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    
    # start_t = time.perf_counter()
    # tuple_list=[]
    # for camname, cam in config['cams'].items():
    #     pprint.pprint(f'camname: {camname} \n cam: {cam}')
    #     tup = (config, camname, cam, args, experiment, start_t, trigger_with_arduino) #, serial_queue) #, arduino)
    #     #p = mp.Process(target=initialize_and_loop, args=(tup,))
    #     #p.start()
    #     tuple_list.append(tup)
    # tuple_list = (config, camname, cam, args, experiment, start_t, trigger_with_arduino)
    camname = list(config['cams'].keys())[0]
    cam = config['cams'][camname]
    pprint.pprint(f'camname: {camname} \n cam: {cam}')
    cam1 = Basler(args, cam, experiment, config, cam_id=0)
    
    if args.acquisition_mode == 'frames' and not trigger_with_arduino:
        frames = cam1.get_n_frames(args.n_total_frames)
        # print(f'frames: {len(frames)}')
        # frames.result()
        
    elif args.acquition_mode == 'duration':
        start_time = time.time()
        while time.time() < start_time:
            frames = cam1.get_n_frames(1)
        pass

if __name__=='__main__':
    # set_start_method("spawn")
    main()