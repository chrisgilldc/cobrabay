# CobraBay Configuration

The system will look for a configuration file on startup, and is required for operation. 
The system will search in several places in this order:
1. From the command line:
   1. Config file name is 'config.yaml', unless a file name is given with -c.
   2. If a fully-qualified path is specified with -c, that is use and all other path options are ignored.
   3. If a config directory is specified with -cd, config file name will be searched for in the config directory.
   4. If a base directory is specified without specifying a separate config directory, config file will be searched for 
   5. in the base directory.
2. From 'config.yaml' in the current working directory, if no command line options specified

Environment variables are not supported at this time.

## Config Sections
All sections are **required**, even if empty. Can be defined in any order.

| Section                 | Description |
|-------------------------| --- |
| [System](#System)       | Basic system configuration |
| [Triggers](#Triggers)   | Triggers define how the system detects docking or undocking behavior. |
| [Display](#Display)     | The display mounted in the garage. |
| [Detectors](#Detectors) | Sensing units placed around the garage. |
| [Bays](#Bays)           | Dimensions and behavior for a particular parking spot. Currently only one Bay is supported. |


## System
| Option              | Required? | Valid Options                   | Units   | Description                                                                                                                                                                     |
|---------------------|-----------|---------------------------------|---------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| units               | No        | **'metric'**, 'imperial'        | N/A     | Sets units to use for other options and display.                                                                                                                                |
| system_name         | No        | float                           | seconds | Time between sonic sensor firings. This should be tuned so that echos from one sensor doesn't interfere with another - exact timing will depend on the geometry of your garage. |
| [mqtt](#mqtt)       | Yes       | dict                            | N/A | Dictionary of MQTT settings. See below                                                                                                                                          |
| mqtt_commands       | Yes       | bool                            | N/A | Should commands via MQTT be honored?                                                                                                                                            |
| interface           | Yes       | Any valid Linux interface name. | N/A | Interface to monitor for connectivity status on the display.                                                                                                                    |
| homeassistant       | Yes       | bool                            | N/A | Integrate with Home Assistant? Will control sending of HA discovery options.                                                                                                    |
| [logging](#Logging) | No     | dict                       | N/A | Options for logging system-wide or within specific modules. See below for details.                                                                                              |

### System Subsections

#### mqtt

MQTT section, within the system segment.

| Options   | Required? | Description                                          |
|-----------| --- |------------------------------------------------------------|
| broker    | Yes | Host or IP of the broker to connect to.                    |
| port      | Yes | Broker port to connect to. SSL is not currently supported. |
| username  | Yes | Username to log into the broker with.                      |
| password  | Yes | Password to log into the broker with.                      |

#### Logging

Logging options, system-wide or for specific modules.

| Options   | Required? | Default               | Description                                                                                    |
|-----------|-----------|-----------------------|------------------------------------------------------------------------------------------------|
| console   | No        | True                  | Log to the console                                                                             |
| file      | No        | True                  | Log to a file                                                                                  | 
| file_path | No        | cwd/<System_Name>.log | File to log do when file logging is enabled.                                                   |
| bays      | No        | None                  | Log level for all Bays                                                                         |
| bay       | No     | None                  | Enumerate log levels for specific bays, using their IDs.                                       |
| config    | No     | None                  | Log level for the configuriation handling module.                                              |
| core      | No     | None                  | Log level for the CobraBay Core.                                                               |
| detectors | No     | None                  | Log level for all Detectors.                                                                   |
| detector  | No     | None             | Enumerate log levels for specific detectors, using their IDs.                                  |
| display   | No     | None                  | Log level for the Display module.                                                              |
| network   | No     | None                  | Log level for the Network module.                                                              |
| mqtt      | No | DISABLE | Log level for MQTT client. This is disabled by default and will be **very** chatty if enabled. |

## Triggers
Triggers are used to set when and how the system should take change mode. The triggers section can define a series of 
triggers, as many as are needed.
The key name used for the trigger is the trigger's name.
 
Supported trigger types:
* MQTT Trigger - Monitors an MQTT topic for state change.

### MQTT Trigger
| Options | Required? | Default | Description |
| --- | -- | --- | --- |
| type | Yes | mqtt_sensor | Type of trigger this should be. Currently only 'mqtt_sensor' is supported. |
| topic | Yes | None | MQTT topic to monitor. This must be a *complete* MQTT topic path. |
| bay | Yes | None | Bay this trigger is assigned to. |
| to | No | None | Topic payload to match that will set off this trigger. |
| from | Yes, if 'to' is not set. | None | A change of the topic payload to any state *other* than this value will set off the trigger. |

## Display
Configuration for the display in the garage, to be viewed by the driver. This should be an LED matrix display, no other
display has been tested.


| Options | Required? | Valid Options | Default | Description |
| --- | -- | --- |--------| --- |
| matrix | Yes | Dict | None | Physical configuration, see below. |
| strobe_speed | Yes | str, int | 100 ms | Speed of the bottom strobe. Must be a time value. |
| mqtt_image | No | bool | Yes | Should display image be sent to MQTT. Mostly for debugging, but may be interesting. |
| mqtt_update_interval | No | str, int | 5 s | If sending the display image to MQTT server, how often to update. |

### Display Subsections

#### Matrix
| Options       | Required? | Valid Options | Default | Description                                                                                                                                                            |
|---------------|-----------|---------------|---------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| width         | Yes       | int           | None    | Width of the matrix, in pixels                                                                                                                                         | 
| height        | Yes       | int           | None    | Height of the matrix, in pixels                                                                                                                                        |
| gpio_slowdown | Yes       | int           | None    | GPIO Slowdown setting to prevent flicker. Check [rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) docs for recommendations. Likely requires testing. |

## Detectors
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

### Sensor definition
Two types of sensor are currently supported - the serial TFMini-S and the I2C VL53L1X. 

#### TFMini-S
| Options | Required? | Valid Options         | Default                      | Description                                                                                |
| --- | --- |---|--|--------------------------------------------------------------------------------------------|
| type | Yes | str | None | TFMini sensor type.                                                         |
| port | Yes | str | None | Serial port to used. Will be prefixed with '/dev/' if not included. IE: 'serial0', 'ttyS0' |
| baud | Yes | int | None | baud rate of the sensor. You probably want 115200                                          |

#### VL53L1X
| Options | Required? | Valid Options | Default | Description                     |
|---| --- | --- | --- |---------------------------------|
| type | Yes | str | VL53L1X | VL53L1X sensor type. |
| i2c_bus | Yes | int | None | I2C bus to use. On Raspberry Pi, should be 1. |
| i2c_address | Yes | str (hex) | None | I2C address for the sensor. Should be a hex string, ie: "0x33" |
| enable_board | Yes | str (hex) | None | Board which holds the pin used to enable and disable the sensor.<br>If that pin is on an AW9523, this should be a hex address of the AW9523.<br>If directly on the Pi, should be 0 |
| enable_pin | Yes | int | None | Pin to enable and disable the board. |
| distance_mode | Yes | str | None | Distance mode to set the sensor to |
| timing | Yes | str | None | Timing for the sensor. Can be one of:<br>15 (short mode only), 20, 33, 50, 100, 200, 500 |

## Bay Options
Define the bay the vehicle stops in. Currently, all should be defined under a single key, which is the bay id. In the
future multiple bays may be possible.

| Options | Required? | Valid Options | Default | Description |
| --- | --- |-------------------| --- |---|
| name | No | str               | None | Bay ID | Friendly name of the bay, used for Home Assistant discovery. If not defined, defaults to the bay ID. | 
| timeouts | Yes | dict              | None    | Various timeouts, see below.                                         |
| depth | Yes | distance quantity | None    | Total distance from the longitudinal sensor point to the garage door. |
| longitudinal | Yes | dict              | None | Longitudinal detectors for this bay.                                 |
| lateral | Yes | dict              | None | Lateral detectors for this bay.                                      |

### Bay Timeouts
No bay timeouts are required, all must be convertable to Pint time-dimension quantities.

| Options | Required? | Valid Options | Default | Description |
| --- | --- | --- | --- | --- |
| dock | No | time quantity | 2m | During a dock, vehicle must be still for this amount of time to be considered complete. |
| undock | No | time quantity | 5m | During an undock, will wait for this amount of time for motion to start. |
| post-roll | No | time quantity | 10s | After motion is complete, how long to keep the last message on the display. |

### Longitudinal and Lateral assignments
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
