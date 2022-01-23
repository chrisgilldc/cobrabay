####
# Cobra Bay - Sensors
#
# Reads in defined sensors
####

# Experimental asyncio support so we can keep updating the display while sensors update.
import asyncio

import board, digitalio, sys, time, terminalio 
from adafruit_hcsr04 import HCSR04
from adafruit_aw9523 import AW9523
from adafruit_vl53l1x import VL53L1X
from .synthsensor import SynthSensor

class Sensors:
    def __init__(self,config):
        # Holding dicts
        self.sensors = {} # Holds sensors.

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
            if sensor_obj is not None:
                self.sensors[sensor] = {
                    'type': config['sensors'][sensor]['type'],
                    'obj': sensor_obj }
                # For ultrasound sensors, add in the averaging rate and initialize buffer.
                if self.sensors[sensor]['type'] == 'hcsr04':
                    self.sensors[sensor]['avg'] = config['sensors'][sensor]['avg']
                    self.sensors[sensor]['queue'] = []

    def _CreateSensor(self,options):
        print(options)
        # VL53L1X sensor.
        if options['type'] == 'vl53':
            # Create the sensor
            try:
                new_sensor = VL53L1X(board.I2C(),address=options['address'])
            except Exception as e:
                print("VL53L1X sensor not available at address '" + str(options['address']) + "'. Ignoring.")
                return None
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

            # Make sure the GPIO board has been initialized.
            # This is already seeded with 'local', so that *always* works.
            # Since we only support AW9523 expansion boards(currently), 
            # then any missing board must be an AW9523.
            if options['board'] not in self.gpio_boards:
                try:
                    self.gpio_boards[options['board']] = AW9523(board.I2C(),address=options['board'])
                except Exception as e:
                    print("AW9523 not available at address '" + str(options['board']) + "'. Skipping.")
                    return None
                    
            # Create HCSR04 object with the correct pin syntax.
            
            # Pins on the AW9523
            if options['board'] in (0x58,0x59,0x5A,0x5B):
                new_sensor = HCSR04(
                    trigger_pin=self.gpio_boards[options['board']].get_pin(options['trigger']),
                    echo_pin=self.gpio_boards[options['board']].get_pin(options['echo']),
                    timeout=timeout)
            # 'Local' GPIO, directly on the board.
            elif options['board'] == 'local':
                # Use the exec call to convert the inbound pin number to the actual pin objects
                tp = eval("board.D{}".format(options['trigger']))
                ep = eval("board.D{}".format(options['echo']))
                new_sensor = HCSR04(trigger_pin=tp,echo_pin=ep,timeout=timeout)
            else:
                print("GPIO board '" + options['board'] + "' not valid!")
                sys.exit(1)
            return new_sensor

        # Synthetic sensors, IE: fake numbers to allow for testing.
        elif options['type'] == 'synth':
            return SynthSensor(options)
        else:
            print("Not a valid sensor type!")
            sys.exit(1)
            
    # Provides a uniform interface to access different types of sensors.
    def _ReadSensor(self,sensor):
        if self.sensors[sensor]['type'] == 'hcsr04':
            try:
                distance = self.sensors[sensor]['obj'].distance
            except RuntimeError:
                # Catch timeouts and return None if it times out.
                return None
            # Sensor can be wonky and return 0, even when it doesn't strictly timeout.
            # Catch these and return None instead.
            if distance > 0:
                return distance
            else:
                return None
        if self.sensors[sensor]['type'] in ('vl53','synth'):
            distance = self.sensors[sensor]['obj'].distance
            return distance

    # Utility function to just list all the sensors found.
    def ListSensors(self):
        return [k for k in self.sensors.keys()]

    def VL53(self,action):
        if action not in ('start','stop'):
            print("Invalid action '" + action + "' requested for VL53.")
            sys.exit(1)
        else:
            for sensor in self.sensors:
                if self.sensors[sensor]['type'] == 'vl53':
                    if action == 'start':
                        self.sensors[sensor]['obj'].start_ranging()
                    if action == 'stop':
                        self.sensors[sensor]['obj'].stop_ranging()

    async def Sweep(self,sensor_data,type = ['all'],):
        for sensor in self.sensors:
            if self.sensors[sensor]['type'] in type or type == 'all':
                # Get the raw sensor value.
                value = self._ReadSensor(sensor)
                if type == 'hcsr04':
                    # Reject times when the sensor returns none or zero, because that's almost certainly a glitch. 
                    # You should never really be right up against the sensor!
                    if value != 0 and value is not None:
                        # If queue is full, remove the oldest element.
                        if len(self.sensors[sensor]['queue']) >= self.sensors[sensor]['avg']:
                            del self.sensors[sensor]['queue'][0]
                        # Now add the new value and average.
                        self.sensors[sensor]['queue'].append(value)
                        # Calculate the average
                        avg_value = sum(self.sensors[sensor]['queue']) / self.sensors[sensor]['avg']
                        # Send the average back.
                        sensor_data[sensor] = avg_value
                    # Now ensure wait before the next check to prevent ultrasound interference.
                    await asyncio.sleep(self.config['sensor_pacing'])
                    #time.sleep(self.config['sensor_pacing'])
                else:
                    # For non-ultrasound sensors, send it directly back.
                    sensor_data[sensor] = value

                # Only return non-none values
                if value is not None:
                    sensor_data[sensor] = value
        await asyncio.sleep(0)