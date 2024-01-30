####
# Cobra Bay - Data Types
####

from collections import namedtuple as namedtuple_untyped
from typing import NamedTuple as namedtuple_typed
from pint import Quantity


# Config Validation
# CBValidation = namedtuple_untyped("CBValidation", ['valid', 'result'])
class CBValidation(namedtuple_typed):
    valid: str
    result: bool


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
class TFMP_data(namedtuple_typed):
    status: str
    distance: float
    flux: float
    temperature: float


class Sensor_Response(namedtuple_typed):
    """
    Response from sensor
    response_type will be as defined in const.SENOR_VALUE_*. Only SENOR_VALUE_OK should be considered readable.
    All other response codes can be considered failures to read. They may be lumped together or parsed out as
    appropriate.
    """
    response_type: str
    reading: Quantity


#Vector = namedtuple_untyped('Vector', ['speed', 'direction'])
class Vector(namedtuple_typed):
    """
    Vector of longitudinal movement
    """
    speed: float
    direction: str
