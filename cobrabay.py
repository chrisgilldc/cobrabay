####
# CobraBay - Command line invoker
####

import sys
import logging
from logging.handlers import SysLogHandler
import lib.cobrabay as cobrabay

# Find a default 'config.py' file.
try:
    from config import config
    config = config
except ImportError:
    print("Core: No config.py file! Have to have a config to load!")
    sys.exit()

# Initialize the object.
cb = cobrabay.CobraBay(config)

# Start the main operating loop.
cb.run()