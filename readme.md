# Project Description

This program live streams the frames of Basler acA2040-120um camera with additional options such as configuring the camera settings, exporting frames as a video, saving metadata of each frame, triggering camera from SW (pypylon) or HW (Arduino), making inference from a pretrained ML model, preview of the camera stream and model predictions.

The program utilizes threading capabilities of Python to run tasks concurrently without blocking each other.

# Installation 

### Software

1. Download and install [Basler Pylon SDK](https://www2.baslerweb.com/en/downloads/software-downloads/#type=pylonsoftware).
2. Download and install [FLIR Spinnaker SDK 4.0.0 (both GUI and Python SDK)](https://www.teledynevisionsolutions.com/support/support-center/software-firmware-downloads/iis/spinnaker-sdk-download/spinnaker-sdk--download-files/?pn=Spinnaker+SDK&vn=Spinnaker+SDK). Make sure the correct FFMPEG dependencies exist. I used [FFMPEG-4.4.5 "Rao"](https://www.ffmpeg.org/download.html#releases).

2. **[Optional for hardware trigger with Arduino]** Upload `utils/arduino_pwm_led/arduino_pwm_led.ino` file to the Arduino.

### Hardware

1. Connect Basler USB 3.0 and/or FLIR GS3-U3 to the computer.

Optional Steps for the hardware trigger:

2. Connect:
    - Pin 3 of Arduino with Pin 1 (Brown cable) of the Basler, and Pin 4 (Green cable) of the FLIR GS3-U3.
    - GND pin of Arduino with Pin 6 (White cable) of the Basler, and Pin 5 (Brown cable) of the FLIR GS3-U3.

3. Connect Pin 10 of Arduino with the stimulation's input ((+) for the external LED) line, and GND pin of Arduino with LED's (-) line.

4. Connect Arduino to the computer via USB.

### Set Arduino access rights

Do the following if using Arduino for the first time on Linux.

```bash
# navigate to rules.d directory
cd /etc/udev/rules.d
#create a new rule file
sudo touch my-newrule.rules
# open the file
sudo nano my-newrule.rules
# add the following
KERNEL=="ttyACM0", MODE="0666"
```
Restart the computer for the access rights to take effect.

### Requirements

You can create a new environment before installing the necessary dependencies.

`conda create -n <your_env_name> python=3.10`

Intall the dependencies via:

```bash
cd basler_arduino
pip install -r requirements.txt
```

OR 

`conda env create -f environment.yml -n <your_env_name>`


If some packages do not get installed, run this separately:
`pip install pyyaml pyserial pypylon pynput tqdm opencv-python`

# Configs

### Data Save Path

Change `savedir` under the [configuration file](config/config-basler_sw_trigger.yaml):

### Acquisition Mode

`--acquisition_mode` controls the acquisition mode, and is only implemented for `"frames"` for now.

### SW vs. HW Trigger

The cameras can be trigger via both SW or HW (Arduino). The relevant `--config` file should be provided for either case. For the HW trigger, `--trigger_with_arduino` should be set to one of the followings `['true', '1', 't', 'y', 'yes']`

`--n_total_frames` should be equal to the product of total duration of each blocks in [`stimulation_config.json`](config/stimulation_config.json) and the `AcquisitionFrameRate` parameter in the [camera config file](config/config-basler_hw_trigger.yaml).


### Stimulation

Stimulation should always be used in the HW trigger mode.

If `--stimulation_path` is `""`, no stimulation will be triggered.

`stimulation_config.json` contains the stimulation profiles with the following structure:

```json
"<block number>": {"duration_sec": "8", // duration of the block in sec
                    "stimulation": "1", // bool flag for whether stimulation exists
                    "stimulation_turnOn_times_sec": ["2", "4"], // list of local (within block) stimulation start times in sec
                    "stimulation_durations_ms": ["1000", "2000"], // list of stimulation durations in ms
                    "pulse_ontime_ms": ["50", "250"], // list of pulse on times in ms
                    "pulse_offtime_ms": ["50", "250"]}, // list of pulse off times in ms
```

# Running

You can run the main program `acquire_frames_stimulation.py` with the default arguments given in [`.vscode/launch.json`](.vscode/launch.json)

### Preview

You can toggle the prediction preview by pressing the `"P"` button on the keyboard during runtime.

# Hardware Troubleshoot

For GPIO coax cable color codes, refer [here](https://docs.baslerweb.com/basler-io-cable-hrs-6p-open-p?_gl=1*6p8gh3*_gcl_au*MTQyMTg2MzkwOC4xNzI2MDg5ODQ4).

Find Basler GPIO pins [here](https://docs.baslerweb.com/aca2040-120um)

### Arduino

If the Arduino IDE stalls with the following notification:

`Downloading index library_index.tar.bz2`

End arduino processes in the system monitor or kill their pids, and delete `/home/<username>/.arduinoIDE/arduino-cli.yaml` file.

# Software Troubleshoot

### Spinnaker

I needed to make a static build for the FFMPEG by following the commands:

```bash
# Navigate to the downloaded folder
cd ~/Downloads/ffmpeg-4.4.5

# Configure FFmpeg with Shared Libraries: Rebuild FFmpeg, enabling shared libraries
./configure --enable-shared --disable-static --enable-gpl --disable-x86asm

# Compile and Install
make -j$(nproc)
sudo make install

# make sure the .so files are present
ls /usr/local/lib | grep libav

# update library cache
sudo ldconfig
```

For the following error in SpinView:

```
Spinnaker system instance cannot be acquired. could not load producer.make sure the environemnt variable SPINNAKEr_gentl64_cti exists, and points to the location of the file spinnaker_gentl.cti [-1012]
```

Set the environment variables:

```bash
sudo nano ~/.bashrc
export SPINNAKER_GENTL64_CTI=/opt/spinnaker/lib/spinnaker-gentl/Spinnaker_GenTL.cti
export LD_LIBRARY_PATH=/opt/spinnaker/lib:$LD_LIBRARY_PATH
```
Then reboot. Make sure SpinView runs. 
