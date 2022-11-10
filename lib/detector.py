####
# CobraBay Detector
####

from .sensors import CB_VL53L1X, TFMini, I2CSensor, SerialSensor
from pint import UnitRegistry, Quantity, DimensionalityError
from statistics import mean
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
        for setting in self._required_settings:
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
    def __init__(self, detector_id, detector_name):
        # Create a logger.
        self._logger = logging.getLogger("CobraBay").getChild("Detector").getChild(detector_name)
        # A unit registry
        self._ureg = UnitRegistry()
        # Is the detector ready for use?
        self._ready = False
        # Settings for the detector. Starts as an empty dict.
        self._settings = {'detector_id': detector_id, 'detector_name': detector_name}
        # What settings are required before the detector can be used? Must be set by the subclass.
        self._required_settings = None
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
        return self._settings['detector_id']

    @property
    def name(self):
        return self._settings['detector_name']

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
    def __init__(self, detector_id, detector_name, sensor_options):
        super().__init__(detector_id, detector_name)
        self._logger.debug("Creating sensor object using options: {}".format(sensor_options))
        if sensor_options['type'] == 'VL53L1X':
            # Create the sensor object using provided settings.
            self._sensor_obj = CB_VL53L1X(sensor_options)
        elif sensor_options['type'] == 'TFMini':
            self._sensor_obj = TFMini(sensor_options)
        else:
            raise ValueError("Detector {} trying to use unknown sensor type {}".format(
                detector_name, sensor_options['type']))

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
    def __init__(self, detector_id, detector_name, sensor_options):
        super().__init__(detector_id, detector_name, sensor_options)
        self.type = 'range'
        self._logger.info("Initializing Range detector.")
        self._required_settings = ['offset', 'bay_depth', 'spread_park', 'pct_warn', 'pct_crit']
        for setting in self._required_settings:
            self._settings[setting] = None
        # Default the warn and critical percentages.
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
            elif ( self.bay_depth * 0.90 ) <= self._history[0][0]:
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

    # Based on readings, is the vehicle in motion?
    @property
    @read_if_stale
    def motion(self):
        self._logger.debug("Trying to determine motion for detector: {}".format(self.name))
        self._logger.debug("Sensor history: {}".format(self._history))
        # Filter out non-Quantity sensor responses. We may want to keep them for other reasons, but can't average them.
        history = []
        for entry in self._history:
            if isinstance(entry[0], Quantity):
                history.append(entry)

    @property
    @read_if_stale
    def vector(self):
        return_dict = {'speed': Quantity("0 mph"), 'direction': None}
        return return_dict

    #     # If the sensor is reading beyond range, speed and direction can't be known, so return immediately.
    #     if isinstance(self._history[0][0], str):
    #         return { 'speed': 'unknown', 'direction': 'unknown'}
    #     # Only consider readings within the past 10s. This makes sure nothing bogus gets in here for wild readings.
    #     readings = []
    #     for reading in self._history:
    #         if monotonic_ns() - reading[1] <= 10000000000:
    #             readings.append(reading)
    #     i = 0
    #     vectors = []
    #     while i < len(readings):
    #         try:
    #             d = ( self._history[i][0] - self._history[i+1][0] )
    #         # If the index doesn't exist, or we can't subtract, move ahead.
    #         except IndexError:
    #             i += 1
    #         except TypeError:
    #             i +=1
    #         else:
    #             t = Quantity(self._history[i+1][1] - self._history[i][1],'nanoseconds').to('seconds')
    #             v = d/t
    #             vectors.append(v)
    #             i += 1
    #     net_vector = mean(vectors)
    #     if net_vector.magnitude == 0:
    #         direction = 'still'
    #         speed = net_vector
    #     elif net_vector.magnitude > 0:
    #         direction = 'forward'
    #         speed = net_vector
    #     elif net_vector.magnitude < 0:
    #         # Make the speed positive, we'll report direction separately.
    #         direction = 'reverse'
    #         speed = net_vector * -1
    #     return {'speed': speed, 'direction': direction}

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
    def __init__(self, detector_id, detector_name, sensor_options):
        super().__init__(detector_id, detector_name, sensor_options)
        # Initialize required elements as None. This lets us do a readiness check later.
        self._required_settings = ['offset', 'spread_ok', 'spread_warn', 'side']
        for setting in self._required_settings:
            self._settings[setting] = None
        self._range_reading = None

    @property
    @read_if_stale
    def value(self):
        self._logger.debug("Creating adjusted value from latest value: {}".format(self._history[0][0]))
        # Interpretation logic for the sensor value.
        # First check to see if we've been intercepted or not? IF we haven't, than any sensor reading is bogus.
        if isinstance(self._range_reading, Quantity):
            if self._range_reading > self.intercept:
                # If the vehicle hasn't reached this sensor yet, any reading should be discarded, return
                # not intercepted instead.
                return "Not intercepted"
            else:
                # We *should* be able to get a reading.
                if isinstance(self._history[0][0], Quantity):
                    return self._history[0][0] - self.offset
                else:
                    return "Unknown"
        else:
            # If we don't have a range value provided yet, then return unknown.
            return "Unknown"

    @property
    @read_if_stale
    def quality(self):
        self._logger.debug("Assessing quality for value: {}".format(self.value))
        # Process quality if we get a quantity from the Detector.
        if isinstance(self.value, Quantity):
            self._logger.debug("Comparing to: \n\t{}\n\t{}".format(
                self.spread_ok, self.spread_warn))
            if self.value > Quantity('96 in'):
                qv = "No object"
            elif abs(self.value) <= self.spread_ok:
                qv = "OK"
            elif abs(self.value) <= self.spread_warn:
                qv = "Warning"
            elif abs(self.value) > self.spread_warn:
                qv = "Critical"
            else:
                qv = "Unknown"
        else:
            qv = "Unknown"
        self._logger.debug("Quality returning {}".format(qv))
        return qv

    @property
    def ready(self):
        return self._ready

    # The intercept distance of this lateral detector.
    @property
    def intercept(self):
        return self._settings['intercept']

    @intercept.setter
    def intercept(self, m_input):
        self._settings['intercept'] = self._convert_value(m_input)

    # Take in range readings from the bay.
    @property
    def range_reading(self):
        return self._range_reading

    @range_reading.setter
    def range_reading(self, m_input):
        self._range_reading = m_input

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
