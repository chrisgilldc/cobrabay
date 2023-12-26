# Various constants

## General constants. Multiple types of objects need these.
GEN_UNKNOWN = 'unknown'
GEN_UNAVAILABLE = 'unavailable'

## Bay States
BAYSTATE_DOCKING = 'docking'
BAYSTATE_UNDOCKING = 'undocking'
BAYSTATE_VERIFY = 'verify'
BAYSTATE_READY = 'ready'
BAYSTATE_NOTREADY = 'not_ready'
BAYSTATE_POSTROLL = 'postroll'
BAYSTATE_MOTION = (BAYSTATE_DOCKING, BAYSTATE_UNDOCKING)

## Bay Commands
BAYCMD_DOCK = 'dock'
BAYCMD_UNDOCK = 'undock'
BAYCMD_ABORT = 'abort'

## System States
SYSSTATE_READY = 'ready'
SYSSTATE_DOCKING = 'docking'
SYSSTATE_UNDOCKING = 'undocking'
SYSSTATE_MOTION = (SYSSTATE_DOCKING, SYSSTATE_UNDOCKING)

## Sensor states.
SENSTATE_FAULT = 'fault'
SENSTATE_DISABLED = 'disabled'
SENSTATE_ENABLED = 'enabled'
SENSTATE_RANGING = 'ranging'
SENSTATE_NOTRANGING = 'not_ranging'

# Non-Quantity values the sensor can be in without
SENSOR_VALUE_OK = 'ok'
SENSOR_VALUE_WEAK = 'weak'
SENSOR_VALUE_STRONG = 'strong'
SENSOR_VALUE_FLOOD = 'flood'
SENSOR_VALUE_TOOCLOSE = 'tooclose'

# Detector quality values.
DETECTOR_QUALITY_OK = 'ok'
DETECTOR_QUALITY_WARN = 'warning'
DETECTOR_QUALITY_CRIT = 'critical'
DETECTOR_QUALITY_BASE = 'base'
DETECTOR_QUALITY_FINAL = 'final'
DETECTOR_QUALITY_PARK = 'park'
DETECTOR_QUALITY_BACKUP = 'backup'
DETECTOR_QUALITY_NOOBJ = 'no_object'
DETECTOR_QUALITY_EMERG = 'emergency'
DETECTOR_QUALITY_DOOROPEN = 'door_open'
DETECTOR_QUALITY_BEYOND = 'beyond_range'
DETECTOR_NOREADING = 'no_reading'
DETECTOR_NOINTERCEPT = 'not_intercepted'

# Directional values
DIR_FWD = 'forward'
DIR_REV = 'reverse'
DIR_STILL = 'still'



