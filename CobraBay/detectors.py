####
# CobraBay Detector
####
import pint.errors

from .sensors import CB_VL53L1X, TFMini, I2CSensor, SerialSensor
# Import all the CobraBay Exceptions.
from .exceptions import CobraBayException, SensorValueException
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
        for setting in self._required:
            if getattr(self, setting) is None:
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
        # Assume we shouldn't read the sensor.
        if len(self._history) > 0:
            # Time difference between now and the most recent read.
            time_delta = monotonic_ns() - self._history[0][1]
            if time_delta > 1000000000:  # 1s is too long, read the sensor.
                read_sensor = True
        # If we have no history, ie: at startup, go ahead and read.
        else:
            read_sensor = True  ## If there's no history, read the sensor, we must be on startup.
        # If flag is set, read the sensor and put its value into the history.
        if read_sensor:
            try:
                value = self._sensor_obj.range
            except CobraBayException as e:
                # For our own exceptions, we can save and process.
                value = e
            except BaseException as e:
                # Anything else we have to re-raise.
                raise e
            self._logger.debug("Triggered sensor reading. Got: {} ({})".format(value, type(value)))
            # Add value to the history and truncate history to ten records.
            self._history.insert(0, (value, monotonic_ns()))
            self._history = self._history[:10]
        # Call the wrapped function.
        return func(self)

    return wrapper


class Detector:
    def __init__(self, detector_id, name, offset="0 cm", log_level="WARNING"):
        # Save parameters.
        self._detector_id = detector_id
        self._name = name
        # Create a logger.
        self._logger = logging.getLogger("CobraBay").getChild("Detector").getChild(self._name)
        self._logger.setLevel(log_level)
        # A unit registry
        self._ureg = UnitRegistry()
        # Is the detector ready for use?
        self._ready = False
        # Measurement offset. We start this at zero, even though that's probably ridiculous!
        self._offset = Quantity(offset)
        # List to keep the history of sensor readings. This is used for some methods.
        self._history = []

    # Value will return the adjusted reading from the sensor.
    @property
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
        return self._offset

    @offset.setter
    @check_ready
    def offset(self, input):
        self._offset = self._convert_value(input)

    @property
    def id(self):
        return self._detector_id

    @property
    def name(self):
        return self._name

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
    def __init__(self, detector_id, name, sensor_type, sensor_settings, log_level="WARNING", **kwargs):
        super().__init__(detector_id=detector_id, name=name, log_level=log_level)
        self._logger.debug("Creating sensor object using options: {}".format(sensor_settings))
        if sensor_type == 'VL53L1X':
            self._logger.debug("Setting up VL53L1X with sensor settings: {}".format(sensor_settings))
            self._sensor_obj = CB_VL53L1X(**sensor_settings, log_level=log_level)
        elif sensor_type == 'TFMini':
            self._logger.debug("Setting up TFMini with sensor settings: {}".format(sensor_settings))
            self._sensor_obj = TFMini(**sensor_settings, log_level=log_level)
        else:
            raise ValueError("Detector {} trying to use unknown sensor type {}".format(
                 self._name, sensor_settings))

    # Allow adjustment of timing.
    def timing(self, timing_input):
        # Make sure the timing input is a Quantity.
        timing_input = self._convert_value(timing_input)
        # Sensor takes measurement time in microseconds.
        mt = timing_input.to('microseconds').magnitude
        self._sensor_obj.measurement_time = mt

    # Called when the system needs to turn this sensor on.
    def activate(self):
        self._logger.debug("Detector starting sensor ranging.")
        self._sensor_obj.start_ranging()

    # Called when the system needs to go into idle mode and turn the sensor off.
    def deactivate(self):
        self._logger.debug("Detector stopping sensor ranging.")
        self._sensor_obj.stop_ranging()

    # Complete turn the sensor on or off using its enable pin.
    def enable(self):
        self._logger.debug("Enabling sensor.")
        self._sensor_obj.enable()

    def disable(self):
        self._logger.warning("Setting sensor enable pin to false.")
        self._sensor_obj.disable()

    # Called *only* when the system is exiting. This is currently an alias for deactivating, but other types
    # of hardware may need other behavior, ie: freeing devices.
    def shutdown(self):
        self.deactivate()
        self.disable()

    # Debugging methods to let the main system know a few things about the attached sensor.
    @property
    def sensor_type(self):
        return type(self._sensor_obj)

    @property
    def status(self):
        return self._sensor_obj.status

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
    def __init__(self, detector_id, name, error_margin, sensor_type, sensor_settings, log_level="WARNING"):
        super().__init__(detector_id, name, sensor_type, sensor_settings, log_level)
        # Required properties. These are checked by the check_ready decorator function to see if they're not None.
        # Once all required properties are not None, the object is set to ready. Doesn't check for values being *correct*.
        self._required = ['bay_depth','spread_park','pct_warn','pct_crit']
        # Save parameters
        self._error_margin = error_margin

        # Initialize variables, to be set by properties later.
        # Since these are all bay-specific, it doesn't make sense to set them at init-time.
        self._bay_depth = None
        self._spread_park = None
        self._pct_warn = None
        self._pct_crit = None
        self._dist_warn = None
        self._dist_crit = None

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
        self._logger.debug("90% of bay depth is: {}".format(self.bay_depth * .9))
        # Is there one of our own exceptions? These we can *probably* handle and get some useful information from.
        if isinstance(self._history[0][0], SensorValueException):
            # A weak reading from the sensor almost certainly means the door is open and nothing is blocking.
            if self._history[0][0].status == "Weak":
                return "Door open"
            elif self._history[0][0].status in ("Saturation", "Flood"):
                # When saturated or flooded, just pass on those statuses.
                return self._history[0][0]
            else:
                return "Unknown"
        # All other exceptions.
        elif isinstance(self._history[0][0], BaseException):
            return "Unknown"
        else:
            # You're about to hit the wall!
            if self._history[0][0] < Quantity("2 in"):
                return 'Emergency!'
            elif (self.bay_depth * 0.90) <= self._history[0][0]:
                self._logger.debug(
                    "Reading is more than 90% of bay depth ({})".format(self.bay_depth * .9))
                return 'No object'
            # Now consider the adjusted values.
            elif self.value < 0 and abs(self.value) > self.spread_park:
                return 'Back up'
            elif abs(self.value) < self.spread_park:
                return 'Park'
            elif self.value <= self._dist_crit:
                self._logger.debug("Critical distance is {}, returning Final.".format(self._dist_crit))
                return 'Final'
            elif self.value <= self._dist_warn:
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
        last_element = len(history) - 1
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
        return {'speed': speed, 'net_dist': net_dist, 'net_time': net_time}

    # Based on readings, is the vehicle in motion?
    @property
    @read_if_stale
    def motion(self):
        # Grab the movement
        movement = self._movement
        if movement is None:
            return "Unknown"
        elif abs(self._movement['net_dist']) > Quantity(self._error_margin):
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
            return {"speed": "Unknown", "direction": "Unknown"}
        # Okay, not none, so has value!
        if movement['net_dist'] > Quantity(self._error_margin):
            return {'speed': abs(movement['speed']), 'direction': 'forward'}
        elif movement['net_dist'] < (Quantity(self._error_margin) * -1):
            return {'speed': abs(movement['speed']), 'direction': 'reverse'}
        else:
            return {'speed': Quantity("0 kph"), 'direction': 'still'}

    # Gets called when the rangefinder has all settings and is being made ready for use.
    def _when_ready(self):
        # Calculate specific distances to use based on the percentages.
        self._derived_distances()

    # Allow dynamic distance mode changes to come from the bay. This is largely used for debugging.
    def distance_mode(self, target_mode):
        try:
            self._sensor_obj.distance_mode = target_mode
        except ValueError:
            print("Could not change distance mode to {}".format(target_mode))

    @property
    def bay_depth(self):
        return self._bay_depth

    @bay_depth.setter
    @check_ready
    def bay_depth(self, depth):
        self._bay_depth = self._convert_value(depth)

    @property
    def spread_park(self):
        return self._spread_park

    @spread_park.setter
    @check_ready
    def spread_park(self, input):
        self._spread_park = self._convert_value(input)

    # Properties for warning and critical percentages. We take these are "normal" percentages (ie: 15.10) and convert
    # to decimal so it can be readily used for multiplication.
    @property
    def pct_warn(self):
        try:
            return self._pct_warn * 100
        except TypeError:
            return None

    @pct_warn.setter
    @check_ready
    def pct_warn(self, input):
        self._pct_warn = input / 100

    @property
    def pct_crit(self):
        try:
            return self._pct_crit * 100
        except TypeError:
            return None

    @pct_crit.setter
    @check_ready
    def pct_crit(self, input):
        self._pct_crit = input / 100

    # When object is declared ready, calculated derived distances.
    def _when_ready(self):
        self._derived_distances()

    # Pre-bake distances for warn and critical to make evaluations a little easier.
    def _derived_distances(self):
        self._logger.debug("Calculating derived distances.")
        adjusted_distance = self.bay_depth - self._offset
        self._logger.debug("Adjusted distance: {}".format(adjusted_distance))
        self._dist_warn = ( adjusted_distance.magnitude * self.pct_warn )/100 * adjusted_distance.units
        self._logger.debug("Warning distance: {}".format(self._dist_warn))
        self._dist_crit = ( adjusted_distance.magnitude * self.pct_crit )/100 * adjusted_distance.units
        self._logger.debug("Critical distance: {}".format(self._dist_crit))

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
    def __init__(self, detector_id, name, sensor_type, sensor_settings, log_level="WARNING"):
        super().__init__(detector_id, name, sensor_type, sensor_settings, log_level)
        self._required = ['side', 'spread_ok', 'spread_warn']
        self._side = None
        self._spread_ok = None
        self._spread_warn = None

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
            self._logger.debug("Comparing to OK ({}) and WARN ({})".format(
                self.spread_ok, self.spread_warn))
            if self.value > Quantity('90 in'):
                # A standard vehicle width (in the US, at least) is 96 inches. If we can reach across a significant
                # proportion of the bay, we're not finding a vehicle, so deem it to be no vehicle.
                qv = "No vehicle"
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
        return self._spread_ok

    @spread_ok.setter
    @check_ready
    def spread_ok(self, m_input):
        self._spread_ok = self._convert_value(m_input).to('cm')
        # Check to see if the detector is now ready.

    @property
    def spread_warn(self):
        return self._spread_warn

    @spread_warn.setter
    @check_ready
    def spread_warn(self, m_input):
        self._spread_warn = self._convert_value(m_input).to('cm')

    @property
    def side(self):
        return self._side

    @side.setter
    @check_ready
    def side(self, m_input):
        if m_input.upper() not in ('R', 'L'):
            raise ValueError("Lateral side must be 'R' or 'L'")
        else:
            self._side = m_input.upper()

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
