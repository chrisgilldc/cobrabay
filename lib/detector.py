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
    def __init__(self, board_options):
        super().__init__()
        self._offset = Quantity("0 cm")
        # Create the sense object using provided settings.
        self._sensor_obj = CB_VL53L1X(board_options)
        self._history = []
        self._required_settings = []
        self._settings = {}
        self._ready = False

    # Allow adjustment of timing.
    def timing(self, timing_input):
        # Make sure the timing input is a Quantity.
        timing_input = self._convert_value(timing_input)
        # Sensor takes measurement time in microseconds.
        mt =  timing_input.to('microseconds').magnitude
        self._sensor_obj.measurement_time = mt

    @property
    def ready(self):
        return self._ready

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

    # Utility method to convert into quantities.
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

    def _check_ready(self):
        for setting in self._required_settings:
            if self._settings[setting] is None:
                self._ready = False
                return False
        self._ready = True
        return True

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
    def __init__(self, board_options):
        super().__init__(board_options)
        self._required_settings = ['offset','bay_depth','pct_warn','pct_crit']
        self._settings = {}
        for setting in self._required_settings:
            self._settings[setting] = None
        # Default the warn and critical percentages.
        self._settings['pct_crit'] = 5
        self._settings['pct_warn'] = 10

    @property
    def value(self):
        if not self.ready:
            raise RuntimeError("Detector is not fully configured, cannot read value yet.")
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

    @property
    def offset(self):
        return self._settings['offset']

    @offset.setter
    def offset(self, input):
        self._settings['offset'] = self._convert_value(input)
        self._check_ready()

    @property
    def bay_depth(self):
        return self._settings['bay_depth']

    @bay_depth.setter
    def bay_depth(self, input):
        self._settings['bay_depth'] = self._convert_value(input)
        self._check_ready()

    @property
    def pct_warn(self):
        return self._settings['pct_warn']

    @pct_warn.setter
    def pct_warn(self, input):
        self._settings['pct_warn'] = input
        if self._check_ready():
            self._derived_distances()

    @property
    def pct_crit(self):
        return self._settings['pct_crit']

    @pct_crit.setter
    def pct_crit(self, input):
        self._settings['pct_warn'] = input
        if self._check_ready():
            self._derived_distances()

    def _derived_distances(self):
        self._settings['dist_warn'] = ( self._settings['bay_depth'] - self._settings['offset'] ) * ( self._settings['pct_warn'] / 100 )
        self._settings['dist_crit'] = ( self._settings['bay_depth'] - self._settings['offset'] ) * ( self._settings['pct_crit'] / 100 )

# Detector for lateral position
class Lateral(SingleDetector):
    def __init__(self,board_options):
        super().__init__(board_options)
        # Initialize required elements as None. This lets us do a readiness check later.
        self._required_settings = ['offset','spread_ok','spread_warn','spread_critical','side']
        self._settings = {}
        for setting in self._required_settings:
            self._settings[setting] = None

    @property
    def ready(self):
        return self._ready

    @property
    def offset(self):
        return self._settings['offset']

    @offset.setter
    def offset(self,input):
        # Convert into a Pint Quantity.
        self._settings['offset'] = self._convert_value(input)
        # Check to see if the detector is now ready.
        self._check_ready()

    @property
    def spread_ok(self):
        return self._settings['spread_ok']

    @spread_ok.setter
    def spread_ok(self,input):
        self._settings['spread_ok'] = self._convert_value(input)
        # Check to see if the detector is now ready.
        self._check_ready()

    @property
    def spread_warn(self):
        return self._settings['spread_warn']

    @spread_warn.setter
    def spread_warn(self,input):
        self._settings['spread_warn'] = self._convert_value(input)
        # Check to see if the detector is now ready.
        self._check_ready()

    @property
    def spread_critical(self):
        return self._settings['spread_critical']

    @spread_critical.setter
    def spread_critical(self,input):
        self._settings['spread_warn'] = self._convert_value(input)
        # Check to see if the detector is now ready.
        self._check_ready()

    @property
    def side(self):
        return self._settings['side']

    @side.setter
    def side(self,input):
        if input.upper() not in ('R','L'):
            raise ValueError("Lateral side must be 'R' or 'L'")
        else:
            self._settings['side'] = input.upper()
            self._check_ready()

# Wrapper to group together multiple detectors
class MultiDetector(Detector):
    pass