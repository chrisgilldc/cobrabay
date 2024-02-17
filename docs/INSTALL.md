# CobraBay Installation

This guide covers the installation of the base system and CobraBay software on the hardware as recommended in [Hardware](HARDWARE.md)
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
  * ```sudo apt-get upgrade```
* Update system settings with raspi config ```sudo raspi-config```
  * Enable I2C.
    * Navigate to '3 Interface Options'
    * Select 'I5 I2C'. Select 'Yes', then 'OK'.
  * Enable serial port for TFMini.
    * Navigate to '3 Interface Options'
    * Select 'I6 Serial Port'
    * When asked 'Would you like a login shell to be accessble over serial?', select NO.
    * When asked 'Would you like the serial port hardware to be enabled?', select YES.
  * Press tab twice to select 'FINISH'
  * When asked 'Would you like to reboot now?', select 'NO'
* Update system configuration.
  * Add 'isolcpus=3' to the end of /boot/cmdline.txt
  * Blacklist the sound module. The Adafruit installation script currently doesn't do this correctly for the latest RPiOS version ([#253](https://github.com/adafruit/Raspberry-Pi-Installer-Scripts/issues/253))
  ```sudo echo -n "blacklist snd_bcm2835" > /etc/modprobe.d/alsa-blacklist.conf```
* Reboot the system.
  * ```sudo reboot```

### Prepare to install CobraBay

Unfortunately, the rgbmatrix library is not packaged. It needs to be installed manually. Install it manually using the following steps.
* Install the RGB Matrix library using the Adafruit scripts
  * ```curl https://raw.githubusercontent.com/adafruit/Raspberry-Pi-Installer-Scripts/main/rgb-matrix.sh >rgb-matrix.sh sudo bash rgb-matrix.sh```
  * Select "Y" to Continue
  * Select "2", Matrix HAT + RTC
  * Select "1" for Quality

### Install CobraBay

* Install a few extra packages (if you used Lite)
* ```sudo apt install gcc python3-dev git```

* Install requirements.
  * ```pip3 install -r requirements.txt```


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