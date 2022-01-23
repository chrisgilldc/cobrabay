####
# Cobra Bay - Main
####

# Sys class so we can gracefully, properly bomb out if needed.
import sys

# Experimental asyncio support so we can keep updating the display while sensors update.
import asyncio

# Import the other CobraBay classes
from .bay import Bay
from .display import Display
#from cobrabay import Network
from .sensors import Sensors

class CobraBay():
    def __init__(self,config):
        print("CobraBay initializing...")
        # check for all basic options.
        for option in ('global','sensors','bay'):
            if option not in config:
                print("Configuration does not include required section: '" + option + "'")
                sys.exit(1)
        # Make sure at least one sensor exists.
        if len(config) == 0:
            print("Must define at least one sensor, otherwise what are we doing here?")
            sys.exit(1)
        # Make sure sensors are assigned.
        if 'sensor' not in config['bay']['range']:
                print("Error with range configuration.")
                print("No sensor assigned.")
                sys.exit(1)            
        for index in range(len(config['bay']['lateral'])):
            if 'sensor' not in config['bay']['lateral'][index]:
                print("Error with lateral zone '" + str(index) + "'.")
                print("Lateral zone must have sensor assigned.")
                sys.exit(1)

        # Basic checks passed. Good enough! Assign it.
        self.config = config

        # General Processing
        # All internal work is done in metric.
        # Convert dimensions from inches to cm if necessary.
        if self.config['global']['units'] == 'imperial':
            # Range distance options to convert
            for option in ('dist_max','dist_stop'):
                self.config['bay']['range'][option] = self.config['bay']['range'][option] * 2.54
            # Lateral option distance options to convert
            for index in range(len(self.config['bay']['lateral'])):
                for option in ('intercept_range','ok_spread','warn_spread','red_spread'):
                    self.config['bay']['lateral'][index][option] = self.config['bay']['lateral'][index][option] * 2.54
        else:
            # If we're defaulting to metric, make sure it's explicit set for later testing.
            self.config['units'] = 'metric'

        # Create master sensor object to hold all necessary sensor sub-objects.
        self.sensors = Sensors(self.config)
        print("Sensors created...")
        print(self.sensors.sensors)
        # Create Display object
        print("Creating display...")
        self.display = Display(self.config)

        print("Initialized! Ready for Launch!")
        
    # Start sensors and display to guide parking.
    async def Dock(self):
        # Start the VL53 sensors ranging
        self.sensors.VL53('start')
        while True:
            sensor_data = {}
            bay_state = {}
            task_sensors_hcsr04 = asyncio.create_task(self.sensors.Sweep(sensor_data,'hcsr04'))
            task_sensors_nonus = asyncio.create_task(self.sensors.Sweep(sensor_data,['vl53','synth']))
            task_bay = asyncio.create_task(self.bay.Update(bay_state,sensor_data))
            #task_display = asyncio.create_task(self.display.UpdateDisplay(sensor_data))
            await asyncio.gather(task_sensors_hcsr04,task_sensors_nonus,task_display)

                
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
