####
# CobraBay
####

config = {
    'max_detect_range': 276, # Range in inches where tracking starts.
    'approach_strobe_speed': 100 # Strobe speed for the approach lights. In Milliseconds.
}

# Release any previous displays.
import displayio
displayio.release_displays()

# Initialize CobraBay object
from cobrabay import CobraBay
cobrabay = CobraBay(config)
print(cobrabay._ApproachStrobe())

# Begin loop
while True:
    cobrabay.UpdateScreen()
