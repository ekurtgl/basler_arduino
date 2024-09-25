import json
import time
from utils.arduino import Arduino
from utils.helpers import str_to_bool
from utils.stimulation import Stimulator

def decode_stimulation():

    with open('config/stimulation_config.json', 'r') as file:
        stimulation_cfg = json.load(file)
    
    block_durations = []  # sec
    stimulation_turnOn_times_global = []  # sec
    stimulation_durations = []  # ms
    pulse_intervals = []  # ms
    pulse_dutyCycles = []  # percent
    
    global_offset = 0  # sec
    stimulation_end_time = None

    for block_number in stimulation_cfg.keys():
        cur_block = stimulation_cfg[block_number]
        block_durations.append(int(cur_block["duration_sec"]))

        if cur_block['stimulation'] not in ['1', 'True', 'true']:
            global_offset += block_durations[-1]
            continue
        
        assert len(cur_block["stimulation_turnOn_times_sec"]) != 0
        assert len(cur_block["stimulation_turnOn_times_sec"]) == len(cur_block["stimulation_durations_ms"])
        assert len(cur_block["stimulation_turnOn_times_sec"]) == len(cur_block["pulse_ontime_ms"])
        assert len(cur_block["stimulation_turnOn_times_sec"]) == len(cur_block["pulse_offtime_ms"])

        for i, local_on_time in enumerate(cur_block["stimulation_turnOn_times_sec"]):
            stimulation_turnOn_times_global.append(int(local_on_time) + global_offset)
            if stimulation_end_time is not None:
                if stimulation_turnOn_times_global[-1] < stimulation_end_time:
                    raise ValueError("Conflicting stimulation start/end times.")
                
            stimulation_durations.append(int(cur_block["stimulation_durations_ms"][i]))
            stimulation_end_time = stimulation_turnOn_times_global[-1] + (stimulation_durations[-1] / 1000)
            pulse_intervals.append((int(cur_block["pulse_ontime_ms"][i]) + int(cur_block["pulse_offtime_ms"][i])))
            pulse_dutyCycles.append(round(int(cur_block["pulse_ontime_ms"][i]) /
                                    (int(cur_block["pulse_ontime_ms"][i]) + int(cur_block["pulse_offtime_ms"][i])) * 100))
        
        global_offset += int(cur_block["duration_sec"])

    return (block_durations, stimulation_turnOn_times_global,
            stimulation_durations, pulse_intervals,
            pulse_dutyCycles)

arduino = Arduino(port='/dev/ttyACM0', baudrate=115200)
arduino.initialize()
time.sleep(0.5)

(block_durations, stimulation_turnOn_times_global,
            stimulation_durations, pulse_intervals,
            pulse_dutyCycles) = decode_stimulation()

print('\nStimulation parameters:')
print(f'block_durations: {block_durations}')
print(f'stimulation_turnOn_times_global: {stimulation_turnOn_times_global}')
print(f'stimulation_durations: {stimulation_durations}')
print(f'pulse_intervals: {pulse_intervals}')
print(f'pulse_dutyCycles: {pulse_dutyCycles}\n')

stim_profiles = [f'{stimulation_turnOn_times_global[i]}-{stimulation_durations[i]}-' + 
                    f'{pulse_intervals[i]}-{pulse_dutyCycles[i]}' for i in range(len(stimulation_turnOn_times_global))]
cmd = 'D,' + ','.join(stim_profiles) + '\n'
arduino.arduino.write(cmd.encode())
print("\n***Sent stimulation start cmd to Arduino: {} ***".format(cmd))
time.sleep(0.5)
arduino.continuous_listen = True
arduino.listen()
# start_t = time.perf_counter()

# while time.perf_counter() - start_t < 0.5:
#     recv = arduino.arduino.readline()
#     # print(recv)
#     print("Received msg from arduino: {}".format(recv.rstrip().decode('utf-8')))

cmd = 'T\n'
arduino.arduino.write(cmd.encode())
print("\n***Sent stimulation trigger cmd to Arduino: {} ***".format(cmd))
# time.sleep(0.5)

# recv = arduino.arduino.readline()
# # print(recv)
# print("Received msg from arduino: {}".format(recv.rstrip().decode('utf-8')))
time.sleep(sum(block_durations))
arduino.continuous_listen = False
arduino.arduino.close()
