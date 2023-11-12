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
ENVOPTIONS_EMPTY = ENVOPTIONS(
    None, None, None, None, None, None, None
)

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


# Sensor movement vector
Vector = namedtuple_untyped('Vector', ['speed', 'direction'])