# CobraBay
## A parking guidance system

## Installing

### Platform

This system was originally written for CircuitPython, with the intention of running on microcontrollers (ie: Metro M4). Due to
memory-management issues, it has been converted to a standard Python application. It has been tested on a Pi 3+ with 
Raspberry Pi OS Lite 64-bit. Any other Pi with Raspberry Pi OS should work.

### System Configuration
* Install OS
* Configure network (Wifi or Ethernet, as appropriate)
* Enable I2C


### Required Libraries

* [paho-mqtt](https://github.com/eclipse/paho.mqtt.python)
* [rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix)

### CobraBay
* Copy 'cobrabay' to _device_/lib/cobrabay
* Copy 'code.py' to _device_/code.py

Install the following libraries:
  * adafruit_aw9523
  * adafruit_bitmap_font
  * adafruit_display_shapes
  * adafruit_display_text
  * adafruit_esp32spi
  * adafruit_hcsr04
  * adafruit_register
  * adafruit_vl53l1x
  * paho-mqtt

To install modules:
```
pip3 install adafruit-circuitpython-aw9523 adafruit_circuitpython_bitmap_font \
  adafruit_circuitpython_display_shapes adafruit_circuitpython_display_text \
  adafruit_circuitpython_hcsr04 adafruit_circuitpython_vl53l1x \
  paho-mqtt
```

Optionally, if you want to send to remote syslog:
* [syslog_handler](https://github.com/chrisgilldc/circuitpython_syslog_handler)

### Fonts
Place the fonts directory from the repo into _device_/fonts

### Hardware
System has been built and tested with the following hardware:
* Metro M4 Airlift
* 64x32 RGB LED Matrix
* AW9523 GPIO Expander
* US-100 ultrasonic rangefinder
* VL53L1X IR rangefinder

It *may* work on other hardware configurations that are equivilent, but I haven't tested them and make no guarantees.

Details on assembly, including models for 3d printing enclosures can be found here.

### Configuration

Configuration is handled in a dict at the beginning of code.py. It includes the following options. Defaults in bold.

#### General
| Option        | Required?              | Valid Options            | Units   | Description                                                                                                                                                                     |
|---------------|------------------------|--------------------------|---------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| units         | No                     | **'metric'**, 'imperial' | N/A     | Sets units to use for other options and display.                                                                                                                                |
| sensor_pacing | No                     | float                    | seconds | Time between sonic sensor firings. This should be tuned so that echos from one sensor doesn't interfere with another - exact timing will depend on the geometry of your garage. |
| bay           | Yes                    | ...                      | N/A     | Sub-dict with information about the parking bay. See below.                                                                                                                     |
| sensors       | Yes                    | ...                      | N/A     | Sensor name with sub-dict of sensor options. See below.                                                                                                                         |
| network       | No                     | True/False               | N/A     | Enable networking, yes or no. Defaults to False                                                                                                                                 |
| ssid          | Yes if Network is True | str                      | N/A     | SSID of WiFi network to use                                                                                                                                                     | 
| psk           | Yes if Network is True | str                      | N/A     | Pre-Shared Key of WiFi network to use                                                                                                                                           |

#### Bay Options
Dimensions for the parking bay. All units are either in centimeters or inches, depending on the master units setting.

| Options | Required? | Description |
| --- | --- | --- |
| detect_range | Yes | Maximum detection range for the approach. Can be less than your maximum possible range if the far ranges are known to be unreliable and you want to trim them off. |
| park_range | Yes | Distance from the sensor where the car should stop. Sets the '0' mark when displaying distance. |
| height | Yes | Height of the garage when vacant. |
| vehicle_height | Yes | Height of the vehicle. Used along with overall height to detect when car is moving sideways out of its bay. |

#### Sensor Options
| Options | Sensor Type | Required? | Valid Options | Units | Description |
| --- | --- | --- | --- | --- | --- |
| type | N/A | Yes | 'vl53', 'hcsr04' | N/A | Type of sensor. Note, HCSR04 mode should work for any compatible sensor, such as the US-100. |
| address | vl53 | Yes | 0x29, 0x.... | N/A | I2C address of the sensor. |
| distance_mode | vl53 | No | **'long'**, 'short' | N/A | Distance sensing mode |
| timing_budget | vl53 | No | 15 (short mode only), 20, 33, **50**, 100, 200, 500 | ms | Ranging duration. Increasing and improve reliability. Only certain values are supported by the base library. |
| board | hcsr04 | Yes | **'local'**,'0x58','0x59','0x5A','0x5B' | N/A | Where the GPIO pins for trigger and echo are. 'Local' uses on-board pins from the board. If using an AW9523 GPIO expander, specify the I2C address of the board. |
| trigger | hcsr04 | Yes | int | N/A | Pin to trigger ping. |
| echo | hcsr04 | Yes | int | N/A | Pin to listen for echo on. |
| timeout | hcsr04 | Yes | float | seconds | How long to wait for the echo. |

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

**Memory**

Topic: '/cobrabay/_MAC_/mem'

Available memory on the device, in kilobytes. Largely useful in debugging where we can wander into MemoryExceptions.

### Device Commands

A Device can accept the following commands through the topic 'cobrabay/_MAC_/cmd'

| Command        | Options                                     | Action                                                                                                | 
|----------------|---------------------------------------------|-------------------------------------------------------------------------------------------------------|
| reset          | None                                        | Perform a soft reset of the whole system                                                              |
| rescan_sensors | None                                        | Rescan the defined sensors                                                                            |
| display_sensor | sensor: *sensor_id*<br />timeout: *seconds* | Display reading from *sensor_id* on the display for *timeout* seconds. Timeout defaults to 360s (5m). | 
| discover       | None                                        | Recalculate discovery and resend to Home Assistant.                                                   |

### Bay Sensors
Bay sensors are reported as a child of the device, under '/cobrabay/_MAC_/_bay_name_/_sensor_'

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



A pr*ogression of sensors would look like this:*

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
| complete | Mark the docking as complete based on an external criteria |
| abort | Abort a running docking or undocking. |
| verify | Check occupancy of bay and update status. |


# Future Enhancements
Not-quite-bugs:
* Get Syslog handler to attach to children.

Sort of working but not done yet:
* Home Assistant Discovery

Features
* Include NTP client so real timestamps can be included
* Separate configuration into YAML
* Add ability to load/reload/save configuration via MQTT commands