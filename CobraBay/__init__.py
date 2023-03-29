####
# Cobra Bay init
####

from .bay import CBBay
from .display import CBDisplay
from .core import CBCore
from .config import CBConfig
from .network import CBNetwork
from .systemhw import CBPiStatus
from .version import __version__

import CobraBay.detectors
import CobraBay.sensors
import CobraBay.triggers

# def read_version():
#     print(__file__)
#     """Read a text file and return the content as a string."""
#     with io.open("/CobraBay/CobraBay/version.py") as f:
#         return f.read()

__repo__ = "https://github.com/chrisgilldc/cobrabay.git"
all = [
    'CBBay',
    'CBDisplay',
    'CBCore',
    'CBConfig',
    'CBNetwork',
    'CBPiStatus',
    '__version__'
]
