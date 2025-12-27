# Cobra Bay Installation

This guide covers the installation of the base system and Cobra Bay software on the hardware as recommended in [Hardware](HARDWARE.md)
Variances may be allowable but performance cannot be guaranteed.

### Platform

This system was originally written for CircuitPython, with the intention of running on microcontrollers (ie: Metro M4). Due to
memory-management issues, it has been converted to a standard Python application. It has been tested on a Pi 3+ with 
Raspberry Pi OS Lite 64-bit.

### System Configuration
* Install OS - Follow standard RPi OS Lite installation process. Be sure to enable SSH!
* Configure network (Wifi or Ethernet, as appropriate)
* Boot system and login via SSH.
* Update packages.
  * ```sudo apt-get update```
  * ```sudo apt-get full-upgrade```
* Update system settings with raspi config ```sudo raspi-config```
  * Enable I2C.
    * Navigate to '3 Interface Options'
    * Select 'I2C'. Select 'Yes', then 'OK'.
  * Enable serial port for TFMini.
    * Navigate to '3 Interface Options'
    * Select 'Serial Port'
    * When asked 'Would you like a login shell to be accessble over serial?', select NO.
    * When asked 'Would you like the serial port hardware to be enabled?', select YES.
  * Press tab twice to select 'FINISH'
  * When asked 'Would you like to reboot now?', select 'NO'
* Update system configuration.
  * Add 'isolcpus=3' to the end of /boot/firmware/cmdline.txt
  * Blacklist the sound module. The Adafruit installation script currently doesn't do this correctly for the latest RPiOS version ([#253](https://github.com/adafruit/Raspberry-Pi-Installer-Scripts/issues/253))
  ```sudo bash -c 'echo -n "blacklist snd_bcm2835" > /etc/modprobe.d/alsa-blacklist.conf'```
* Reboot the system.
  * ```sudo reboot```

### Install Cobrabay
* Install system packages.
  * ```sudo apt-get install liblgpio-dev swig```
* Create a virtual environment. If you change the path of this venv, be sure to update the path in all further instructions.
  * ```python -m venv ~/.virtualenvs/cb_prod```
* Enter the venv
  * ```source ~/.env_cobrabay/bin/activate```
* Install Cobrabay.
  * ```pip install git+https://github.com/chrisgilldc/cobrabay```
* Create a configuration file. See [CONFIG](CONFIG.md) for more details.
* Create the user systemd unit directory
* ```mkdir -p ~pi/.config/systemd/user```
* Create a user system unit in ```~pi/.config/systemd/user/cobrabay.service```. An [example](docs/scripts/cobrabay.service) is included in docs/scripts.
* Load the new systemd unit.
  * ```systemctl --user daemon-reload```
* Try to start Cobrabay with systemd.
  * ```systemctl --user start cobrabay.service```
* Make sure the service started. Running the 'status' command should show 'active (running)', and data should have been sent to your MQTT broker.
  * ```systemctl --user status cobrabay.service```
* If running, you can now activate the service to start at boot-time.
  * ```systemctl --user enable cobrabay.service```
* Reboot the system and confirm the service starts.
  * ```sudo reboot```
* Confirm the system starts when rebooted.
* Should be set!