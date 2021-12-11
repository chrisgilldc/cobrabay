####
# Cobra Bay Sensors
####

import board, digitalio, sys, time, terminalio 
from adafruit_hcsr04 import HCSR04
from adafruit_aw9523 import AW9523
from adafruit_vl53l1x import VL53L1X

class Sensors:
    def __init__(self,config):
        # Holding dicts
        self.sensors = {} # Holds sensors.
        self.ranges = {} # ranges as reported by each individual sensor

        # Boards with GPIO pins. Always has 'local' as the native board. Can add additional boards (ie: AW9523) during initialization.
        self.gpio_boards = { 'local': board }
        
        # General config.
        self.config = {
            'sensor_pacing': 0.5
            }
        
        # Try to pull over values from the config array. If present, they'll overwrite the default. If not, the default stands.
        for config_value in ('sensor_pacing'):
            try:
                self.config[config_value] = config[config_value]
            except:
                pass
      
        # Process the sensors
        for sensor in config['sensors']:
            sensor_obj = self._CreateSensor(config['sensors'][sensor])
            self.sensors[sensor] = {
                'sensor_type': config['sensors'][sensor]['type'],
                'sensor_obj': sensor_obj }
                
    def _CreateSensor(self,options):
        # VL53L1X sensor.
        if options['type'] == 'vl53':
            # Create the sensor
            new_sensor = VL53L1X(board.I2C(),address=options['address'])
            # Set the defaults.
            new_sensor.distance_mode = 2
            new_sensor.timing_budget = 50
            if 'distance_mode' in options:
                if options['distance_mode'] == 'short':
                    new_sensor.distance_mode = 1
            if 'timing_budget' in options:
                if options['timing_budget'] in (15,20,33,50,100,200,500):
                    new_sensor.timing_budget = options['timing_budget']
                else:
                    print("Requested timing budget '" + str(options['timing_budget']) + "' not supported. Keeping default of 50ms.")

            new_sensor.start_ranging()

            return new_sensor
            
        # The HC-SR04 sensor, or US-100 in HC-SR04 compatibility mode
        elif options['type'] == 'hcsr04':
            
            # Confirm trigger, echo and board are set. These are *required*.
            for parameter in ('board','trigger','echo'):
                if parameter not in options:
                    raise ValueError
                    return parameter
            # Set a custom timeout if necessary
                if 'timeout' not in options:
                    timeout = 0.1
                else:
                    timeout = options['timeout']

            # Check for going via an AW9523, and set it up that way.
            if options['board'] in (0x58,0x59,0x5A,0x5B):
                # If the desired board hasn't been initialized yet, do so.
                if options['board'] not in self.gpio_boards:
                    self.gpio_boards[options['board']] = AW9523(board.I2C(),address=options['board'])
                # Now create the sensor.
                    new_sensor = HCSR04(
                        trigger_pin=self.gpio_boards[options['board']].get_pin(options['trigger']),
                        echo_pin=self.gpio_boards[options['board']].get_pin(options['echo']),
                        timeout=timeout)
                return new_sensor
            # If it's 'local', set up 
            elif options['board'] == 'local':
                # Use the exec call to convert the inbound pin number to the actual pin objects
                tp = eval("board.D{}".format(options['trigger']))
                ep = eval("board.D{}".format(options['echo']))
                return HCSR04(trigger_pin=tp,echo_pin=ep,timeout=timeout)
        else:
            print("Not a valid sensor type!")
            sys.exit(1)
            
    # Provides a uniform interface to access different types of sensors.
    def ReadSensor(self,sensor):
        if self.sensors[sensor]['sensor_type'] == 'hcsr04':
            try:
                return self.sensors[sensor]['sensor_obj'].distance
            except RuntimeError:
                # Catch timeouts and return None if it times out.
                return None
        if self.sensors[sensor]['sensor_type'] == 'vl53':
            return self.sensors[sensor]['sensor_obj'].distance

    # Utility function to just list 
    def ListSensors(self):
        return [k for k in self.sensors.keys()]
    
    # Return a value for all the sensors.
    def Sweep(self):
        return_data = {}
        for sensor in self.sensors:
            value = self.ReadSensor(sensor)
            # Only return non-none values
            if value is not None:
                return_data[sensor] = value
        return return_data