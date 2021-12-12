####
# Cobra Bay Main
####

# Sys class so we can gracefully, properly bomb out if needed.
import sys

# Experimental asyncio support so we can keep updating the display while sensors update.
import asyncio

# Import the other CobraBay classes
from .display import Display
from .network import Network
from .sensors import Sensors

class CobraBay():
    def __init__(self):
        print("CobraBay initializing...")
        # Put config file loading here later, eventually.
        self.config = {
            'units': 'imperial', # Set to 'imperial' for feet/inches. Otherwise defaults to metric.
            'max_detect_range': 276, 
            'speed_limit': 5, # Treat jumps in range over this rate as spurious. Either MPH or KPH, depending on units.
            'sensor_pacing': 0.5, # Time in seconds between each ultrasonic sensor ping, to prevent echos.
            'bay': { # Dimensions of the parking bay. Either inches or cm, depending on units setting.
                'detect_range': 276, # Range where tracking should start.
                'park_range': 54,# Distance where the car should stop. Probably shouldn't be zero!
                'height': 46 , # Distance from ceiling to floor.
                'vehicle_height': 24 # How tall the vehicle is?
                },
            'sensors': {
                'center': {'type': 'vl53', 'address': 0x29, 'distance_mode': 'long', 'timing_budget': 50},
                #'sonic_aw': {'type': 'hcsr04', 'board': 0x58, 'trigger': 1, 'echo': 2, 'timeout': 0.5 },
                'left': {'type': 'hcsr04', 'board': 'local', 'trigger': 0, 'echo': 1, 'timeout': 0.5 },
                'right': {'type': 'hcsr04', 'board': 'local', 'trigger': 12, 'echo': 13, 'timeout': 0.5 }
                },
            'network': True
        }
        
        # Convert dimensions from inches to cm if necessary.
        if self.config['units'] == 'imperial':
            for option in ('detect_range','park_range','height','vehicle_height'):
                self.config['bay'][option] = self.config['bay'][option] * 2.54

        # Create sensor object
        self.sensors = Sensors(self.config)
        # Create Display object
        self.display = Display(self.config)

        print("Initialized! Ready for Launch!")
        
    # Start sensors and display to guide parking.
    async def Dock(self):
        # Start the VL53 sensors ranging
        self.sensors.VL53('start')
        while True:
            sensor_data = {}
            task_sensors_hcsr04 = asyncio.create_task(self.sensors.Sweep(sensor_data,'hcsr04'))
            task_sensors_vl53 = asyncio.create_task(self.sensors.Sweep(sensor_data,'vl53'))
            task_display = asyncio.create_task(self.display.UpdateDisplay(sensor_data))
            await asyncio.gather(task_sensors_vl53, task_display)
                
    # Complete parking, turn off display and shut down sensors.
    async def PowerDown(self):
        # Get all the current tasks, except ourself.
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        # Cancel all the running coroutines. This will inherently stop all the ultrasound sensors.
        for task in tasks:
            task.cancel()
        # Explicitly stop any vl53 sensors, which range on their own.
        self.sensors.VL53('stop')
        # Release the display so it can be properly reinitialized later.
        displayio.release_displays()
