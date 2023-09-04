# CobraBay
## A parking guidance system

With a snug two-car garage and two small children, getting parked in exactly the right spot was important. This system
is the product (and ongoing project) of two years work trying to get a good solution to help myself and my wife park in
just the right way.

It has also been the primary way I have taught myself python and electronics, so there is likely a lot that can be 
optimized, done better or redesigned here. Constructive feedback welcome!

---
* [Building](docs/HARDWARE.md) - How to put together the hardware
* Installing - How to install the software
* [Configuration](docs/CONFIG.md) - Reference to the configuration file options.

## Installing

### Platform

This system was originally written for CircuitPython, with the intention of running on microcontrollers (ie: Metro M4). Due to
memory-management issues, it has been converted to a standard Python application. It has been tested on a Pi 3+ with 
Raspberry Pi OS Lite 64-bit. Any other Pi with Raspberry Pi OS should work.

### System Configuration
* Install OS - I use RaspberryPiOS 64 Lite
* Configure network (Wifi or Ethernet, as appropriate)
* Enable I2C
* Update system configuration
  * Add 'isolcpus=3' to the end of /boot/cmdline.txt
  * Blacklist the sound module. The Adafruit installation script currently doesn't do this correctly for the latest RPiOS version ([#253](https://github.com/adafruit/Raspberry-Pi-Installer-Scripts/issues/253))
  ```sudo echo -n "blacklist snd_bcm2835" > /etc/modprobe.d/alsa-blacklist.conf```
* Enable serial port for TFMini support
  * ```raspi-config```
  * 3 Interfaces
  * I6 Serial Port
  * Login shell over serial -> NO
  * Serial port hardware enabled -> YES
  * reboot (should prompt when done)

### Required Libraries

* Install a few extra packages (if you used Lite)
* ```sudo apt install gcc python3-dev git```
* Install requirements.
* ```pip3 install -r requirements.txt```
* Install the RGB Matrix library using the Adafruit scripts
  * ```curl https://raw.githubusercontent.com/adafruit/Raspberry-Pi-Installer-Scripts/main/rgb-matrix.sh >rgb-matrix.sh sudo bash rgb-matrix.sh```
  * Select "Y" to Continue
  * Select "2", Matrix HAT + RTC
  * Select "1" for Quality

### Install CobraBay

Note: I have not yet made this a PIPable repository. Maybe some day. For now, you need to download the package manually 
and do a local install.
* Login as 'pi'
* Download the [latest release](https://github.com/chrisgilldc/cobrabay/releases/latest) and extract.
  ```wget https://github.com/chrisgilldc/cobrabay/archive/refs/tags/v0.2.0-alpha.tar.gz```
* Extract the archive.
  ```tar -xzf v0.2.0-alpha.tar.gz```
* PIP install for the Pi user from the archive
  ```pip install --user ./v0.2.0-alpha.tar.gz```

# Future Enhancements & Bug Fixes
## Enhancements:
* Better separate undock and dock modes. Currently, undock uses too much of the dock behavior.
* Range-based trigger. Start process based on range changes
* Replace strober with progress bar - **In progress**
* Ability to save current system settings to config file
* Ability to soft-reload system from config file
* Ability to save current vehicle position as offsets
* Even better sensor handling. Reset sensors if they go offline. - **In progress**


## Known Issues:
* ~~Detector offsets sometimes don't apply.~~ Fixed (I think)
* If MQTT broker is inaccessible during startup, an MQTT trigger will cause system to go into a loop.

