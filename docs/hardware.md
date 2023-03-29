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


Basic System Configuration

1. Install Raspbian
2. Configure network.
3. Run a complete update
````
apt-get update
apt-get upgrade
````
4. Set up serial
   1. Open the /boot/config.txt file in an editor
   ````
   sudo nano /boot/config.txt
   ````
   2. Disable audio. Find the setting below and change **on** to **off**.
   ````
   dtparam=audio=on
   ````
   3. Add the following lines to the end of the /boot/config.txt to turn on the UART and turn off Bluetooth
   (which by default will use the hardware UART.)
   ````
   enable_uart=1
   dtoverlay=pi3-disable-bt
   ````
   4. Reboot.
   ````
   sudo reboot
   ````