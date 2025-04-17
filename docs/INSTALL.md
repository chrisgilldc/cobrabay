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
  * ```sudo apt-get upgrade```
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
  ```sudo echo -n "blacklist snd_bcm2835" > /etc/modprobe.d/alsa-blacklist.conf```
* Reboot the system.
  * ```sudo reboot```

### Prepare to install Cobra Bay

#### Install the rgbmatrix library
Unfortunately, the rgbmatrix library is not packaged. It needs to be installed manually. Install it manually using the following steps.
* Install the RGB Matrix library using the Adafruit scripts
  * ```curl https://raw.githubusercontent.com/adafruit/Raspberry-Pi-Installer-Scripts/main/rgb-matrix.sh >rgb-matrix.sh; sudo bash rgb-matrix.sh```
  * Select "Y" to Continue
  * Select "2", Matrix HAT + RTC
  * Select "1" for Quality
  * The library will compile. When complete and asked to reboot, select "y"

#### Create a Virtual Environment.

Raspberry Pi OS, as of Bookworm, requires use of Virtual Environments (venvs) to contain Python packages.

To set up a venv for Cobra Bay, do the following:
* Ensure venv support is installed.
  * ```sudo apt install python3.11-venv```
* Install the Python packages available as RPiOS packages.
  * ```sudo apt-get install -y python3-cerberus python3-gpiozero python3-paho-mqtt python3-numpy python3-pint python3-psutil python3-serial python3-smbus2 python3-yaml```
* Create a venv. If you change the path of this venv, be sure to update the path in all further instructions.
  * ```python -m venv --system-site-packages ~/.env_cobrabay```
* Enter the venv
  * ```source ~/.env_cobrabay/bin/activate```


### Install Cobra Bay

Cobra Bay is currently in Alpha and not fully packaged. You will need to install by pulling from the source. The main
branch is expected to be relatively stable, with some possible crashing conditions.
* Download the [main branch code](wget https://github.com/chrisgilldc/cobrabay/archive/refs/heads/main.zip) and extract.
  ```wget https://github.com/chrisgilldc/cobrabay/archive/refs/heads/main.zip```
* Extract the archive.
  ```unzip main.zip```
* It's recommended to rename based on the current version. These instructions will use 'cobrabay_version' as the path.
  * ```mv cobrabay-main cobrabay_0.4.0a```
* Install the remaining packages into the venv.
  * Enter the venv if not already. ```source ~/.env_cobrabay/bin/activate```
  * Install packages. ```pip install -r ~/cobrabay_version/requirements.txt```
* 
* Install a few extra packages (if you used Lite)
  * ```sudo apt install gcc python3-dev git```
* Install requirements.
  * ```pip3 install -r requirements.txt```
* Install the remaining packages from the requirements list. Note that this includes the packages already installed from
the system packages, which should have been included and not get picked up again.
  * ```pip3```
  * 

### Configure Cobra Bay
