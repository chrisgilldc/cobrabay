####
# CobraBay
####

# Release any previous displays.
import displayio
displayio.release_displays()

# Initialize CobraBay object
import cobrabay

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