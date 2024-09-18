# Installation 

### Hardware

1. Connect Basler USB 3.0 to the computer.

Optional Steps for hardware trigger:

2. Connect Pin 9 of Arduino with Pin 1 (Brown cable) of the Basler, and GND pin of Arduino with Pin 6 (White cable) of the Basler.

3. Connect Arduino to the computer

### Software

1. Upload `Arduino_trigger.ino` file to the Arduino.
2. Download and install [Basler Pylon SDK](https://www2.baslerweb.com/en/downloads/software-downloads/#type=pylonsoftware).


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

## Hardware Troubleshoot

For GPIO coax cable color codes, refer [here](https://docs.baslerweb.com/basler-io-cable-hrs-6p-open-p?_gl=1*6p8gh3*_gcl_au*MTQyMTg2MzkwOC4xNzI2MDg5ODQ4).

Find Basler GPIO pins [here](https://docs.baslerweb.com/aca2040-120um)


