####
# CobraBay Detector
####

from .sensor import VL53L1X as CB_VL53L1X
from pint import UnitRegistry, Quantity
from statistics import mean
from time import monotonic_ns

class Detector:
    def __init__(self):
        # A unit registry
        self._ureg = UnitRegistry()

    # This should get overriden by the specific sub-classes.
    def _setup_detector(self,settings):
        pass

    def reading(self):
        pass

    def detector(self):
        pass

# Single Detectors add wrappers around a single sensor.
class SingleDetector(Detector):
    def __init__(self, offset, timing, board_options):
        super().__init__()
        # Store the sensor object.
        self._offset = offset
        # Create the sense object using provided settings.
        self._sensor_obj = CB_VL53L1X(board_options)
        self._history = []

    # Store the current reading as the offset. Useful when an object is *in* the spot where it should be.
    def tare(self):
        self._offset = self._range_avg()

    def _convert_value(self, input_value):
        # If it's already a quantity, return it right away.
        if isinstance(input_value, Quantity):
            return input_value
        elif isinstance(input_value, str):
            return Quantity(input_value)
        else:
            raise ValueError("Not a parseable value!")

    def _range_avg(self, num=5):
        results = []
        while len(results) < num:
            results.append(self._sensor_obj.range)
        return mean(results) * results[0].units

    # Method for stopping hardware when software is shutting down.
    # This tries to clean up and not leave things in a bad state.
    def shutdown(self):
        self._sensor_obj.stop_ranging()

# Detector that measures range progress.
class Range(SingleDetector):
    @property
    def value(self):
        # Read the sensor and put it at the start of the list, along with a timestamp.
        self._history.insert(0,[self._sensor_obj.range, monotonic_ns()])
        # Make sure the history list is always five elements, so we don't just grow this ridiculously.
        self._history = self._history[:5]
        # Return that reading, minus the offset.
        return self._history[0][0] - self._offset

# Detector for lateral position
class Lateral(SingleDetector):
    def __init__(self,sensor,settings):
        super().__init__(sensor, settings)

# Wrapper to group together multiple detectors
class MultiDetector(Detector):
    pass