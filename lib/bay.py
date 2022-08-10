####
# Cobra Bay - Bay
#
# Takes raw sensor data and interprets bay status.
# NOTE: This class does all calculations in metric. Any unit conversion is done in the display class.
####

####
#
# Class output type: 'dict'
# 'range' - range of the vehicle from the stopping point. NOT the sensor. Will be negative if overshot (ie: need to
#   back up) and None if vehicle is not detected/out of range.
# 'lateral' - List of dicts representing each lateral detection zone, ordered closest to the stopping point to furthest.
#   Dict contains:
#       'size' - How far off the vehicle is from the ideal lateral position.
#       'direction' - Direction of the position deviance. 'L' or 'R', relative to the range sensor.
#       'status' - Which status this zone is in, as defined by the distances in the config, 'red','yellow','green'
#       'lateral_num' - Number of lateral zones. This is the expected number, while errors in sensors *may*
#       give a different numbers of entries in the lateral list.
#
####
import logging
from time import monotonic
from pint import Unit
from .nan import NaN


class Bay:
    # Initialization. Takes in the Bay component from the overall config.
    def __init__(self, bay_config, sensor_status):
        # Get the Bay logger.
        self._logger = logging.getLogger("cobrabay").getChild("bay")
        self._logger.info('Bay: Initializing...')
        
        # Store the configuration for future reference.
        self._config = bay_config
        self._name = bay_config['name']

        # Make sure the lateral zones are sorted by distance.
        self._config['lateral'] = sorted(self._config['lateral'], key=lambda x: x['intercept_range'])

        # Make a list of used sensors
        self._used_sensors = [self._config['range']['sensor']]
        for lateral in self._config['lateral']:
            self._used_sensors.append(lateral['sensor'])

        if not self._haveallsensors(sensor_status):
            self.state = 'unavailable'
        else:
            self.state = 'ready'
            
        self._logger.info('Bay: Initialization complete.')

        # Reset to initialize variables.
        self.reset()

    # Reset method, also used for initialization.
    def reset(self):
        # Initialize variables that should have starting values.
        self._previous_range = 1000000
        # Current motion state.
        self.motion = 'No Movement'
        # Dict to store processed sensors.
        self._sensors = {}
        # Set occupancy to unknown, since we don't have sensor data to know.
        self.occupied = 'unknown'
        # Presume we're ready. We're not rechecking sensor status.
        self.state = 'ready'

    def _haveallsensors(self, sensor_status):
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
        # IF we've gotten here without returning, then we must have all sensors.
        return True


        
    # Process the lateral detection areas. These are in order, closest to furthest.
    def _lateral(self, sensor_values):
        return_list = []
        for area in range(len(self._config['lateral'])):
            # Check if the sensor actually has a value.
            if sensor_values[self._config['lateral'][area]['sensor']] is None:
                return_list.append('NP')
            # Check if the vehicle is close enough to trigger this lateral sensor. If so, evaluate the lateral position.
            elif sensor_values[self._config['range']['sensor']] <= self._config['lateral'][area]['intercept_range']:
                # Pass the area ID and required sensor for evaluation.
                return_list.append(self._lateralarea(area, sensor_values))
            else:
                # Put a Beyond Range marker and move on.
                return_list.append('Beyond Range')
        return return_list
        
    # Create an adjusted range
    def _adjusted_range(self, sensor_range=None):
        # We never really should get this, but if we do, turn around and return None back, beacuse, WTF?
        if sensor_range is None or isinstance(sensor_range, NaN):
            return NaN("No sensor reading")
        # If detected distance is beyond the reliable detection distance, return a "Beyond Range message.
        if sensor_range > self._config['range']['dist_max']:
            return NaN("Beyond range")
        else:
            adjusted_range = sensor_range - self._config['range']['dist_stop']
            if adjusted_range <= 0:
                # This means you've hit the sensor!
                self.state = "crashed"
                return NaN("CRASH!")
            else:
                return adjusted_range

    # Get range and range percentage out of the sensor values.
    def _range_values(self, sensor_values):
        # Find out if the range sensor exists in the sensor values dict
        if self._config['range']['sensor'] not in sensor_values:
            range = None
            range_pct = None
        else:
            # Get the adjusted range of the sensor.
            range = self._adjusted_range(sensor_values[self._config['range']['sensor']])
            # When adjusted range can't get a reasonable value, it will return a NaN object. So if it's *not* a NaN,
            # we can calculate a percentage properly.
            if not isinstance(range, NaN):
                # Calculate a percentage, rounded to two decimal places. This force converts to centimeters, since all
                # sensors return centimeters, and the float conversion ensures this returns as a float, not as an
                # undimensioned quantity.
                range_pct = round(float(range / self._config['range']['dist_max'].to("cm")) * 100, 2)
            else:
                range_pct = NaN("No range.")
        return range, range_pct

    # Method called when docking is complete.
    def complete(self):
        # Set bay state to ready, since the bay can be ready to *undock*
        self.state = 'ready'
        # Bay is occupied, by definition, since docking is complete.
        self.occupied = 'occupied'
        # Likewise, motion has to be stopped, you shouldn't be driving in a completed bay.
        self.motion = 'still'

    # Called when there are new sensor values to be interpreted against the bay's parameters.
    def update(self, sensor_values, verify=False):
        # Catch bad states. This *shouldn't* be needed, but make sure.
        if self.state == 'unavailable':
            # Don't allow sensors to be updated when the bay itself is unavailable.
            self._logger.error("Bay is not available")
            return
        elif self.state not in ('docking', 'undocking'):
            # Bay has to be set to docking or undocking before it can take a sensor update.
            self._logger.error("Cannot update when not docking. Must set to docking first.")
            return

        # Get range and range percentage. This will return a Unit if it's actually valid, and a
        # NaN object if it's something else
        range, range_pct = self._range_values(sensor_values)
        # The "verify" flag is used to run on a single sensor sweep. When that happens we can't calculate motion.
        # So if verify isn't set, figure out motion and update that.
        if not verify:

            # Update the bay motion state if values are being returned.
            if isinstance(range, Unit) and isinstance(range_pct, float):
                # Evaluate for vehicle movement. We allow for a little wobble.
                try:
                    range_change = self._position['range'] - range
                except TypeError:
                    pass
                else:
                    if range_change > 1:
                        self._last_move_time = monotonic()
                        if self._position['range'] > range:
                            self.motion = 'Approaching'
                        if self._position['range'] < range:
                            self.motion = 'Receding'
                    else:
                        try:
                            time_diff = monotonic() - self._last_move_time
                        except AttributeError:
                            time_diff = 0
                        if self._config['park_time'].to("s") <= time_diff:
                            self.motion = 'No Movement'

        # Update the bay position dict.
        self._sensors = dict(
            range=range,
            range_pct=range_pct,
            lateral=self._lateral(sensor_values),
            lateral_num=len(self._config['lateral']))

    # Get alignment quality indicators based on the current sensor status.
    def alignment(self):
        # Catch bad states. This *shouldn't* be needed, but make sure.
        if self.state == 'unavailable':
            # Don't allow sensors to be updated when the bay itself is unavailable.
            self._logger.error("Bay is not available")
            return
        elif self.state not in ('docking', 'undocking'):
            # Bay has to be set to docking or undocking before it can take a sensor update.
            self._logger.error("Cannot update when not docking. Must set to docking first.")
            return
        elif len(self._sensors) == 0:
            self._logger.error("Cannot rate alignment when no sensor data. Call update first.")
            return

        def _lateralarea(self, area, sensors):
            # self._logger.debug('Bay: Checking lateral area ' + str(area))
            # Create a dictionary for the return values
            return_dict = {}

            # Find out difference between ideal distance and reported distance.
            position_deviance = sensors[self._config['lateral'][area]['sensor']] - \
                                self._config['lateral'][area]['dist_ideal']

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
            elif self._config['lateral'][area]['ok_spread'] < abs(position_deviance) < \
                    self._config['lateral'][area]['warn_spread']:
                return_dict['status'] = 1
            # Way off, huge warning.
            elif abs(position_deviance) >= self._config['lateral'][area]['red_spread']:
                return_dict['status'] = 3
            # Notably off, warn yellow.
            elif abs(position_deviance) >= self._config['lateral'][area]['warn_spread']:
                return_dict['status'] = 2
            return return_dict

        alignment = {}

        return

    def _alignment_grade(self):
        pass

    @property
    def occupied(self):
        '''
        Occupancy of the bay.

        Can be one of three states: 'occupied', 'vacant' or 'unknown'.

        :returns: bay occupancy state
        :rtype: String
        '''
        return self._occupied

    @occupied.setter
    def occupied(self, value):
        self._occupied = value

    @property
    def sensor_list(self):
        return self._used_sensors

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        if value not in ("docking","ready","unavailable","crashed"):
            raise ValueError("Requested state '{}' is not a valid bay state.".format(value))
        if value == 'docking' and self.occupied == 'occupied':
            raise RuntimeError('Cannot dock while already occupied!')
        self._state = value

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, value):
        self._position = value

    @property
    def motion(self):
        '''
        Is motion detected by the set of sensors?

        :return: Motion detect by sensors?
        :rtype: String
        '''
        return self._motion

    @motion.setter
    def motion(self, value):
        self._motion = value

    # Property to make it easier to test for lateral config. This is used downstream in display and network
    @property
    def lateral(self):
        if len(self._config['lateral']) > 0:
            return True
        else:
            return False
