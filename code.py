####
# CobraBay
####

from gc import mem_free

print("Initial free memory: {}".format(mem_free()))

# Release any previous displays.
import displayio
displayio.release_displays()

# Initialize CobraBay object
import cobrabay
print("Memory after importing Cobrabay: {}".format(mem_free()))
import sys
print("Memory after importing sys: {}".format(mem_free()))

# Find a default 'config.py' file.
try:
    from config import config
    config = config
except ImportError:
    print("Core: No config.py file! Have to have a config to load!")
    sys.exit(1)

# Initialize the object.
cb = cobrabay.CobraBay(config)

# Start the main operating loop.
cb.run()