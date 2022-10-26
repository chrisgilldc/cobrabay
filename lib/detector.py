####
# CobraBay Detector
####

from .sensor import VL53L1X as CB_VL53L1X
from pint import UnitRegistry, Quantity
from statistics import mean
from time import monotonic_ns
from functools import wraps


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
# a value be read if
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
                value = self.value
        else:
            value = self.value
        # Send whichever value it is into the function.
        return func(self, value)
    return wrapper

class Detector:
    def __init__(self, detector_id, detector_name):
        # A unit registry
        self._ureg = UnitRegistry()
        # Is the detector ready for use?
        self._ready = False
        # Settings for the detector. Starts as an empty dict.
        self._settings = { 'detector_id': detector_id, 'detector_name': detector_name }
        # What settings are required before the detector can be used? Must be set by the subclass.
        self._required_settings = None
        # Measurement offset. We start this at zero, even though that's probably ridiculous!
        self._settings['offset'] = Quantity("0 cm")
        # List to keep the history of sensor readings. This is used for some methods.
        self._history = []

    # All of the below methods should be overridden and are included here for direction.
    def _setup_detector(self, settings):
        raise NotImplementedError

    # value will return the reading from the detector.
    def value(self):
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

    # Utility method to convert into quantities.
    def _convert_value(self, input_value):
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

# Single Detectors add wrappers around a single VL53L1X sensor.
class SingleDetector(Detector):
    def __init__(self, detector_id, detector_name, board_options):
        super().__init__(detector_id, detector_name)
        # Create the sense object using provided settings.
        self._sensor_obj = CB_VL53L1X(board_options)

    @property
    def value(self):
        raise NotImplemented

    # Allow adjustment of timing.
    def timing(self, timing_input):
        # Make sure the timing input is a Quantity.
        timing_input = self._convert_value(timing_input)
        # Sensor takes measurement time in microseconds.
        mt = timing_input.to('microseconds').magnitude
        self._sensor_obj.measurement_time = mt

    # Pass-through of the I2c address, for debugging.
    @property
    def i2c_address(self):
        return self._sensor_obj.i2c_address

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


# Detector that measures range progress.
class Range(SingleDetector):
    def __init__(self, detector_id, detector_name, board_options):
        super().__init__(detector_id, detector_name, board_options)
        self._required_settings = ['offset', 'bay_depth', 'spread_park', 'pct_warn', 'pct_crit']
        for setting in self._required_settings:
            self._settings[setting] = None
        # Default the warn and critical percentages.
        self._settings['pct_crit'] = 5 / 100
        self._settings['pct_warn'] = 10 / 100

    @property
    def value(self):
        # Read the sensor and put it at the start of the list, along with a timestamp.
        self._history.insert(0, [self._sensor_obj.range, monotonic_ns()])
        # Make sure the history list is always five elements, so we don't just grow this ridiculously.
        self._history = self._history[:5]
        # Return that reading, minus the offset.
        return self._history[0][0] - self.offset

    # Quality assesses where the vehicle is on their approach relative to the depth of the bay and the stop location.
    @property
    @only_if_ready
    def quality(self):
        # Get the value once. Will use either cached or uncached
        value = self.value
        # You're about to hit the wall!
        if ( value + self.offset ) < Quantity("2 in"):
            return 'emerg'
        # Overshot by too much, back up.
        elif value < 0 and abs(value) > self.spread_park:
            return 'back-up'
        elif abs(value) < self.spread_park:
            return 'park'
        elif value <= self._settings['dist_crit']:
            return 'crit'
        elif value <= self._settings['dist_warn']:
            return 'warn'
        else:
            return 'ok'

    @property
    @only_if_ready
    def vector(self):
        # Only consider readings within the past 10s. This makes sure nothing bogus gets in here for wild readings.
        readings = []
        for reading in self._history:
            if monotonic_ns() - reading[1] <= 10000000000:
                readings.append(reading)
        # print("Calculated readings: {}".format(readings))
        i = 0
        vectors = []
        while i < len(readings):
            try:
                d = ( self._history[i][0] - self._history[i+1][0] )
            except IndexError:
                i +=1
            else:
                print("Calculated distance: {}".format(d))
                t = Quantity(self._history[i+1][1] - self._history[i][1],'nanoseconds').to('seconds')
                print("Calculated time: {}".format(t))
                v = d/t
                vectors.append(v)
                print("Calculated velocity: {}".format(v))
                i += 1
        net_vector = mean(vectors)
        if net_vector.magnitude == 0:
            direction = 'still'
            speed = net_vector
        elif net_vector.magnitude > 0:
            direction = 'forward'
            speed = net_vector
        elif net_vector.magnitude < 0:
            # Make the speed positive, we'll report direction separately.
            direction = 'reverse'
            speed = net_vector * -1
        return {'speed': speed, 'direction': direction}

    # Based on readings, is the vehicle in motion?
    @property
    @only_if_ready
    def motion(self):
        if self.vector['speed'] > 0:
            return True
        else:
            return False


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
    def offset(self,input):
        super(Range, self.__class__).offset.fset(self, input)

# Detector for lateral position
class Lateral(SingleDetector):
    def __init__(self, detector_id, detector_name, board_options):
        super().__init__(detector_id, detector_name, board_options)
        # Initialize required elements as None. This lets us do a readiness check later.
        self._required_settings = ['offset', 'spread_ok', 'spread_warn', 'spread_crit', 'side']
        for setting in self._required_settings:
            self._settings[setting] = None

    @property
    def value(self):
        # Read the sensor and put it at the start of the list, along with a timestamp.
        self._history.insert(0, [self._sensor_obj.range, monotonic_ns()])
        # Make sure the history list is always five elements, so we don't just grow this ridiculously.
        self._history = self._history[:5]
        # Return that reading, minus the offset.
        if self._range_reading > self._settings['intercept']:
            return 'NI'
        elif self._history[0][0] < 0:
            return "UR"
        elif self._history[0][0] >= Quantity("96 in"):
            return "BR"
        else:
            return self._history[0][0] - self.offset

    @property
    @only_if_ready
    def quality(self):
        value = self.value
        # Process quality if we get a quantity from the Detector.
        if isinstance(value, Quantity):
            if abs(value) <= self.spread_ok:
                return "ok"
            elif abs(value) <= self.spread_warn:
                return "warn"
            elif abs(value) >= self.spread_crit:
                return "crit"
        # Otherwise, return the text value of the detector.
        else:
            return value

    @property
    def ready(self):
        return self._ready

    # The intercept distance of this lateral detector.
    @property
    def intercept(self):
        return self._settings['intercept']

    @intercept.setter
    def intercept(self, input):
        self._settings['intercept'] = self._convert_value(input)

    # Take in range readings from the bay.
    @property
    def range_reading(self):
        return self._range_reading

    @range_reading.setter
    def range_reading(self, input):
        self._range_reading = input

    @property
    def spread_ok(self):
        return self._settings['spread_ok']

    @spread_ok.setter
    @check_ready
    def spread_ok(self, input):
        self._settings['spread_ok'] = self._convert_value(input)
        # Check to see if the detector is now ready.

    @property
    def spread_warn(self):
        return self._settings['spread_warn']

    @spread_warn.setter
    @check_ready
    def spread_warn(self, input):
        self._settings['spread_warn'] = self._convert_value(input)
        # Check to see if the detector is now ready.

    @property
    def spread_crit(self):
        return self._settings['spread_crit']

    @spread_crit.setter
    @check_ready
    def spread_crit(self, input):
        self._settings['spread_crit'] = self._convert_value(input)
        # Check to see if the detector is now ready.

    @property
    def side(self):
        return self._settings['side']

    @side.setter
    @check_ready
    def side(self, input):
        if input.upper() not in ('R', 'L'):
            raise ValueError("Lateral side must be 'R' or 'L'")
        else:
            self._settings['side'] = input.upper()

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
    def offset(self,input):
        super(Lateral, self.__class__).offset.fset(self, input)