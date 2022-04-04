####
# Cobra Bay - Bay
#
# Takes raw sensor data and interprets bay status.
# NOTE: This class does all calculations in metric. Any unit conversion is done in the display class.
####

####
#
# Class output type: 'dict'
# 'range' - range of the vehicle from the stopping point. NOT the sensor. Will be negative if overshot (ie: need to back up)
#   and None if vehicle is not detected/out of range.
# 'lateral' - List of dicts representing each lateral detection zone, ordered closest to the stopping point to furthest. Dict contains:
#   'size' - How far off the vehicle is from the ideal lateral position.
#   'direction' - Direction of the position deviance. 'L' or 'R', relative to the range sensor.
#   'status' - Which status this zone is in, as defined by the distances in the config, 'red','yellow','green'
# 'lateral_num' - Number of lateral zones. This is the true expected number, while errors in sensors *may* give a different
#   numbers of entries in the lateral list.
#
####

import adafruit_logging as logging

class Bay:
    # Initialization. Takes in the Bay component from the overall config.
    def __init__(self,bay_config,sensor_status):
        # Get the Bay logger.
        self._logger = logging.getLogger('bay')
        self._logger.info('Bay: Initializing...')
        
        # Store the configuration for future reference.
        self._config = bay_config
 
        # Bay State
        self._bay_state = 'init'
 
        # Make sure the lateral zones are sorted by distance.
        self._config['lateral'] = sorted(self._config['lateral'], key=lambda x: x['intercept_range'])

        # Create starting state for all areas, so nothing returns empty.
        #self.state = []
        #i = 1
        #while i <= len(self._config['lateral']):
        #    self.state.append({ 'size': 0, 'direction': 'N', 'status': 0 })
        #    i += 1

        # Make a list of used sensors
        self._used_sensors = [self._config['range']['sensor']]
        for lateral in self._config['lateral']:
            self._used_sensors.append(lateral['sensor'])

        if not self._HaveAllSensors(sensor_status):
            self._bay_state = 'unavailable'
        else:
            self._bay_state = 'ready'
            
        self._logger.info('Bay: Initialization complete.')

    def _HaveAllSensors(self,sensor_status):
        for sensor in self._used_sensors:
            self._logger.debug('Bay: Checking sensor: ' + str(sensor))
            # If we can't find a sensor, or it's unavailable, return False immediately.
            if sensor not in sensor_status:
                self._logger.debug('Bay: Not found, returning false.')
                return False
            elif sensor_status[sensor] == 'unavailable':
                self._logger.debug('Bay: unavailable, returning false.')
                return False
            # If we find an available sensor, we can continue.
            elif sensor_status[sensor] == 'available':
                self._logger.debug('Bay: available, returning true')
                pass
        # IF we've gotten here without returning, then we must have all sensors.
        return True

    def _LateralArea(self,area,sensors):
        self._logger.debug('Bay: Checking lateral area ' + str(area))
        # Create a dictionary for the return values
        return_dict = {}

        # Find out difference between ideal distance and reported distance.
        position_deviance = sensors[self._config['lateral'][area]['sensor']] - self._config['lateral'][area]['dist_ideal']

        # Report the absolute deviation from ideal.
        return_dict['size'] = abs(position_deviance)
        
        # Report the direction of any deviation
        if position_deviance == 0:
            return_dict['direction'] = None
        # Deviance away from the sensor.
        elif position_deviance > 0:
            if self._config['lateral'][area]['side'] == 'L':
                return_dict['direction'] = 'R'
            else:
                return_dict['direction'] = 'L'
        # Deviance towards the sensor.
        elif position_deviance < 0:
            if self._config['lateral'][area]['side'] == 'L':
                return_dict['direction'] = 'L'
            else:
                return_dict['direction'] = 'R'
                
        # Classify the status based on the configured warning zones.
        # Within the 'dead zone', no report is given, it's treated as being spot on.
        if abs(position_deviance) <= self._config['lateral'][area]['ok_spread']:
            return_dict['status'] = 0
        # Between the dead zone and the warning zone, we show white, an indicator but nothing serious.
        elif self._config['lateral'][area]['ok_spread'] < abs(position_deviance) < self._config['lateral'][area]['warn_spread']:
            return_dict['status'] = 1
        # Way off, huge warning.
        elif abs(position_deviance) >= self._config['lateral'][area]['red_spread']:
            return_dict['status'] = 3
        # Notably off, warn yellow.
        elif abs(position_deviance) >= self._config['lateral'][area]['warn_spread']:
            return_dict['status'] = 2
   
        return return_dict
        
    # Process the lateral detection areas. These are in order, closest to furthest.
    def _Lateral(self,sensor_values):
        self._logger.debug('Bay: Checking latera areas.')
        return_list = []
        for area in range(len(self._config['lateral'])):
            # Check if the sensor actually has a value.
            if sensor_values[self._config['lateral'][area]['sensor']] is None:
                return_list.append('NP')
            # Check if the vehicle is close enough to trigger this lateral sensor. If so, evaluate the lateral position, otherwise, ignore.
            elif sensor_values[self._config['range']['sensor']] <= self._config['lateral'][area]['intercept_range']:
                # Pass the area ID and required sensor for evaluation.
                return_list.append(self._LateralArea(area,sensor_values))
            else:
                # Put a Beyond Range marker and move on.
                return_list.append('BR')
        return return_list
        
    # Create an adjusted range
    def _AdjustedRange(self,range = None):
        # We never really should get this, but if we do, turn around and return None back, beacuse, WTF?
        if range is None:
            return (None, None)
        # If detected distance is beyond the reliable detection distance, return 'BR'
        if range > self._config['range']['dist_max']:
            return ('BR', None)
        else:
            adjusted_range = range - self._config['range']['dist_stop']
            range_pct = ( adjusted_range / self._config['range']['dist_max'] )
            return ( adjusted_range, range_pct )
            
    def State(self,sensor_states = None):
        # If we're given new sensor states, do a recheck here.
        if sensor_states is not None:
            pass
        return self._bay_state
            
    # Called when the main loop has updated sensor values the bay needs to interpret.
    def Update(self,sensor_values):
        if self._bay_state == 'unavailable':
            self._logger.debug('Bay: Bay state is unavailable, returning None')
            return None
        else:
            range, range_pct = (None, None) if self._config['range']['sensor'] not in sensor_values else self._AdjustedRange(sensor_values[self._config['range']['sensor']])
            bay_state = {
                'range': range,
                'range_pct': range_pct,
                'lateral': self._Lateral(sensor_values),
                'lateral_num': len(self._config['lateral'])
                }
            return bay_state