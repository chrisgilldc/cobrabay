"""
Cobra Bay
"""

# Configuration processors
import cobrabay.config
# Constants
import cobrabay.const
# Datatypes
import cobrabay.datatypes
# Sensor objects
import cobrabay.sensors
# Triggers
import cobrabay.triggers

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
