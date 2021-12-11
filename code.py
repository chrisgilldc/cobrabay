####
# CobraBay
####
import board
import time

# Release any previous displays.
import displayio
displayio.release_displays()

# Initialize CobraBay object
import cobrabay
cb = cobrabay.CobraBay()

# Start the system!
cb.Run()
