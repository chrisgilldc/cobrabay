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
        self.offset = offset
        print("Offset: {}".format(self._offset))
        # Create the sense object using provided settings.
        self._sensor_obj = CB_VL53L1X(board_options)
        self._history = []

    # Store the current reading as the offset. Useful when an object is *in* the spot where it should be.
    def tare(self):
        self._offset = self._range_avg()

    @property
    def offset(self):
        return self._offset

    @offset.setter
    def offset(self,input):
        if isinstance(input,Quantity):
            # If offset is already a quantity, use that.
            self._offset = input
        elif isinstance(input,str):
            # If it's a string, use the Quantity string-parser approach.
            self._offset = Quantity(input)
        else:
            # Otherwise, it's *likely* numeric, so default to millimeters and hope it workse.
            self._offset = Quantity(input,"mm")

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

    def activate(self):
        self._sensor_obj.start_ranging()

    def deactivate(self):
        self._sensor_obj.stop_ranging()

    # Method for stopping hardware when software is shutting down.
    # This tries to clean up and not leave things in a bad state.
    # Currently this is just an alias for deactivate, but is named differently because it may grow later.
    def shutdown(self):
        self.deactivate()


# Detector that measures range progress.
class Range(SingleDetector):
    @property
    def value(self):
        # Read the sensor and put it at the start of the list, along with a timestamp.
        self._history.insert(0,[self._sensor_obj.range, monotonic_ns()])
        # Make sure the history list is always five elements, so we don't just grow this ridiculously.
        self._history = self._history[:5]
        # Return that reading, minus the offset.
        return self._history[0][0] - self.offset

    def distance_mode(self,input):
        try:
            self._sensor_obj.distance_mode = input
        except ValueError:
            print("Could not change distance mode to {}".format(input))

# Detector for lateral position
class Lateral(SingleDetector):
    def __init__(self,sensor,settings):
        super().__init__(sensor, settings)

# Wrapper to group together multiple detectors
class MultiDetector(Detector):
    pass