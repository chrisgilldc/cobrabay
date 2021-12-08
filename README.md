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
| max_detect_range | Yes | int | **cm** / in | Distance at which vehicle approach will start being reported. This should likely be the depth of your garage, plus or minus some adjustment factor. This shouldn't be longer than the reliable detection distance of the ranging sensor. |
| speed_limit | No | int | **kph** / mph | |
| sensor_pacing | No | float | seconds | Time between sonic sensor firings. This should be tuned so that echos from one sensor doesn't interfere with another - exact timing will depend on the geometry of your garage. |
| sensors | Yes | ... | N/A | Sensor name with sub-dict of sensor options. See below. |

#### Sensor Options
| Options | Sensor Type | Required? | Valid Options | Units | Description |
| --- | --- | --- | --- | --- | --- |
| type | N/A | Yes | 'vl53', 'hcsr04' | N/A | Type of sensor. Note, HCSR04 mode should work for any compatible sensor, such as the US-100. |
| address | vl53 | Yes | 0x29, 0x.... | N/A | I2C address of the sensor. |
| distance_mode | vl53 | Yes | **'long'**, 'short' | N/A | Distance sensing mode |
| timing_budget | vl53 | Yes | int | ms | |
| board | hcsr04 | Yes | **'local'**,'0x58','0x59','0x5A','0x5B' | N/A | Where the GPIO pins for trigger and echo are. 'Local' uses on-board pins from the board. If using an AW9523 GPIO expander, specify the I2C address of the board. |
| trigger | hcsr04 | Yes | int | N/A | Pin to trigger ping. |
| echo | hcsr04 | Yes | int | N/A | Pin to listen for echo on. |
| timeout | hcsr04 | Yes | float | seconds | How long to wait for the echo. |
