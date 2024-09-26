import json
import time
from utils.helpers import str_to_bool
from concurrent.futures import ThreadPoolExecutor


tp = ThreadPoolExecutor(10)  # max 10 threads

def threaded(fn):
    def wrapper(*args, **kwargs):
        return tp.submit(fn, *args, **kwargs)  # returns Future object
    return wrapper


class Stimulator():

    def __init__(self, args, arduino, cam, logger, save_path=None) -> None:
        self.args = args
        self.arduino = arduino
        self.cam = cam
        self.save_path = save_path
        self.monitor = False
        self.stimulation_status = False
        self.logger = logger

        self.decode_stimulation()

        if sum(self.block_durations) * self.cam['options']['AcquisitionFrameRate'] != int(args.n_total_frames):
                raise ValueError('Inconsistent number of frames between the args and stimulation.')

    def decode_stimulation(self):

        with open(self.args.stimulation_path, 'r') as file:
            stimulation_cfg = json.load(file)

        if str_to_bool(self.args.save) and self.save_path is not None:
            with open(self.save_path, 'w') as file:
                json.dump(stimulation_cfg, file)
        
        self.block_durations = []  # sec
        self.stimulation_turnOn_times_global = []  # sec
        self.stimulation_durations = []  # ms
        self.pulse_intervals = []  # ms
        self.pulse_dutyCycles = []  # percent
        
        global_offset = 0  # sec
        stimulation_end_time = None

        for block_number in stimulation_cfg.keys():
            cur_block = stimulation_cfg[block_number]
            self.block_durations.append(int(cur_block["duration_sec"]))

            if cur_block['stimulation'] not in ['1', 'True', 'true']:
                global_offset += self.block_durations[-1]
                continue
            
            assert len(cur_block["stimulation_turnOn_times_sec"]) != 0
            assert len(cur_block["stimulation_turnOn_times_sec"]) == len(cur_block["stimulation_durations_ms"])
            assert len(cur_block["stimulation_turnOn_times_sec"]) == len(cur_block["pulse_ontime_ms"])
            assert len(cur_block["stimulation_turnOn_times_sec"]) == len(cur_block["pulse_offtime_ms"])

            for i, local_on_time in enumerate(cur_block["stimulation_turnOn_times_sec"]):
                self.stimulation_turnOn_times_global.append(int(local_on_time) + global_offset)
                if stimulation_end_time is not None:
                    if self.stimulation_turnOn_times_global[-1] < stimulation_end_time:
                        raise ValueError("Conflicting stimulation start/end times.")
                    
                self.stimulation_durations.append(int(cur_block["stimulation_durations_ms"][i]))
                stimulation_end_time = self.stimulation_turnOn_times_global[-1] + (self.stimulation_durations[-1] / 1000)
                self.pulse_intervals.append((int(cur_block["pulse_ontime_ms"][i]) + int(cur_block["pulse_offtime_ms"][i])))
                self.pulse_dutyCycles.append(round(int(cur_block["pulse_ontime_ms"][i]) /
                                        (int(cur_block["pulse_ontime_ms"][i]) + int(cur_block["pulse_offtime_ms"][i])) * 100))
            
            global_offset += int(cur_block["duration_sec"])
    
    def print_params(self):
        self.logger.info(f'block_durations: {self.block_durations}')
        self.logger.info(f'stimulation_turnOn_times_global: {self.stimulation_turnOn_times_global}')
        self.logger.info(f'stimulation_durations: {self.stimulation_durations}')
        self.logger.info(f'pulse_intervals: {self.pulse_intervals}')
        self.logger.info(f'pulse_dutyCycles: {self.pulse_dutyCycles}\n')
        # print(f'block_durations: {self.block_durations}')
        # print(f'stimulation_turnOn_times_global: {self.stimulation_turnOn_times_global}')
        # print(f'stimulation_durations: {self.stimulation_durations}')
        # print(f'pulse_intervals: {self.pulse_intervals}')
        # print(f'pulse_dutyCycles: {self.pulse_dutyCycles}\n')
    
    def send_stim_config(self):
        if self.arduino is None:
            raise ValueError('Arduino is not set as the trigger source.')
        
        stim_profiles = [f'{self.stimulation_turnOn_times_global[i]}-{self.stimulation_durations[i]}-' + 
                         f'{self.pulse_intervals[i]}-{self.pulse_dutyCycles[i]}' for i in range(len(self.stimulation_turnOn_times_global))]
        cmd = 'D,' + ','.join(stim_profiles) + '\n'
        self.arduino.arduino.write(cmd.encode())
        self.logger.info("***Sent stimulation config cmd to Arduino: {} ***".format(cmd))
        # print("***Sent stimulation config cmd to Arduino: {} ***".format(cmd))
    
    def send_stim_trigger(self):
        cmd = 'T\n'
        self.arduino.arduino.write(cmd.encode())
        self.logger.info("***Sent stimulation trigger cmd to Arduino: {} ***".format(cmd))
        # print("***Sent stimulation trigger cmd to Arduino: {} ***".format(cmd))

    # @threaded
    # def start_monitoring(self):
    #     if self.arduino is None:
    #         raise ValueError('Arduino is None, can''t stimulate.')
        
    #     while self.monitor:
    #         if time.perf_counter() - self.start_t > self.stimulation_turnOn_times_global[0]:
    #             cmd = "Re,{},{}\r\n".format(self.pulse_intervals[0], self.pulse_dutyCycles[0])
    #             self.arduino.arduino.write(cmd.encode())
    #             # print(f'\nStimulation start time: {round(time.perf_counter() - self.start_t, 2)} sec.')
    #             print("***Sent stimulation start cmd to Arduino: {} ***".format(cmd))
    #             self.stimulation_turnOn_times_global.pop(0)
    #             self.pulse_intervals.pop(0)
    #             self.pulse_dutyCycles.pop(0)
    #             self.stimulation_status = True
            
    #         if self.stimulation_status:
    #             if time.perf_counter() - self.start_t > (self.stimulation_durations[0] / 1000):
    #                 cmd = "V\r\n"
    #                 self.arduino.arduino.write(cmd.encode())
    #                 print(f'Stimulation stop time: {round(time.perf_counter() - self.start_t, 2)} sec.')
    #                 print("***Sent stimulation stop cmd to Arduino: {} ***".format(cmd))
    #                 self.stimulation_durations.pop(0)
    #                 self.stimulation_status = False

        

        

