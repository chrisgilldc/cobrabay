####
# Cobray Bay - The Bay!
####
import pint.errors

from .detector import Range
from pint import UnitRegistry, Quantity
from PIL import Image, ImageDraw
import logging

class Bay:
    def __init__(self,logger,detectors):

        # Set the Bay ID. This is static for testing, real config processing will come later.
        self.bay_id = 'bay1'
        # Create a logger.
        self._logger = logging.getLogger("CobraBay").getChild(self._bay_id)
        self._logger.setLevel(logging.DEBUG)
        # Log our initialization.
        self._logger.info("Bay '{}' initializing...".format(self._bay_id))
        # Create a unit registry.
        self._ureg = UnitRegistry

        self._detectors = {}
        # Have to have a range detector
        self._detectors['range'] = detectors['range']
        # raise ValueError("Bay detectors must include a range detector.")
        # Flag to indicate if we're tracking lateral positions.
        self._lateral = False

        # Set the display height. This is needed for some display calculations
        self._matrix = {'width': 64, 'height': 32 }
        self._display_som = "imperial"
        self._state = 'ready'
        self._logger.info("Bay '{}' initialization complete.".format(self._bay_id))

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
            return 'Meh?'
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
        # Trap invalid bay states.
        if input not in ('docking','undocking','occupied','unoccupied','unavailable'):
            raise ValueError("{} is not a valid bay state.".format(input))
        if input in ('docking','undocking') and self._state not in ('docking','undocking'):
            # When entering docking or undocking state, start ranging on the sensors.
            for detector in self._detectors:
                detector.activate()
        if input not in ('docking','undocking') and self._state in ('docking', 'undocking'):
            # When leaving docking or undocking state, stop ranging on the sensors.
            for detector in self._detectors:
                detector.deactivate()


    # MQTT status methods. These generate payloads the core network handler can send upward.
    def mqtt_messages(self,verify=False):
        outbound_messages = [] # topic, message, repease, topic_mappings
        # State message.
        outbound_messages.append(
            {'topic': 'bay_occupied', 'message': self.occupied, 'repeat': False, 'topic_mappings': {'bay_id': self._bay_id}}
        )
        # Only generate  positioning messages if 1) we're  docking or undocking or 2)  a verify has been explicitly requested.
        if verify or self.state in ('docking','undocking'):
            outbound_messages.append(
                {'topic': 'bay_park_quality', 'message': self.park_quality, 'repeat': False, 'topic_mappings': {'bay_id': self._bay_id}}
            )
            outbound_messages.append(
                {'topic': 'bay_position', 'message': self.position, 'repeat': False, 'topic_mappings': {'bay_id': self._bay_id}}
            )
            outbound_messages.append(
                {'topic': 'bay_state', 'message': self.state, 'repeat': False,'topic_mappings': {'bay_id': self._bay_id}}
            )
        return outbound_messages

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

    @property
    def bay_id(self):
        return self._bay_id

    @bay_id.setter
    def bay_id(self,input):
        self._bay_id = input