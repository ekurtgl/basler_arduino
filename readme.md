# Installation 

### Software

1. Download and install [Basler Pylon SDK](https://www2.baslerweb.com/en/downloads/software-downloads/#type=pylonsoftware).
2. **[Optional for hardware trigger with Arduino]** Upload `utils/arduino_pwm_led/arduino_pwm_led.ino` file to the Arduino.

### Hardware

1. Connect Basler USB 3.0 to the computer.

Optional Steps for hardware trigger:

2. Connect Pin 3 of Arduino with Pin 1 (Brown cable) of the Basler, and GND pin of Arduino with Pin 6 (White cable) of the Basler.

3. Connect Pin 10 of Arduino with the stimulation's input ((+) for the external LED) line, and GND pin of Arduino with LED's (-) line.

4. Connect Arduino to the computer via USB.

### Set Arduino access rights

```bash
# navigate to rules.d directory
cd /etc/udev/rules.d
#create a new rule file
sudo touch my-newrule.rules
# open the file
sudo vim my-newrule.rules
# add the following
KERNEL=="ttyACM0", MODE="0666"
```
Restart the computer for the access rights to take effect.


### Configs

`--n_total_frames` should be equal to the product of total duration of each blocks in `stimulation_config.json` and the `AcquisitionFrameRate`.

## Hardware Troubleshoot

For GPIO coax cable color codes, refer [here](https://docs.baslerweb.com/basler-io-cable-hrs-6p-open-p?_gl=1*6p8gh3*_gcl_au*MTQyMTg2MzkwOC4xNzI2MDg5ODQ4).

Find Basler GPIO pins [here](https://docs.baslerweb.com/aca2040-120um)

### Arduino

If the Arduino IDE stalls with the following notification:

`Downloading index library_index.tar.bz2`

End arduino processes in the system monitor or kill their pids, and delete `/home/<username>/.arduinoIDE/arduino-cli.yaml` file.

