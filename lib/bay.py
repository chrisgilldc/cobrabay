####
# Cobray Bay - The Bay!
####

from .detector import Range
from pint import UnitRegistry, Quantity
from PIL import Image, ImageDraw

class Bay:
    def __init__(self,logger,detectors):
        self._ureg = UnitRegistry

        self._detectors = {}
        # Have to have a range detector
        self._detectors['range'] = detectors['range']
        # raise ValueError("Bay detectors must include a range detector.")

        # Flag to indicate if we're tracking lateral positions.
        self._lateral = False
        # Set the Bay ID.
        self._bay_id = 'bay1'
        # Set the display height. This is needed for some display calculations
        self._matrix = {'width': 64, 'height': 32 }
        self._display_som = "imperial"

    # Bay properties
    @property
    def occupied(self):
        '''
        Occupancy state of the bay, derived from the State.
        If positively occupied or not, returns that, otherwise 'unknown'.

        :returns: bay occupancy state
        :rtype: String
        '''
        if self.state in ('occupied','unoccupied'):
            return self.state
        else:
            return 'unknown'

    # How good is the parking job?
    @property
    def park_quality(self):
        if self.occupied == 'occupied':
            # Some logic here.
            pass
        else:
            return 'Not Parked'

    @property
    def position(self):
        '''
        Position of the vehicle in the bay

        :returns Positioning dictionary
        :rtype Dict
        '''
        return_dict = {}
        # Longitudinal offset.
        return_dict['lo'] = self._detectors['range'].value
        if self._lateral:
            # Add code here later for lateral position
            pass
        else:
            return_dict['la'] = None
        return return_dict

    @property
    def state(self):
        '''
        Operating state of the bay.
        Can be one of 'docking', 'undocking', 'occupied', 'unoccupied,
        Can also have the error state 'unavailable'

        :returns Bay state
        :rtype: String
        '''
        return self._state

    @state.setter
    def state(self,input):
        if input in ('docking','undocking','occupied','unoccupied','unavailable'):
            self._state = input
        else:
            raise ValueError("{} is not a valid bay state.".format(input))


    # MQTT status methods. These generate payloads the core network handler can send upward.
    def mqtt_messages(self):
        pass

    def mqtt_discovery(self):
        pass

    # Image making methods

    # Draws the image to be overlaid on the RGB Matrix
    def image(self):
        pass

    def _approach_strobe(self):
        pass

    def _range_text(self):
        pass

    def _lateral_markers(self):
        pass

    # Method to be called when CobraBay it shutting down.
    def shutdown(self):
        for detector in self._detectors:
            self._detectors[detector].shutdown()