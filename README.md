# CobraBay
## A parking guidance system

![Launch!](docs/cb_launch.gif)

With a snug two-car garage and two small children, getting parked in exactly the right spot was important. This system
is the product (and ongoing project) of two years work trying to get a good solution to help myself and my wife park in
just the right way.

It has also been the primary way I have taught myself python and electronics, so there is likely a lot that can be 
optimized, done better or redesigned here. Constructive feedback welcome!

---
* [Building](docs/HARDWARE.md) - How to put together the hardware
* Installing - How to install the software
* [Configuration](docs/CONFIG.md) - Reference to the configuration file options.


## Bugs
* ~~Bay vector isn't computed, speed and direction aren't sent.~~
  * Fixed. Vector is now computed and properly sent to MQTT as well. Sensitivity needs tuning, small changes are resulting in 'unknown' results.
* Undocking never kicks out of Undock placard.
  * May be fixed by vector issue, needs testing.
* MQTT messages go 'unknown' in HA - review MQTT messages for retain status, should probably be more aggressive about it.

## Known Issues:
* ~~Detector offsets sometimes don't apply.~~ Fixed (I think)
* If MQTT broker is inaccessible during startup, an MQTT trigger will cause system to go into a loop.

## Enhancements:
* Performance
  * Split sensors into separate thread/process. 
* Operations
  * Range-based trigger. Start process based on range changes.
  * Even better sensor handling. Reset sensors if they go offline. - **In progress**
  * Additional diagnostics via MQTT. Min/max ranges seen, total faults, total non-numerical values on sensor, maybe more.
  * Restructure commands for cleaner HA interaction.
* Configuration
  * Ability to save current system settings to config file
  * Ability to soft-reload system with new config file.
  * Ability to set some (all?) config values via MQTT.
  * Ability to save current vehicle position as offsets
* Display
  * Replace strober with progress bar - **In progress** 
  * Micro-car graphic
  * Alternatives to clock, possibly divide the display.
* Consoldiate sensor access and data path 
* Multiple bay support (is this needed? IDK.)
* Documentation
  * Review current documentation for accuracy
  * Write hardware build guide
  * Create Sphinx documention (also: Learn Sphinx)



