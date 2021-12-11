####
# Cobra Bay Main
####

# Sys class so we can gracefully, properly bomb out if needed.
import sys

# Import the other CobraBay classes
from .display import Display
from .network import Network
from .sensors import Sensors

class CobraBay():
    def __init__(self):
        print("CobraBay Initializing!")
        # Put config file loading here later, eventually.
        self.config = {
            'units': 'imperial', # Set to 'imperial' for feet/inches. Otherwise defaults to metric.
            'max_detect_range': 276, # Range where tracking starts. Centimeters or Inches, depending on units.
            'speed_limit': 5, # Treat jumps in range over this rate as spurious. Either MPH or KPH, depending on units.
            'sensor_pacing': 0.5, # Time in seconds between each sensor ping, to prevent echos.
            'sensors': {
                'center': {'type': 'vl53', 'address': 0x29, 'distance_mode': 'long', 'timing_budget': 50},
                #'sonic_test_r': {'type': 'hcsr04', 'board': 0x58, 'trigger': 1, 'echo': 2, 'timeout': 0.5 },
                'left': {'type': 'hcsr04', 'board': 'local', 'trigger': 0, 'echo': 1, 'timeout': 1 }
                },
            'network': False
        }
        
        # Convert max detect range if necessary
        if self.config['units'] == 'imperial':
            self.config['max_detect_range'] = self.config['max_detect_range'] * 2.54
        
        # Create sensor object
        self.sensors = Sensors(self.config)
        # Create Display object
        self.display = Display(self.config)

    def Run(self):
        while True:
            self.display.UpdateDisplay()