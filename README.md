# Cobra Bay
## A parking guidance system

![Launch!](docs/cb_launch.gif)

With a snug two-car garage and two small children, getting parked in exactly the right spot was important. This system
is the product (and ongoing project) of two years work trying to get a good solution to help myself and my wife park in
just the right way.

It has also been the primary way I have taught myself python and electronics, so there is likely a lot that can be 
optimized, done better or redesigned here. Constructive feedback welcome!

Current development version: 0.4.2a3

---
* [Building](docs/HARDWARE.md) - How to put together the hardware
* [Installing](docs/INSTALL.md) - How to install the software
* [Configuration](docs/CONFIG.md) - Reference to the configuration file options.

## Bugs
* System
  * Improve I2C Error Handling - Some I2C faults, especially for an AW9523, can still tank the system.
  * Finish implementing threading. Maybe not needed if fault isolation is done? TBD.
  * Fix shutdown exceptions. Sensor destructor doesn't actually work correctly.
  * Report IP correctly on startup
* Logging
  * Add log file size limits and auto-rollover. Otherwise, in debug mode this can fill the filesystem!
* Network
  * MQTT messages go 'unknown' in HA - Should probably be more aggressive about retain statuses.
  * Run network loop after MQTT connect attempt to confirm actual connection.
  * Properly react to homeassistant/status online messages.
* Bay & Sensor
  * Bay doesn't acknowledge range sensor negative range.
  
## Known Issues:
* ~~Detector offsets sometimes don't apply.~~ Fixed (I think)
* If MQTT broker is inaccessible during startup, an MQTT trigger will cause system to go into a loop.

## Enhancements:
* Structure
  * Separate some routines into separate libraries?
  * Write tests
* Performance
  * Split sensors into separate thread/process. 
* Operations
  * MQTT-based sensor
  * Range-based trigger. Start process based on range changes.
  * Additional diagnostics via MQTT. Min/max ranges seen, total faults, total non-numerical values on sensor, maybe more.
  * Restructure commands for cleaner HA interaction.
  * Trigger to end operation, ie when garage door closes.
* Configuration
  * Ability to save current system settings to config file
  * Ability to soft-reload system with new config file.
  * Ability to set some (all?) config values via MQTT.
  * Ability to save current vehicle position as offsets.
* Display
  * Replace strober with progress bar 
  * Micro-car graphic
  * Sensor status graphic
  * Alternatives to clock, possibly divide the display.
* Multiple bay support (is this needed? IDK.)
* Documentation
  * Review install instructions
  * Review current documentation for accuracy
  * Write hardware build guide
  * Create Sphinx documention (also: Learn Sphinx)



