# CobraBay MQTT Readme

CobraBay is intended to communicate primarilly through MQTT with other systems, both to report status and take commands.
I have designed and tested it against Home Assistant but in principle another MQTT-based system should integrate.

# The Base

For a given CobraBay system, all other topics are relative to a base topic of `CobraBay/<MAC>`, where `<MAC>` is the MAC
address of the system's network interface. The Base Topic should be stable short of network reconfigurations or hardware replacement.

All other topics in this document are relative to the base topic unless otherwise noted.

# System

The system sends out a variety of topics for status. Several are intended largely for debugging and can be ignored in 
general use.

## Status Topics
| Topic | Type      | Updates | Values                                                                                                                 | Description                                                                                                            |
|---|-----------|---------|------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------|
| connectivity | Immediate | string  | 'online', 'offline' | Is the system online? This is also the system's last will, so exiting (cleanly or not) will set the topic to 'offline' |
| display | b64       | ~5s     | image      | Contents of physical display. May have ~5s update lag.                                                                 |
| cpu_pct | float     | 60s     | 0-100      | Percentage of CPU used.                                                                                                |
| cpu_temp | float | 60s     | 0-200      | CPU temperature, in degrees celsius.                                                                                   |
| mem_info | json dict | 60s     | Memory use | Memory used and available, both as percentage and value in Mb.                                                         |
| undervoltage| bool | 60s | true, false | Is the Pi reporting undervoltage?                                                                                      |

## Commands
Commands can be sent to the 'base/cmd' topic. Not all are implemented.

| Command | Type | Implemented | Description |
| --- | --- | --- | --- |
| rediscover | string | Y | Resend discovery messages to Home Assistant. |
| restart | string | N | Restart the system |
| rescan | string | N | Rescan the configure sensors. |
| save_config | string | N | Save the current configuration to the config file. |

# Bays
Each bay handles topics under `base/<bay_id>`. This makes it notionally possible to have one system handle multiple bays, although multiple displays are not yet supported.
All status topics update as quickly as possible, when relevant. IE: the vector status doesn't update when nothing is moving.

## General Status Topics
| Topic | Type | Updates | Values | Description |
|-------| --- | --- | --- | --- |
| state | string | Immediately | 'ready', 'docking', 'undocking', '' | What the bay is doing now. |
| motion_timer | time | Immediately | From config | Countdown timer to determine the vehicle is still. Based on the `` config option for the bay. | 
| occupancy | bool | Immediately | true, false | Is the bay currently occupied by a vehicle. |
| vector | json dict | Immediately | 'speed', 'direction' | Direction and speed of vehicle movement. Speed will be in mph or kph, depending on config settings. When no movement is found, speed is 0, direction is 'still' |

## Detector Status Topics
Each bay will have a 'detector' topic, under which each detector will be reported under its id. For example, a detector 'mid_lateral' would appear as '<bay_id>/detectors/mid_lateral'.

| Topic | Type | Values                                                   | Description                      | 
| --- | --- |----------------------------------------------------------|----------------------------------|
| state | string | 'fault', 'disabled', 'enabled', 'ranging', 'not_ranging' | Operating state of the detector. |
| status | string | 'disable','enable','range'                               | Commanded state of the detector. |
| fault | bool | true, false                                              |                                  |
| offset | float | Any                                                      |                                  |
| reading | float | Any                                                      |                                  |
| raw_reading | float | Any                                                      |                                  |
| quality | string | Long: 'ok','<br> Lateral: 'ok','warning','critical'      |                                  |

## Commands

