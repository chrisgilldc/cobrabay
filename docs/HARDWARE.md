Building the Hardware

I've designed the hardware system below out of mostly off the shelf parts. Links are provided for reference and 
convenience. You can likely substitute in equivalent components without issue but I make no guarantees.  

General supplies
* M2.5 screws, nuts and standoffs
* M3 screws, nuts and standoffs
* 5-conductor cable
* Neutrik Rean [NYS322](https://mou.sr/3FJMkEK) 5 pin DIN Plugs
* Neutrik Rean [NYS325](https://mou.sr/3FMnG6G) 5 pin DIN Connectors

Core System
* Core System print
  * Use the right hand or left hand print, depending on how you want to route your cables
  * The extension wings are symmetrical, and can be used for either the left or right hand case
* Raspberry Pi 3
  * Should work on any Pi or similar SBC. Original development was on the Metro M4 which lacked the CPU power for the system.
  * If you swap in another board, the prints for the system may need adjustment. Even across Pis, where footprint is 
the same, port positioning differs.
* [64x32 RGB LED Matrix, 4mm Pitch](https://www.adafruit.com/product/2278)
* [Adafruit RGB Matrix Hat](https://www.adafruit.com/product/2345)
* [Adafruit ISO1540 I2C Isolator](https://www.adafruit.com/product/4903)
  * Separates the entire sensor chain from the Pi's power, as the Pi itself can't provide enough power for all the sensors.
* [Adafruit LTC4311 I2C Extender](https://www.adafruit.com/product/4756)
  * Needed to boost the I2C signal over the cable run from the main system to the Lateral Control Box.
  * Depending on the length of the cable run to your range sensor, another may be required.
* [POE Splitter](https://www.amazon.com/gp/product/B079D5452Z/ref=ppx_yo_dt_b_search_asin_title?ie=UTF8&psc=1)
  * To power the Pi directly. You can alternately power via USB, alterations to the case will be needed.
* [5V 4A power supply](https://www.adafruit.com/product/1466)
  * Powers the display and the sensors

The sensor box cases are set up with a caution-stripe lid. If you have a multi-material printer or want to assemble 
yourself, you can use that. Otherwise, print as one object. If printing as one object, you should be able to use only half
the lid thickness.

The cases all support two mounting options - zip ties and screws. Zip tie channels are sized for XXX. Screw keyholes are sized for US #8 screws.

Range Sensor Box
* [Adafruit VL53L1X range sensor](https://www.adafruit.com/product/3967)
* [TFMini-S I2C Range Sensor](https://www.mouser.com/ProductDetail/Benewake/TFmini-S-I2C?qs=DPoM0jnrROXoBoPTEe1VSw%3D%3D)
  * An expensive sensor, this unit is needed to be able to shoot the entire length of a garage - mine, at least, is 
approximately 23 feet (7 meters), which is beyond the VL53L1X's max range.

Lateral Control Box
* Lateral Control Box case
  * There's one extra port opening in the case, to allow for future addtional sensors. Cover it with a port cover for now.
* [Adafruit VL53L1X range sensor](https://www.adafruit.com/product/3967)
  * Also acts as the middle lateral sensor.
* Adafruit AW9523 GPIO Expander
  * Used to control the lateral VL53L1X sensors for address setting.
* 


Lateral Sensor Box
* [Adafruit VL53L1X range sensor](https://www.adafruit.com/product/3967)


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
