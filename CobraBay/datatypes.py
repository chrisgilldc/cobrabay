"""
Cobra Bay - Data Types
"""

from collections import namedtuple as namedtuple_untyped
from typing import NamedTuple as namedtuple_typed
from pint import Quantity
from numpy import datetime64


# Config Validation
# CBValidation = namedtuple_untyped("CBValidation", ['valid', 'result'])
class CBValidation(namedtuple_typed):
    valid: bool
    result: str


# Define the environment options named tuple.
ENVOPTIONS = namedtuple_untyped('EnvOptions',
                                ['base', 'rundir', 'configdir', 'configfile', 'logdir', 'logfile', 'loglevel'])
# Empty environment options named tuple.
ENVOPTIONS_EMPTY = ENVOPTIONS(None, None, None, None, None, None, None)

# Sensor interface information
iface_info = namedtuple_untyped("iface_info", ['type', 'addr'])

# Intercept for lateral detectors
Intercept = namedtuple_untyped('Intercept', ['lateral', 'intercept'])


# TFMini Data
# TFMP_data = namedtuple_untyped("TFMP_Data", ["status", "distance", "flux", "temperature"])
class TFMPData(namedtuple_typed):
    """"
    Response from the TFMini Plus
    """
    status: str
    distance: float
    flux: float
    temperature: float


class SensorReading(namedtuple_typed):
    """
    General purpose sensor response, used to carry sensor values from sensor objects to elsewhere.
    response_type will be as defined in const.SENOR_VALUE_*. Only SENOR_VALUE_OK should be considered readable.
    All other response codes can be considered failures to read. They may be lumped together or parsed out as
    appropriate.
    """
    state: str
    status: str
    fault: bool
    response_type: str
    range: Quantity or None
    temp: Quantity or None
    fault_reason: str or None


class SensorResponse(namedtuple_typed):
    """
    Contains a single set of sensor responses from the sensor manager at a given moment in time. Every sensor should
    always have a SensorReading returned. Those without a new reading ready should use the most recent values with the
    SENSOR_RESP_INR (Interrupt Not Ready) response type.
    """
    timestamp: datetime64
    sensors: dict
    scan_time: float


# Vector = namedtuple_untyped('Vector', ['speed', 'direction'])
class Vector(namedtuple_typed):
    """
    Vector of longitudinal movement
    """
    speed: float
    direction: str
