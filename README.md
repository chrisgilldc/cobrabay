# CobraBay
## A parking guidance system

### Hardware

System has been built and tested with the following components. It may work and be portable to other components, but I haven't tested and make no guarantees.
 - [Adafruit Metro M4 Airlift](https://www.adafruit.com/product/4000)
 - [64x32 RGB LED Matrix @ 4mm pitch](https://www.adafruit.com/product/4886)
 - [AW9523 GPIO Expander breakout board](https://www.adafruit.com/product/4886)
 - HC-SR04 ultrasound sensor
 - VL53

Additional components used for connections and assembly:
 - [Adafruit RGB Matrix shield for Arduino](https://www.adafruit.com/product/2601) (Metro M4 compatible)
 - [5v, 4a power supply](https://www.adafruit.com/product/1466)

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
