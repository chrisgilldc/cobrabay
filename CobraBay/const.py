from numpy import timedelta64

# Various constants

## General constants. Multiple types of objects need these.
GEN_UNKNOWN = 'unknown'
GEN_UNAVAILABLE = 'unavailable'
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

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
SYSSTATE_MOTION = (SYSSTATE_DOCKING, SYSSTATE_UNDOCKING)  # Set if any bay on the system is active.

## Sensor states.
SENSTATE_FAULT = 'fault'
SENSTATE_DISABLED = 'disabled'
SENSTATE_ENABLED = 'enabled'
SENSTATE_RANGING = 'ranging'
SENSTATE_NOTRANGING = 'not_ranging'

# Non-Quantity values the sensor can be in.
SENSOR_VALUE_OK = 'ok'
SENSOR_VALUE_INR = 'inr'  ## Interrupt Not Ready. IE: sensor wasn't ready to read.
SENSOR_VALUE_WEAK = 'weak'
SENSOR_VALUE_STRONG = 'strong'
SENSOR_VALUE_FLOOD = 'flood'
SENSOR_VALUE_TOOCLOSE = 'tooclose'

# Detector quality values.
SENSOR_QUALITY_OK = 'ok'
SENSOR_QUALITY_WARN = 'warning'
SENSOR_QUALITY_CRIT = 'critical'
SENSOR_QUALITY_BASE = 'base'
SENSOR_QUALITY_FINAL = 'final'
SENSOR_QUALITY_PARK = 'park'
SENSOR_QUALITY_BACKUP = 'backup'
SENSOR_QUALITY_NOOBJ = 'no_object'
SENSOR_QUALITY_EMERG = 'emergency'
SENSOR_QUALITY_DOOROPEN = 'door_open'
SENSOR_QUALITY_BEYOND = 'beyond_range'
SENSOR_NOREADING = 'no_reading'
SENSOR_NOINTERCEPT = 'not_intercepted'

# Directional values
DIR_FWD = 'forward'
DIR_REV = 'reverse'
DIR_STILL = 'still'

# Time intervals
TIME_MOTION_EVAL = timedelta64(250,'ms')
