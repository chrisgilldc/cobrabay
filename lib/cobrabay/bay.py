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

class Bay:
    # Initialization. Takes in the Bay component from the overall config.
    def __init__(self,bay_config):
        # Store the configuration for future reference.
        self.config = bay_config
 
        ## Process range detection.
        # Create a list to store how many cycles we've had to hold data
        self.lateral_cycles = []
 
        # Make sure the lateral zones are sorted by distance.
        self.config['lateral'] = sorted(self.config['lateral'], key=lambda x: x['intercept_range'])

        # Create starting state for all areas, so nothing returns empty.
        self.state = []
        i = 1
        while i <= len(self.config['lateral']):
            self.state.append({ 'size': 0, 'direction': 'N', 'status': 0 })
            i += 1

        print(self.config)
        print(self.state)

    def _LateralZone(self,sensor):
        pass

    # Process the lateral detection areas. These are in order, closest to furthest.
    def _Lateral(self,sensor_values):
        return_list = []
        for index in range(len(self.config['lateral'])):
            return_dict = {}
            # If the main range sensor says the vehicle is close enough, start paying attention to this sensor.
            if self.sensor_values[self.config['range']['sensor']] <= self.config['lateral'][index]['intercept_range']:
                # Get the distance of the vehicle from the lateral sensor.
                try:
                    lat_position = sensor_values[self.config['lateral'][index]['sensor']]
                    print("Got lateral position: " + str(lat_position))
                except KeyError:
                    # If the sensor isn't reporting, we change it to a None and mark it as a non-reporting cycle
                    lat_position = None
                    self.lateral_status[index]['cycles'] += 1
                else:
                    # Set the cycles for this sensor back to zero.
                    self.lateral_status[index]['cycles'] = 0
                    # Determine the deviance side and magnitude based on this sensor report.
                    position_deviance = lat_position - self.config['lateral'][index]['dist_ideal']
                    print("Position deviance: " + str(position_deviance))
                    if position_deviance == 0:
                        deviance_side = None
                    # Deviance away from the sensor.
                    elif position_deviance > 0:
                        if self.config['lateral'][index]['side'] == 'P':
                            deviance_side = 'P'
                        else:
                            deviance_side = 'D'
                    # Deviance towards the sensor.
                    elif position_deviance < 0:
                        if self.config['lateral'][index]['side'] == 'D':
                            deviance_side = 'D'
                        else:
                            deviance_side = 'P'
                    print("Deviance side: " + str(deviance_side))

                    # How big is the deviance
                    # Within the 'dead zone', no report is given, it's treated as being spot on.
                    if abs(position_deviance) <= self.config['lateral'][index]['ok_spread']:
                        self.lateral_status[index]['deviance_side'] = 0
                    # Between the dead zone and the warning zone, we show white, an indicator but nothing serious.
                    elif self.config['lateral'][index]['ok_spread'] < abs(position_deviance) < self.config['lateral'][index]['warn_spread']:
                        self.lateral_status[index]['deviance_side'] = 1
                    # Way off, huge warning.
                    elif abs(position_deviance) >= self.config['lateral'][index]['red_spread']:
                        self.lateral_status[index]['deviance_side'] = 3
                    # Notably off, warn yellow.
                    elif abs(position_deviance) >= self.config['lateral'][index]['warn_spread']:
                        self.lateral_status[index]['deviance_side'] = 2
                        
                    print("Lateral status: " + str(self.lateral_status[index]['deviance_side']))

        
        return list
        
    # Create an adjusted range
    def _AdjustedRange(self,range = None):
        if range is None:
            return None
        else:
            return range - self.config['range']['dist_stop']
        
    # Called when the main loop has updated sensor values the bay needs to interpret.
    def Update(self,bay_state,sensor_values):
        
        bay_state = {
            'range': None if self.config['range']['sensor'] not in sensor_values else self.sensor_values[self.config['range']['sensor']],
            'lateral': 0,
            'lateral_num': len()
            }
