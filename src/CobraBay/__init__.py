"""
Cobra Bay
"""

# Configuration processors
import CobraBay.config
# Constants
import CobraBay.const
# Datatypes
import CobraBay.datatypes
# Sensor objects
import CobraBay.sensors
# Triggers
import CobraBay.triggers

# Unitary Classes
from .bay import CBBay
from .display import CBDisplay
from .core import CBCore
from .network import CBNetwork
from .sensormgr import CBSensorMgr
from .systemhw import CBPiStatus
from .version import __version__

__repo__ = "https://github.com/chrisgilldc/cobrabay.git"
all = [
    'CBBay',
    'CBDisplay',
    'CBCore',
    'CBConfig',
    'CBNetwork',
    'CBPiStatus',
    'CBSensorMgr',
    'const',
    'sensors',
    'triggers',
    '__version__'
]
