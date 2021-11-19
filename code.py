####
# CobraBay
####

# Release any previous displays.
import displayio
displayio.release_displays()

# Initialize CobraBay object
from cobrabay import CobraBay
cobrabay = CobraBay()
print(cobrabay._ApproachStrobe())

# Begin loop
while True:
    cobrabay.UpdateScreen()
