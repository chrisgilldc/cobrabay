# CobraBay
## A parking guidance system

## Installing

### Platform

This system was originally written for CircuitPython, with the intention of running on microcontrollers (ie: Metro M4). Due to
memory-management issues, it has been converted to a standard Python application. It has been tested on a Pi 3+ with 
Raspberry Pi OS Lite 64-bit. Any other Pi with Raspberry Pi OS should work.

### System Configuration
* Install OS - I use RaspberryPiOS 64 Lite
* Configure network (Wifi or Ethernet, as appropriate)
* Enable I2C

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


### Hardware
System has been built and tested with the following hardware:
* Raspberry Pi 4
* 64x32 RGB LED Matrix
* AW9523 GPIO Expander
* TFMini
* VL53L1X IR rangefinder

It *may* work on other hardware configurations that are equivilent, but I haven't tested them and make no guarantees.

Details on assembly, including models for 3d printing enclosures can be found here.

### Configuration

The system will look for a configuration file on startup.
The configuration file is a yaml file with several major sections.

#### Config Sections
All sections are **required**, even if empty. Can be defined in any order.

| Section                 | Description |
|-------------------------| --- |
| [System](#System)       | Basic system configuration |
| [Triggers](#Triggers)   | Triggers define how the system detects docking or undocking behavior. |
| [Display](#Display)     | The display mounted in the garage. |
| [Detectors](#Detectors) | Sensing units placed around the garage. |
| [Bays](#Bays)           | Dimensions and behavior for a particular parking spot. Currently only one Bay is supported. |


#### System
| Option              | Required? | Valid Options                   | Units   | Description                                                                                                                                                                     |
|---------------------|-----------|---------------------------------|---------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| units               | No        | **'metric'**, 'imperial'        | N/A     | Sets units to use for other options and display.                                                                                                                                |
| system_name         | No        | float                           | seconds | Time between sonic sensor firings. This should be tuned so that echos from one sensor doesn't interfere with another - exact timing will depend on the geometry of your garage. |
| [mqtt](#mqtt)       | Yes       | dict                            | N/A | Dictionary of MQTT settings. See below                                                                                                                                          |
| mqtt_commands       | Yes       | bool                            | N/A | Should commands via MQTT be honored?                                                                                                                                            |
| interface           | Yes       | Any valid Linux interface name. | N/A | Interface to monitor for connectivity status on the display.                                                                                                                    |
| homeassistant       | Yes       | bool                            | N/A | Integrate with Home Assistant? Will control sending of HA discovery options.                                                                                                    |
| [logging](#Logging) | No     | dict                       | N/A | Options for logging system-wide or within specific modules. See below for details.                                                                                              |

##### System Subsections

###### mqtt

MQTT section, within the system segment.

| Options   | Required? | Description                                          |
|-----------| --- |------------------------------------------------------------|
| broker    | Yes | Host or IP of the broker to connect to.                    |
| port      | Yes | Broker port to connect to. SSL is not currently supported. |
| username  | Yes | Username to log into the broker with.                      |
| password  | Yes | Password to log into the broker with.                      |

###### Logging

Logging options, system-wide or for specific modules.

| Options    | Required? | Default               | Description                                  |
|------------|-----------|-----------------------|----------------------------------------------|
| console    | No        | True                  | Log to the console                           |
| file       | No        | True                  | Log to a file                                | 
| file_path  | No        | cwd/<System_Name>.log | File to log do when file logging is enabled. |
| bays       | No        | None                  | Log level for all Bays                       |
| <bay_name> | No     | None                  | Log level for a specific bay.                |
| config                | No     | None                  | Log level for the configuriation handling module. |
| core                  | No     | None                  | Log level for the CobraBay Core.                  |
| detectors             | No     | None                  | Log level for all Detectors.                      |
| <detector_name> | No     | None                  | Log level for a specific detector.                |
| display               | No     | None                  | Log level for the Display module.                 |
| network               | No     | None                  | Log level for the Network module.                 |
| mqtt | No | DISABLE | Log level for MQTT client. This is disabled by default and will be **very** chatty if enabled. |

#### Triggers
Triggers are used to set when and how the system should take change mode. The triggers section can define a series of 
triggers, as many as are needed.
The key name used for the trigger is the trigger's name.
 
Supported trigger types:
* MQTT Trigger - Monitors an MQTT topic for state change.

##### MQTT Trigger
| Options | Required? | Default | Description |
| --- | -- | --- | --- |
| type | Yes | mqtt_sensor | Type of trigger this should be. Currently only 'mqtt_sensor' is supported. |
| topic | Yes | None | MQTT topic to monitor. This must be a *complete* MQTT topic path. |
| bay | Yes | None | Bay this trigger is assigned to. |
| to | No | None | Topic payload to match that will set off this trigger. |
| from | Yes, if 'to' is not set. | None | A change of the topic payload to any state *other* than this value will set off the trigger. |

#### Display
Configuration for the display in the garage, to be viewed by the driver. This should be an LED matrix display, no other
display has been tested.


| Options | Required? | Valid Options | Default | Description |
| --- | -- | --- |--------| --- |
| matrix | Yes | Dict | None | Physical configuration, see below. |
| strobe_speed | Yes | str, int | 100 ms | Speed of the bottom strobe. Must be a time value. |
| mqtt_image | No | bool | Yes | Should display image be sent to MQTT. Mostly for debugging, but may be interesting. |
| mqtt_update_interval | No | str, int | 5 s | If sending the display image to MQTT server, how often to update. |

##### Display Subsections

###### Matrix
| Options       | Required? | Valid Options | Default | Description                                                                                                                                                            |
|---------------|-----------|---------------|---------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| width         | Yes       | int           | None    | Width of the matrix, in pixels                                                                                                                                         | 
| height        | Yes       | int           | None    | Height of the matrix, in pixels                                                                                                                                        |
| gpio_slowdown | Yes       | int           | None    | GPIO Slowdown setting to prevent flicker. Check [rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) docs for recommendations. Likely requires testing. |

#### Detectors
Detectors define sensing devices used to measure vehicle position. This is currently is a 1:1 mapping, where each 
physical sensor is defined as one detector. This may change in the future.
As always, the ID of a detector is the key used to define it in the config file.
Detectors are divided into two sections:

* Longitudinal - Detectors looking in parallel with the direction of vehicle travel
* Lateral - Detectors looking across the direction of vehicle travel

Define each detector under 'longitudinal' or 'lateral'

Detector definition

| Options | Required? | Valid Options | Default | Description                     |
| --- | --- | --- | --- |---------------------------------|
| name | No | str | Detector ID | Friendly name of the detector, used when creating Home Assistant entities. If not defined, will default to the detector ID. |
| sensor | Yes | Dict | None | Configuration for the underlying sensor | 

##### Sensor definition
Two types of sensor are currently supported - the serial TFMini-S and the I2C VL53L1X. 

###### TFMini-S
| Options | Required? | Valid Options         | Default                      | Description                                                                                |
| --- | --- |---|--|--------------------------------------------------------------------------------------------|
| type | Yes | str | None | TFMini sensor type.                                                         |
| port | Yes | str | None | Serial port to used. Will be prefixed with '/dev/' if not included. IE: 'serial0', 'ttyS0' |
| baud | Yes | int | None | baud rate of the sensor. You probably want 115200                                          |

###### VL53L1X
| Options | Required? | Valid Options | Default | Description                     |
|---| --- | --- | --- |---------------------------------|
| type | Yes | str | VL53L1X | VL53L1X sensor type. |
| i2c_bus | Yes | int | None | I2C bus to use. On Raspberry Pi, should be 1. |
| i2c_address | Yes | str (hex) | None | I2C address for the sensor. Should be a hex string, ie: "0x33" |
| enable_board | Yes | str (hex) | None | Board which holds the pin used to enable and disable the sensor.<br>If that pin is on an AW9523, this should be a hex address of the AW9523.<br>If directly on the Pi, should be 0 |
| enable_pin | Yes | int | None | Pin to enable and disable the board. |
| distance_mode | Yes | str | None | Distance mode to set the sensor to |
| timing | Yes | str | None | Timing for the sensor. Can be one of:<br>15 (short mode only), 20, 33, 50, 100, 200, 500 |

#### Bay Options
Define the bay the vehicle stops in. Currently all should be defined under a single key, which is the bay id. In the
future multiple bays may be possible.

| Options | Required? | Valid Options          | Default | Description                                                                                          |
| --- | --- |------------------------|---------|------------------------------------------------------------------------------------------------------|
| name | No        | str                    | Bay ID  | Friendly name of the bay, used for Home Assistant discovery. If not defined, defaults to the bay ID. | 
| motion_timeout | Yes | time quantity          | None    | After this amount of time, consider a dock or undock complete. Prevents premature termination.       |
| depth | Yes | distance quantity | None    | Total distance from the longitudinal sensor point to the garage door.                                |
| longitudinal | Yes | dict | None | Longitudinal detectors for this bay. |
| lateral | Yes | dict | None | Lateral detectors for this bay. |

##### Longitudinal and Lateral assignments
Assign detectors to either longitudinal or lateral roles and specify their configuration around the bay.

Within each role, settings are prioritized like so:

1. Settings from the detector-specific configuration
2. Settings from the role's configured defaults.
3. Settings from the system defaults, if available.



| Options     | Required? | Defaultable? | Valid Options     | Default | Lat | Long | Description                                                                                                                     |
|-------------|-----------|--------------|-------------------|---------|-----|------|---------------------------------------------------------------------------------------------------------------------------------|
| offset      | No        | Yes          | distance quantity | 0"      | Yes | Yes  | Where the zero-point for this detector should be. On Longitudinal sensors, the offset indicates where the vehicle should stop.  |
| pct_warn    | No        | Yes          | number            | 70      | No  | Yes  | Switch to 'warn' once this percentage of the bay distance is covered                                                            |
| pct_crit    | No        | Yes          | number            | 90      | No  | Yes  | Switch to 'crit' once this percentage of the bay distance is covered                                                            |
| spread_park | No        | Yes          | distance quantity | 2"      | No  | Yes  | Maximum deviation from the stop point that can still be considered "OK"                                                         |
| spread_ok   | No        | Yes          | distance quantity | 1"      | Yes | No   | Maximum deviation from the offset point that can still be considered "OK"                                                       |
| spread_warn | No        | Yes          | distance_quantity | 3"      | Yes | No   | Maximum deviation from the offset point that be considered a "WARN"                                                             |
| limit       | No        | Yes          | distance_quantity | 96"     | Yes | No   | Reading limit of the lateral sensor. Any reading beyond this will be treated as "no_object"                                     |
| side        | Yes       | Yes          | L, R              | None    | Yes | No   | Which side of the bay, looking out the garage door, the detector is mounted on.                                                 |
| intercept   | Yes       | No           | distance_quantity | None    | Yes | No   | Absolute distance from the longitudinal detector where this detector crosses the bay.                                           |



# Rewrite needed below here!

## MQTT Topics

The system uses MQTT to communicate out and get signals and commands to enter various modes. Two conceptual entities are
available, a device, representing the entire system, and a bay, representing a specific parking space. Currently only
one bay per device is supported, this may change in the future.


### Device Sensors
Device-level sensors are reported under 'cobrabay/_MAC_/_Sensor_'.

**Connectivity**

Topic: '/cobrabay/_MAC_/connectivity'
* online - Device is online and functioning
* offline - Device is not connected to the network, not working.

**Note:** This topic is also the last-will for the device. If Connectivity goes to offline, it can be safely assumed that all other topics are unavailable. 

**CPU**

Topic: '/cobrabay'/_

**Memory**

Topic: '/cobrabay/_MAC_/mem'

Available memory on the device, in kilobytes. Largely useful in debugging where we can wander into MemoryExceptions.


### Device Commands

A Device can accept the following commands through the topic 'cobrabay/_MAC_/cmd'

| Command | Action                                                                                                | 
|---------|-------------------------------------------------------------------------------------------------------|
| reboot  | Perform a soft reset of the whole system                                                              |
| rescan | Rescan hardware and reinitalize all detectors. |
| rediscover | Resend Home Assistant Discovery. |

### Bay Sensors
Bay sensors are reported as a child of the device, under '/CobraBay/_MAC_/_bay_name_/_sensor_'

**Occupied**
Current occupancy of the bay.
Topic: '/cobrabay/_MAC_/_bay_name_/occupied'
* on - Vehicle has been positively identified in the bay
* off - No vehicle identified in the bay

Note that the system presumes unoccupied as the default state, and will thus err on the side of false negatives rather than false positives.

**State**

Current operating state of the bay.

Topic: 'cobrabay/_MAC_/_bay_name_/state'

Will be on of the following:
* ready - Bay is idle and ready to enter a command mode
* docking - In the process of docking
* undocking - In the process of undocking
* verifying - In the process of verifying.
* unavailable - Bay is not able to operate due to an issue. Likely missing/offline sensors.

**Position**

Topic: 'cobrabay/_MAC_/_bay_name_/position'

Reports the position 'quality' of the bay if bay is occupied.

**Sensors**

Reports the most recent sensor readings for this bay.

A progression of sensors would look like this:*

| | Bay Occupancy | Bay State |
| --- | --- | --- |
| No vehicle | 'ready' | 'off' |
| Vehicle approaches to park | 'docking' | 'off' |
| Vehicle stops briefly | 'docking' | 'off' |
| Vehicle fully parked. | 'ready' | 'on' |

### Bay Commands

| Command | Action |
| --- | --- |
| dock | Start the docking process. |
| undock | Start the undocking process. |
| abort | Abort a running docking or undocking. |


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
* Detector offsets sometimes don't apply.
* If MQTT broker is inaccessible during startup, an MQTT trigger will cause system to go into a loop.

