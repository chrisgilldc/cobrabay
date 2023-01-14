####
# CobraBay Detector
####
import pint.errors

from .sensors import CB_VL53L1X, TFMini, I2CSensor, SerialSensor
from pint import UnitRegistry, Quantity, DimensionalityError
from time import monotonic_ns
from functools import wraps
import logging
from collections import namedtuple

# Decorator method to check if a method is ready.
def check_ready(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        # Call the function.
        func(self, *args, **kwargs)
        # Now check for readiness and set ready if we are.
        for setting in self._settings['required']:
            if self._settings[setting] is None:
                self._ready = False
                return
        self._ready = True
        self._when_ready()

    return wrapper


# Use this decorator on any method that shouldn't be usable if the detector isn't marked ready. IE: don't let
# a value be read if the sensor isn't completely set up.


def only_if_ready(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.ready:
            raise RuntimeError("Detector is not fully configured, cannot read value yet. "
                               "Current settings:\n{}".format(self._settings))
        else:
            return func(self, *args, **kwargs)

    return wrapper


# Decorate these methods to have methods check the value history before doing another hit on the sensor.


def use_value_cache(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if len(self._history) > 0:
            time_delta = Quantity(monotonic_ns() - self._history[0][1], 'nanoseconds')
            # Get the timing of the sensor.
            sensor_timing = Quantity(self.measurement_time + " milliseconds")
            if time_delta < sensor_timing:  # If not enough time has passed, send back the most recent reading.
                value = self._history[0][0]
            else:
                value = self._sensor_obj.range
                # Add value to the history and truncate history to ten records.
                self._history.insert(0, value)
                self._history = self._history[:10]
        else:
            value = self._sensor_obj.range
        # Send whichever value it is into the function.
        return func(self, value)

    return wrapper


# This decorator is used for methods that rely on sensor data. If the sensor data is determined to be stale, it will
# trigger a new sensor read prior to executing the method.


def read_if_stale(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        read_sensor = False
        # If
        if len(self._history) > 0:
            # Time difference between now and the most recent read.
            time_delta = monotonic_ns() - self._history[0][1]
            if time_delta > 1000000000:  # 1s is too long, read the sensor.
                read_sensor = True
        # If we have no history, ie: at startup, go ahead and read.
        else:
            read_sensor = True

        # If flag is set, read the sensor and put its value into the history.
        if read_sensor:
            value = self._sensor_obj.range
            self._logger.debug("Triggered sensor reading. Got: {}".format(value))
            # Add value to the history and truncate history to ten records.
            self._history.insert(0, (value, monotonic_ns()))
            self._history = self._history[:10]

        # Send whichever value it is into the function.
        return func(self)

    return wrapper


class Detector:
    def __init__(self, config_obj, detector_id):
        # Request the settings dict from the config object.
        self._settings = config_obj.detector(detector_id)
        # Create a logger.
        self._logger = logging.getLogger("CobraBay").getChild("Detector").getChild(self._settings['name'])
        self._logger.setLevel(config_obj.get_loglevel(detector_id,mod_type='detector'))
        # A unit registry
        self._ureg = UnitRegistry()
        # Is the detector ready for use?
        self._ready = False
        # Measurement offset. We start this at zero, even though that's probably ridiculous!
        self._settings['offset'] = Quantity("0 cm")
        # List to keep the history of sensor readings. This is used for some methods.
        self._history = []

    # Value will return the adjusted reading from the sensor.
    @property
    @read_if_stale
    def value(self):
        raise NotImplementedError

    # Assess the quality of the sensor reading.
    @property
    @read_if_stale
    def quality(self):
        raise NotImplementedError

    # These properties and methods are common to all detectors.
    @property
    def ready(self):
        return self._ready

    # Measurement offset. All detectors will have this, even if it's 0.
    @property
    def offset(self):
        return self._settings['offset']

    @offset.setter
    @check_ready
    def offset(self, input):
        self._settings['offset'] = self._convert_value(input)

    @property
    def id(self):
        return self._settings['id']

    @property
    def name(self):
        return self._settings['name']

    # Convenience property to let upstream modules check for the detector type. This disconnects
    # from the class name, because in the future we may have multiple kinds of 'range' or 'lateral' detectors.
    @property
    def detector_type(self):
        return type(self).__name__.lower()

    # Utility method to convert into quantities.
    @staticmethod
    def _convert_value(input_value):
        # If it's already a quantity, return it right away.
        if isinstance(input_value, Quantity):
            return input_value
        elif isinstance(input_value, str):
            return Quantity(input_value)
        else:
            raise ValueError("Not a parseable value!")

    # This method will get called by the readiness checker once the detector is ready.
    # If the detector has specific additional work to do on becoming ready, override this method and put it here.
    def _when_ready(self):
        pass


# Single Detectors add wrappers around a single sensor. Sensor arrays are not currently supported, but may be in the
# future.
class SingleDetector(Detector):
    def __init__(self, config_obj, detector_id):
        super().__init__(config_obj, detector_id)
        self._logger.debug("Creating sensor object using options: {}".format(self._settings['sensor']))
        if self._settings['sensor']['type'] == 'VL53L1X':
            # Create the sensor object using provided settings.
            self._sensor_obj = CB_VL53L1X(self._settings['sensor'])
        elif self._settings['sensor']['type'] == 'TFMini':
            self._sensor_obj = TFMini(self._settings['sensor'])
        else:
            raise ValueError("Detector {} trying to use unknown sensor type {}".format(
                self._settings['name'], self._settings['sensor']['type']))

    # Allow adjustment of timing.
    def timing(self, timing_input):
        # Make sure the timing input is a Quantity.
        timing_input = self._convert_value(timing_input)
        # Sensor takes measurement time in microseconds.
        mt = timing_input.to('microseconds').magnitude
        self._sensor_obj.measurement_time = mt

    # Called when the system needs to turn this sensor on.
    def activate(self):
        self._sensor_obj.start_ranging()

    # Called when the system needs to go into idle mode and turn the sensor off.
    def deactivate(self):
        self._sensor_obj.stop_ranging()

    # Called *only* when the system is exiting. This is currently an alias for deactivating, but other types
    # of hardware may need other behavior, ie: freeing devices.
    def shutdown(self):
        self.deactivate()

    # Debugging methods to let the main system know a few things about the attached sensor.

    @property
    def sensor_type(self):
        return type(self._sensor_obj)

    @property
    def sensor_interface(self):
        iface_info = namedtuple("iface_info", ['type', 'addr'])
        if isinstance(self._sensor_obj, SerialSensor):
            iface = iface_info("serial", self._sensor_obj.serial_port)
            return iface
        elif isinstance(self._sensor_obj, I2CSensor):
            iface = iface_info("i2c", self._sensor_obj.i2c_address)
            return iface
        return None

# Detector that measures range progress.
class Range(SingleDetector):
    def __init__(self, config_obj, detector_id):
        super().__init__(config_obj, detector_id)
        self._logger.info("Initializing Range detector.")
        self._settings['pct_crit'] = 5 / 100
        self._settings['pct_warn'] = 10 / 100

    # Return the adjusted reading of the sensor.
    @property
    @read_if_stale
    def value(self):
        self._logger.debug("Creating adjusted value from latest value: {}".format(self._history[0][0]))
        if isinstance(self._history[0][0], Quantity):
            return self._history[0][0] - self.offset
        elif self._history[0][0] is None:
            return None
        elif isinstance(self._history[0][0], str):
            if self._history[0][0] == 'No reading':
                return "No reading"
        else:
            return "Error"

    # Method to get the raw sensor reading. This is used to report upward for HA extended attributes.
    @property
    @read_if_stale
    def value_raw(self):
        self._logger.debug("Most recent reading is: {}".format(self._history[0][0]))
        if isinstance(self._history[0][0], Quantity):
            return self._history[0][0]
        elif self._history[0][0] is None:
            return "Unknown"
        elif isinstance(self._history[0][0], str):
            if self._history[0][0] == 'No reading':
                return "No reading"
        else:
            return "Error"

    # Assess the quality of the sensor
    @property
    @read_if_stale
    def quality(self):
        self._logger.debug("Creating quality from latest value: {}".format(self._history[0][0]))
        self._logger.debug("90% of bay depth is: {}".format(self._settings['bay_depth'] * .9))
        if isinstance(self._history[0][0], str):
            # A weak reading from the sensor almost certainly means the door is open and nothing is blocking.
            if self._history[0][0] == "Weak":
                return "Door open"
            else:
                return "Unknown"
        else:
            # You're about to hit the wall!
            if self._history[0][0] < Quantity("2 in"):
                return 'Emergency!'
            elif ( self._settings['bay_depth'] * 0.90 ) <= self._history[0][0]:
                self._logger.debug("Reading is more than 90% of bay depth ({})".format(self._settings['bay_depth'] * .9))
                return 'No object'
            # Now consider the adjusted values.
            elif self.value < 0 and abs(self.value) > self.spread_park:
                return 'Back up'
            elif abs(self.value) < self.spread_park:
                return 'Park'
            elif self.value <= self._settings['dist_crit']:
                return 'Final'
            elif self.value <= self._settings['dist_warn']:
                return 'Base'
            else:
                return 'OK'

    # Determine the rate of motion being measured by the detector.
    @property
    @read_if_stale
    def _movement(self):
        # Filter out non-Quantity sensor responses. We may want to keep them for other reasons, but can't average them.
        history = []
        for entry in self._history:
            if isinstance(entry[0], Quantity):
                history.append(entry)
        # If we don't have at least two data points, can't measure, return none.
        if len(history) < 2:
            return None
        elif history[0][0] == 'Weak':
            return None
        # If the sensor is reading beyond range, speed and direction can't be known, so return immediately.
        last_element = len(history)-1
        self._logger.debug("First history: {}".format(history[0]))
        self._logger.debug("Last history: {}".format(history[last_element]))
        try:
            net_dist = self._history[0][0] - history[last_element][0]
            net_time = Quantity(history[0][1] - history[last_element][1], 'nanoseconds').to('seconds')
        except pint.errors.DimensionalityError:
            # If we're trying to subtract a non-Quantity value, then return unknown for these.
            return None
        self._logger.debug("Moved {} in {}s".format(net_dist, net_time))
        speed = (net_dist / net_time).to('kph')
        # Since we've processed all this already, return all three values.
        return {'speed': speed, 'net_dist': net_dist, 'net_time': net_time }

    # Based on readings, is the vehicle in motion?
    @property
    @read_if_stale
    def motion(self):
        # Grab the movement
        movement = self._movement
        if movement is None:
            return "Unknown"
        elif abs(self._movement['net_dist']) > Quantity(self._settings['error_margin']):
            return True
        else:
            return False

    @property
    @read_if_stale
    def vector(self):
        # Grab the movement value.
        movement = self._movement
        # Determine a direction.
        if movement is None:
            # If movement couldn't be determined, we also can't determine vector, so this is unknown.
            return { "speed": "Unknown", "direction": "Unknown" }
        # Okay, not none, so has value!
        if movement['net_dist'] > Quantity(self._settings['error_margin']):
            return {'speed': abs(movement['speed']), 'direction': 'forward' }
        elif movement['net_dist'] < (Quantity(self._settings['error_margin']) * -1):
            return {'speed': abs(movement['speed']), 'direction': 'reverse' }
        else:
            return {'speed': Quantity("0 kph"), 'direction': 'still' }

    # Gets called when the rangefinder has all settings and is being made ready for use.
    def _when_ready(self):
        # Calculate specific distances to use based on the percentages.
        self._derived_distances()

    # Allow dynamic distance mode changes to come from the bay. This is largely used for debugging.
    def distance_mode(self, input):
        try:
            self._sensor_obj.distance_mode = input
        except ValueError:
            print("Could not change distance mode to {}".format(input))

    @property
    def bay_depth(self):
        return self._settings['bay_depth']

    @bay_depth.setter
    @check_ready
    def bay_depth(self, input):
        self._settings['bay_depth'] = self._convert_value(input)

    @property
    def spread_park(self):
        return self._settings['spread_park']

    @spread_park.setter
    @check_ready
    def spread_park(self, input):
        self._settings['spread_park'] = self._convert_value(input)

    # Properties for warning and critical percentages. We take these are "normal" percentages (ie: 15.10) and convert
    # to decimal so it can be readily used for multiplication.
    @property
    def pct_warn(self):
        return self._settings['pct_warn'] * 100

    @pct_warn.setter
    @check_ready
    def pct_warn(self, input):
        self._settings['pct_warn'] = input / 100

    @property
    def pct_crit(self):
        return self._settings['pct_crit'] * 100

    @pct_crit.setter
    @check_ready
    def pct_crit(self, input):
        self._settings['pct_crit'] = input / 100

    # Pre-bake distances for warn and critical to make evaluations a little easier.
    def _derived_distances(self):
        adjusted_distance = self._settings['bay_depth'] - self._settings['offset']
        self._settings['dist_warn'] = adjusted_distance.magnitude * self.pct_warn * adjusted_distance.units
        self._settings['dist_crit'] = adjusted_distance.magnitude * self.pct_crit * adjusted_distance.units

    # Reference some properties upward to the parent class. This is necessary because properties aren't directly
    # inherented.

    @property
    def i2c_address(self):
        return super().i2c_address

    @property
    def offset(self):
        return super().offset

    @offset.setter
    def offset(self, input):
        super(Range, self.__class__).offset.fset(self, input)


# Detector for lateral position
class Lateral(SingleDetector):
    def __init__(self, config_obj, detector_id):
        super().__init__(config_obj, detector_id)

    @property
    @read_if_stale
    def value(self):
        self._logger.debug("Most recent reading is: {}".format(self._history[0][0]))
        if isinstance(self._history[0][0], Quantity):
            return self._history[0][0] - self.offset
        else:
            return None

    # Method to get the raw sensor reading. This is used to report upward for HA extended attributes.
    @property
    @read_if_stale
    def value_raw(self):
        self._logger.debug("Most recent reading is: {}".format(self._history[0][0]))
        if isinstance(self._history[0][0], Quantity):
            return self._history[0][0]
        else:
            return None

    @property
    @read_if_stale
    def quality(self):
        self._logger.debug("Assessing quality for value: {}".format(self.value))
        # Process quality if we get a quantity from the Detector.
        if isinstance(self.value, Quantity):
            self._logger.debug("Comparing to: \n\t{}\n\t{}".format(
                self.spread_ok, self.spread_warn))
            if self.value > Quantity('96 in'):
                # A standard vehicle width (in the US, at least) is 96 inches, so if we're reading something further
                # than that, it's not the vehicle in question (ie: a far wall, another vehicle, etc).
                qv = "No object"
            elif abs(self.value) <= self.spread_ok:
                qv = "OK"
            elif abs(self.value) <= self.spread_warn:
                qv = "Warning"
            elif abs(self.value) > self.spread_warn:
                qv = "Critical"
            else:
                # Total failure to return a value means the light didn't reflect off anything. That *probably* means
                # nothing is there, but it could be failing for other reasons.
                qv = "Unknown"
        else:
            qv = "Unknown"
        self._logger.debug("Quality returning {}".format(qv))
        return qv

    @property
    def ready(self):
        return self._ready

    @property
    def spread_ok(self):
        return self._settings['spread_ok']

    @spread_ok.setter
    @check_ready
    def spread_ok(self, m_input):
        self._settings['spread_ok'] = self._convert_value(m_input).to('cm')
        # Check to see if the detector is now ready.

    @property
    def spread_warn(self):
        return self._settings['spread_warn']

    @spread_warn.setter
    @check_ready
    def spread_warn(self, m_input):
        self._settings['spread_warn'] = self._convert_value(m_input).to('cm')

    @property
    def side(self):
        return self._settings['side']

    @side.setter
    @check_ready
    def side(self, m_input):
        if m_input.upper() not in ('R', 'L'):
            raise ValueError("Lateral side must be 'R' or 'L'")
        else:
            self._settings['side'] = m_input.upper()

    # Reference some properties upward to the parent class. This is necessary because properties aren't directly
    # inherented.

    @property
    def i2c_address(self):
        return super().i2c_address

    @property
    def offset(self):
        return super().offset

    @offset.setter
    @check_ready
    def offset(self, m_input):
        super(Lateral, self.__class__).offset.fset(self, m_input)
