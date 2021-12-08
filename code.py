####
# CobraBay
####
import board
import time

config = {
    'units': 'imperial', # Set to 'imperial' for feet/inches. Otherwise defaults to metric.
    'max_detect_range': 276, # Range in inches where tracking starts.
    'speed_limit': 5, # Treat jumps in range over this rate as spurious. Either MPH or KPH, dependingon units.
    'sensor_pacing': 0.5, # Time in seconds between each sensor ping, to prevent echos.
    'sensors': {
        'lidar_test': {'type': 'vl53', 'address': '0x29', 'distance_mode': 'short', 'timing_budget': 500}
        'sonic_test': {'type': 'hcsr04', 'board': '0x58', 'trigger': 1, 'echo': 2, 'timeout': 0.5 },
        }
}

# Release any previous displays.
import displayio
displayio.release_displays()

# Initialize CobraBay object
from cobrabay import CobraBay
cobrabay = CobraBay(config)


# Start the system
#import asyncio
#asyncio.run(cobrabay.Run())

# Begin loop
while True:
    range = cobrabay._UpdateSensor('center')
    time.sleep(0.5)
