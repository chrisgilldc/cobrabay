# CobraBay
## A parking guidance system

### Hardware

I build the system with the parts below. You may be able to swap out some of these components, but no guarantee.

| Item | Description | Source | Part # |
| --- | --- | --- | --- |
| Metro M4 Airlift | Microcontroller| Adafruit | [4000](https://www.adafruit.com/product/4000) |
| 64x32 RGB LED Matrix @ 4mm pitch | Display | Adafruit | [4886](https://www.adafruit.com/product/4886) |
| Matrix Shield | Display interface | Adafruit | [2601](https://www.adafruit.com/product/2601) |
| AW9523 GPIO Expander | Additional GPIO | Adafruit | [4886](https://www.adafruit.com/product/4886) |
| US-100 | Ultrasonic Rangefinder | Adafruit | [4019](https://www.adafruit.com/product/4019) |
| VL53L1X | Laser Rangefinder | Adafruit | [3967](https://www.adafruit.com/product/3967) |
| 5V4A Switching Supply | Power Supply | Adafruit | [1466](https://www.adafruit.com/product/1466) |
| 2.1mm DC Barrel jack | Panel Power Jack | Adafruit | [610](https://www.adafruit.com/product/610) |
| QT/Qwiic JST SH 4-pin to Male Headers | I2C Board Connectors | Adafruit | [4209](https://www.adafruit.com/product/4209) |
| 5-pin DIN plug | Remote sensor cables | Parts Express | [092-150](https://www.parts-express.com/Rean-NYS322-5-Pin-DIN-Plug-092-150) |
| 5-pin DIN female chassis connector | Remote sensor ports | Parts Express | [092-154](https://www.parts-express.com/Rean-NYS325-5-Pin-DIN-Female-Chassis-Connector-092-154) |

### Configuration

Configuration is handled in a dict at the beginning of code.py. It includes the following options. Defaults in bold.

#### General
| Option | Required? | Valid Options | Units | Description |
| --- | --- | --- | --- | --- |
| units | No | **'metric'**, 'imperial' | N/A | Sets units to use for other options and display. |
| sensor_pacing | No | float | seconds | Time between sonic sensor firings. This should be tuned so that echos from one sensor doesn't interfere with another - exact timing will depend on the geometry of your garage. |
| bay | Yes | ... | N/A | Sub-dict with information about the parking bay. See below. |
| sensors | Yes | ... | N/A | Sensor name with sub-dict of sensor options. See below. |
| network | No | True/False | N/A | Enable networking, yes or no. Defaults to False |
| ssid | Yes if Network is True | str | N/A | SSID of WiFi network to use | 
| psk | Yes if Network is True | str | N/A | Pre-Shared Key of WiFi network to use |

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

#### MQTT Topics

The system uses MQTT to communicate out and get signals and commands to enter various modes. Two conceptual entities are
available, a device, representing the entire system, and a bay, representing a specific parking space. Currently only
one bay per device is supported, this may change in the future.

The following topics are created, with 'state' topics reporting device state and set topics taking in commands.
* cobrabay/device/<system_id>/state
* cobrabay/device/<system_id>/set
* cobrabay/<bay_id>/state
* cobrabay/<bay_id>/set

Commands are formatted 

##### States
A Device can have the following states:
* online - Device is online and functioning
* offline - Device is not connected to the network, not working. This is also the device's last-will, in case it goes offline unexecptedly.

A Device can accept the following commands:

| Command | Options                                     | Action | 
| --- |---------------------------------------------| --- |
| reset | None                                        | Perform a soft reset of the whole system |
| rescan_sensors | None                                        | Rescan the defined sensors |
| display_sensor | sensor: *sensor_id*<br />timeout: *seconds* | Display reading from *sensor_id* on the display for *timeout* seconds. Timeout defaults to 360s (5m). | 

A Bay can have the following states:

* occupied - A vehicle is in the bay
* vacant - A vehicle is not in the bay
* docking - In the process of docking
* undocking - In the process of undocking
* verifying -
* unavailable - Bay is not able to operate due to an issue. Likely missing/offline sensors.

| Command | Action |
| --- | --- |
| dock | Start the docking process. |
| undock | Start the undocking process. |
| abort | Abort a running docking or undocking. |
| verify | Check occupancy of bay and update status. |