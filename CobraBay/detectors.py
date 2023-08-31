####
# CobraBay Detector
####
import pint.errors

from .sensors import CB_VL53L1X, TFMini, FileSensor, I2CSensor, SerialSensor
from CobraBay.const import *
import CobraBay.exceptions
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


# Decorator for methods reading the sensor.
# If it's been too long since the previous sensor check, check it and add it to the history.
# The wrapped function should use the first element in the history, not the direct reading!
def read_if_stale(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        read_sensor = False  # Assume we won't read the sensor.
        if self._sensor_obj.status != 'ranging':
            # If sensor object isn't ranging, return immediately with a not_ranging result.
            return SENSTATE_NOTRANGING
        else:
            if len(self._history) > 0:
                # Time difference between now and the most recent read.
                time_delta = monotonic_ns() - self._history[0][1]
                # Assume we can read the sensor every other pass of its set timing.
                if time_delta > self._sensor_obj.timing_budget.to('ns').magnitude * 1.1:
                    read_sensor = True
            else:
                read_sensor = True  ## Must read the sensor, there isn't any history. This should only happen on startup.

        # If flag is set, read the sensor and put its value into the history.
        if read_sensor:
            try:
                value = self._sensor_obj.range
                self._logger.debug("Triggered sensor reading. Got: {} ({})".format(value, type(value)))
            except CobraBay.exceptions.SensorException as e:
                raise
            except BaseException:
                # Any other exception, raise immediately.
                raise
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
        self._logger.setLevel(log_level.upper())
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
    def offset(self, the_input):
        self._logger.info("Offset is now - {}".format(the_input))
        self._offset = self._convert_value(the_input)

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
            self._sensor_obj = CB_VL53L1X(**sensor_settings, parent_logger=self._logger)
        elif sensor_type == 'TFMini':
            self._logger.debug("Setting up TFMini with sensor settings: {}".format(sensor_settings))
            self._sensor_obj = TFMini(**sensor_settings, parent_logger=self._logger)
        elif sensor_type == 'FileSensor':
            self._logger.debug("Setting up FileSensor with sensor settings: {}".format(sensor_settings))
            self._sensor_obj = FileSensor(**sensor_settings, sensor=detector_id, parent_logger=self._logger)
        else:
            raise ValueError("Detector {} trying to use unknown sensor type {}".format(
                self._name, sensor_settings))
        self._status = None

    # Allow adjustment of timing.
    def timing(self, timing_input):
        # Make sure the timing input is a Quantity.
        timing_input = self._convert_value(timing_input)
        # Sensor takes measurement time in microseconds.
        mt = timing_input.to('microseconds').magnitude
        self._sensor_obj.measurement_time = mt

    # The status of a single detector is definitionally the status of its enwrapped sensor.
    @property
    def status(self):
        return self._sensor_obj.status

    # Change the status of the detector.
    @status.setter
    def status(self, target_status):
        """
        :param target_status: Status to set the detector to. One of 'disabled', 'enabled', 'ranging'
        :type target_status: str
        :return:
        """
        if target_status.lower() not in ('disabled', 'enabled', 'ranging'):
            raise ValueError("Target status '{}' not valid.".format(target_status))
        else:
            self._logger.debug("Target status: {}".format(target_status))
        if target_status.lower() == self._sensor_obj.status:
            self._logger.info("Detector already has status '{}'. Nothing to do.".format(self._sensor_obj.status))
        else:
            self._logger.debug("Setting sensor object status to '{}'".format(target_status))
            self._sensor_obj.status = target_status

    # Pass through for the operating state of the sensor object.
    @property
    def state(self):
        return self._sensor_obj.state

    @property
    def fault(self):
        """
        Utility property for determining if the detector is in a fault state. The status and state should always match up,
        so if they don't, something is wrong. More complex logic to figure out what the fault is and what action to take
        should be implemented elsewhere.

        :return: bool
        """
        if self.status != self.state:
            self._logger.warning("Detector is in a fault state. Operating status '{}' does not equal running state '{}'".
                                 format(self.status, self.state))
            return True
        else:
            return False

    # Debugging methods to let the main system know a few things about the attached sensor.
    @property
    def sensor_type(self):
        return type(self._sensor_obj)

    @property
    def sensor_interface(self):
        iface_info = namedtuple("iface_info", ['type', 'addr'])
        if isinstance(self._sensor_obj, SerialSensor):
            iface = iface_info("serial", self._sensor_obj.serial_port)
        elif isinstance(self._sensor_obj, I2CSensor):
            iface = iface_info("i2c", self._sensor_obj.i2c_address)
        elif isinstance(self._sensor_obj, FileSensor):
            iface = iface_info("file", self._sensor_obj.file)
        else:
            iface = iface_info("unknown", "unknown")
        return iface

    @property
    def value(self):
        """
        Returns the adjusted measurement of the detector. Calls the "value_raw" method of the detector, which must
        be defined on a per-class basis.
        :return:
        """
        value_raw = self.value_raw
        self._logger.debug("Creating adjusted value from latest value: {}".format(value_raw))
        self._logger.debug("Defined offset is: {}".format(self.offset))
        if isinstance(value_raw, Quantity):
            return value_raw - self.offset
        else:
            return value_raw

    @property
    def value_raw(self):
        raise NotImplementedError("Raw value method should be implemented on a class basis.")


# Detector that measures range progress.
class Longitudinal(SingleDetector):
    def __init__(self, detector_id, name, error_margin, sensor_type, sensor_settings, log_level="WARNING"):
        super().__init__(detector_id=detector_id, name=name, error_margin=error_margin, sensor_type=sensor_type,
                         sensor_settings=sensor_settings, log_level=log_level)
        # Required properties. These are checked by the check_ready decorator function to see if they're not None.
        # Once all required properties are not None, the object is set to ready. Doesn't check for values being *correct*.
        self._required = ['bay_depth', 'spread_park', 'pct_warn', 'pct_crit']
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

    # Method to get the raw sensor reading. This is used to report upward for HA extended attributes.
    @property
    @read_if_stale
    def value_raw(self):
        # Note, the read_if_stale decorator will trap this if the sensor itself isn't ranging. Thus, we can assume it is.
        self._logger.debug("Most recent reading is: {}".format(self._history[0][0]))
        if isinstance(self._history[0][0], Quantity) or isinstance(self._history[0][0], BaseException):
            return self._history[0][0]
        elif self._history[0][0] is None:
            self._logger.debug("Latest reading was None. Returning 'unknown'")
            return "unknown"
        elif isinstance(self._history[0][0], str):
            self._logger.debug("History had string '{}'. Returning 'no_reading'".format(self._history[0][0]))
            return "no_reading"
        else:
            self._logger.debug("Unknown reading state, returning 'error'")
            return "error"

    # Assess the quality of the sensor
    @property
    @read_if_stale
    def quality(self):
        # Pull the current value for evaluation.
        current_raw_value = self.value_raw
        self._logger.debug("Evaluating current raw value '{}' for quality".format(current_raw_value))
        if isinstance(self.value_raw, Quantity):
            # Make an adjusted value as well.
            current_adj_value = current_raw_value - self.offset
            # Actual reading, evaluate.
            if current_raw_value < Quantity("2 in"):
                return DETECTOR_QUALITY_EMERG
            elif (self.bay_depth * 0.90) <= current_raw_value:
                # Check the actual distance. If more than 90% of the bay distance is clear, probably nothing there.
                self._logger.debug(
                    "Reading is more than 90% of bay depth ({})".format(self.bay_depth * .9))
                return DETECTOR_QUALITY_NOOBJ
            # Now consider the adjusted values.
            elif current_adj_value < 0 and abs(current_adj_value) > self.spread_park:
                # Overshot stop point and too far to be considered an okay park, backup.
                return DETECTOR_QUALITY_BACKUP
            elif abs(current_adj_value) < self.spread_park:
                # Just short of stop point, but within allowed range, parked.
                return DETECTOR_QUALITY_PARK
            elif current_adj_value <= self._dist_crit:
                # Within critical range, this is "final"
                return DETECTOR_QUALITY_FINAL
            elif current_adj_value <= self._dist_warn:
                # within warning range, this is "base"
                return DETECTOR_QUALITY_BASE
            else:
                # Too far to be in another status, but reading something, so this is the general 'OK' state.
                return DETECTOR_QUALITY_OK
        # Handle non-Quantity values from the reading.
        elif current_raw_value == SENSOR_VALUE_WEAK:
            return DETECTOR_QUALITY_DOOROPEN
        elif current_raw_value in (SENSOR_VALUE_FLOOD, SENSOR_VALUE_STRONG):
            return DETECTOR_NOREADING
        else:
            return GEN_UNKNOWN

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
            return 'unknown'

        # If the sensor is reading beyond range, speed and direction can't be known, so return immediately.
        last_element = len(history) - 1
        self._logger.debug("First history: {}".format(history[0]))
        self._logger.debug("Last history: {}".format(history[last_element]))
        try:
            net_dist = self._history[0][0] - history[last_element][0]
            net_time = Quantity(history[0][1] - history[last_element][1], 'nanoseconds').to('seconds')
        except pint.errors.DimensionalityError:
            # If we're trying to subtract a non-Quantity value, then return unknown for these.
            return 'unknown'
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
        if not isinstance(movement, dict):
            return GEN_UNKNOWN
        elif abs(self._movement['net_dist']) > Quantity(self._error_margin):
            return True
        else:
            return False

    @property
    def vector(self):

        # Grab the movement value.
        movement = self._movement

        # Can't determine a vector if sensor is NOT RANGING or return UNKNOWN.
        if movement in (SENSTATE_NOTRANGING,GEN_UNKNOWN):
            return {"speed": GEN_UNKNOWN, "direction": GEN_UNKNOWN}
        # Determine a direction.
        self._logger.debug("Have movement value: {}".format(movement))

        # Okay, not none, so has value!
        if movement['net_dist'] > Quantity(self._error_margin):
            return {'speed': abs(movement['speed']), 'direction': DIR_REV}
        elif movement['net_dist'] < (Quantity(self._error_margin) * -1):
            return {'speed': abs(movement['speed']), 'direction': DIR_FWD}
        else:
            return {'speed': Quantity("0 kph"), 'direction': DIR_STILL}

    # Gets called when the rangefinder has all settings and is being made ready for use.
    def _when_ready(self):
        # Calculate specific distances to use based on the percentages.
        self._derived_distances()

    # Allow dynamic distance mode changes to come from the bay. This is largely used for debugging.
    def distance_mode(self, target_mode):
        try:
            self._sensor_obj.distance_mode = target_mode
        except ValueError:
            self._logger.warning("Could not change distance mode to {}".format(target_mode))

    @property
    def bay_depth(self):
        return self._bay_depth

    @bay_depth.setter
    @check_ready
    def bay_depth(self, depth):
        self._bay_depth = self._convert_value(depth)
        self._adjusted_bay_depth = self._bay_depth - self.offset

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
    def pct_warn(self, the_input):
        self._logger.info("Percent warn is - {}".format(the_input))
        self._pct_warn = the_input / 100

    @property
    def pct_crit(self):
        try:
            return self._pct_crit * 100
        except TypeError:
            return None

    @pct_crit.setter
    @check_ready
    def pct_crit(self, the_input):
        self._logger.info("Percent critical is - {}".format(the_input))
        self._pct_crit = the_input / 100

    # Pre-bake distances for warn and critical to make evaluations a little easier.
    def _derived_distances(self):
        self._logger.info("Calculating derived distances.")
        adjusted_distance = self.bay_depth - self._offset
        self._logger.info("Adjusted distance: {}".format(adjusted_distance))
        self._dist_warn = (adjusted_distance.magnitude * self.pct_warn) / 100 * adjusted_distance.units
        self._logger.info("Warning distance: {}".format(self._dist_warn))
        self._dist_crit = (adjusted_distance.magnitude * self.pct_crit) / 100 * adjusted_distance.units
        self._logger.info("Critical distance: {}".format(self._dist_crit))

    # Reference some properties upward to the parent class. This is necessary because properties aren't directly
    # inherented.

    @property
    def offset(self):
        return super().offset

    @offset.setter
    def offset(self, new_offset):
        super(Longitudinal, self.__class__).offset.fset(self, new_offset)

    @property
    def status(self):
        return super().status

    @status.setter
    def status(self, target_status):
        super(Longitudinal, self.__class__).status.fset(self, target_status)


# Detector for lateral position
class Lateral(SingleDetector):
    def __init__(self, detector_id, name, sensor_type, sensor_settings, log_level="WARNING" ):
        super().__init__(detector_id=detector_id, name=name, sensor_type=sensor_type, sensor_settings=sensor_settings,
                         log_level=log_level)
        self._intercept = None
        self._required = ['side', 'spread_ok', 'spread_warn']
        self._side = None
        self._spread_ok = None
        self._spread_warn = None
        self._limit = None
        self._bay_obj = None

    # Method to get the raw sensor reading. This is used to report upward for HA extended attributes.
    @property
    @read_if_stale
    def value_raw(self):
        if isinstance(self._history[0][0], Quantity):
            return self._history[0][0]
        elif isinstance(self._history[0][0], CobraBay.exceptions.SensorException):
            # If the sensor has already errored, raise that.
            raise self._history[0][0]
        else:
            # Anything else, treat it as the sensor returning no reading.
            return DETECTOR_NOREADING

    @property
    @read_if_stale
    def quality(self):
        self._logger.debug("Assessing quality for value: {}".format(self.value))
        # Process quality if we get a quantity from the Detector.
        if isinstance(self.value, Quantity):
            if self.value > self._limit:
                qv = DETECTOR_QUALITY_NOOBJ
            elif abs(self.value) <= self.spread_ok:
                qv = DETECTOR_QUALITY_OK
            elif abs(self.value) <= self.spread_warn:
                qv = DETECTOR_QUALITY_WARN
            elif abs(self.value) > self.spread_warn:
                qv = DETECTOR_QUALITY_CRIT
            else:
                # Total failure to return a value means the light didn't reflect off anything. That *probably* means
                # nothing is there, but it could be failing for other reasons.
                qv = GEN_UNKNOWN
        else:
            qv = GEN_UNKNOWN
        # Check for interception. If this is enabled, we stomp over everything else.
        if self.attached_bay is not None and self.intercept is not None:
            self._logger.debug("Evaluating for interception.")
            lv = self.attached_bay.range.value_raw
            try:
                if lv > self.intercept:
                    self._logger.debug("Reported range '{}' greater than intercept '{}'. Not intercepted.".format(
                        self.attached_bay.range.value, self.intercept
                    ))
                    qv = DETECTOR_NOINTERCEPT
            except ValueError:
                self._logger.warning("Cannot use longitudinal value '{}' to check for intercept".format(lv))
        else:
            self._logger.debug("Cannot evaluate for interception, not configured.")
        self._logger.debug("Quality {}".format(qv))
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

    @property
    def limit(self):
        return self._limit

    @limit.setter
    def limit(self, new_limit):
        self._limit = new_limit

    @property
    def attached_bay(self):
        return self._bay_obj

    @attached_bay.setter
    def attached_bay(self, new_bay_obj):
        self._bay_obj = new_bay_obj

    @property
    def intercept(self):
        return self._intercept

    @intercept.setter
    def intercept(self, new_intercept):
        if not isinstance(new_intercept, Quantity):
            raise TypeError("Intercept must be a quantity.")
        else:
            self._intercept = new_intercept

    # Reference some properties upward to the parent class. This is necessary because properties aren't directly
    # inherented.

    @property
    def i2c_address(self):
        return super()._i2c_address

    @property
    def offset(self):
        self._logger.debug("Returning offset: {}".format(super().offset))
        return super().offset

    @offset.setter
    @check_ready
    def offset(self, m_input):
        self._logger.debug("Setting offset to: {}".format(m_input))
        super(Lateral, self.__class__).offset.fset(self, m_input)

    @property
    def status(self):
        return super().status

    @status.setter
    def status(self, target_status):
        super(Lateral, self.__class__).status.fset(self, target_status)
