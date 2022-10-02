####
# Cobray Bay - The Bay!
####
import pint.errors

from .detector import Range, Lateral
from pint import UnitRegistry, Quantity
from PIL import Image, ImageDraw
import logging

class Bay:
    def __init__(self,config,detectors):
        # Set the Bay ID. This is static for testing, real config processing will come later.
        self.bay_id = 'bay1'
        # Create a logger.
        self._logger = logging.getLogger("CobraBay").getChild(self._bay_id)
        self._logger.setLevel(logging.DEBUG)
        # Log our initialization.
        self._logger.info("Bay '{}' initializing...".format(self._bay_id))
        # Create a unit registry.
        self._ureg = UnitRegistry
        # Set the unit system. Default to Metric. If units is in the config and is imperial, change it to imperial.
        self._unit_system = 'metric'
        if 'units' in config:
            if config['units'].lower() == 'imperial':
                self._unit_system = 'imperial'

        self._setup_detectors(config,detectors)
        self._lateral = False
        # Set the display height. This is needed for some display calculations
        self._matrix = {'width': 64, 'height': 32 }
        self._display_som = "imperial"
        self._state = 'ready'
        self._logger.info("Bay '{}' initialization complete.".format(self._bay_id))

    # Imperative commands
    def dock(self):
        self._logger.debug("Received dock command.")
        if self.state in ('docking','undocking'):
            raise ValueError("Cannot dock, already {}".format(self.state))
        elif self.state == 'unavailable':
            raise ValueError("Cannot dock, bay is unavailable")
        else:
            # Do the things to do when docking.
            self.state = 'docking'

    def undock(self):
        pass

    # Abort gets called when we want to cancel a docking.
    def abort(self):
        # Return the bay to a ready state.
        self.state = 'unoccupied'

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
        if self._unit_system == 'imperial':
            return_dict['lo'] = self._detectors['range'].value.to('in')
        else:
            return_dict['lo'] = self._detectors['range'].value.to('m')

        if len(self._detectors['lateral']) > 0:
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
        self._logger.debug("State change requested to {} from {}".format(input,self._state))
        # Trap invalid bay states.
        if input not in ('docking','undocking','occupied','unoccupied','unavailable'):
            raise ValueError("{} is not a valid bay state.".format(input))
        else:
            self._state = input
        if input in ('docking','undocking') and self._state not in ('docking','undocking'):
            # When entering docking or undocking state, start ranging on the sensors.
            for detector in self._detectors:
                self._detectors[detector].activate()
        if input not in ('docking','undocking') and self._state in ('docking', 'undocking'):
            # When leaving docking or undocking state, stop ranging on the sensors.
            for detector in self._detectors:
                self._detectors[detector].deactivate()


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
        img = Image.new("RGB", (64,32))
        im.rectangle()

    def _frame(self,w,h):
        img = Image.new("RGB", (w,h))
        # Left box
        img.rectangle((0,0),(3,h-4))
        # Right box
        img.rectangle((w-3,0),(3,h-4))

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

    # Method to set up the detectors for the bay. This applies bay-specific options to the individual detectors, which
    # are initialized by the main routine.
    def _setup_detectors(self,config,detectors):
        self._detectors = {}
        # Do the range setup. This behaves a little differently, so is coraled to a separate method for sanity.
        self._setup_range(config,detectors)
        # Lateral configuration.
        # Make the lateral array.
        self._detectors['lateral'] = []
        for detector_config in config['lateral']['detectors']:
            detector_name = detector_config['detector']
            try:
                lateral = detectors[detector_name]
            except KeyError:
                raise KeyError("Tried to create lateral zone with detector '{}' but detector not defined."
                               .format(detector_name))
            # Now we have the detector, set it up right.
            for item in ('offset','spread_ok','spread_warn','spread_crit','side'):
                try:
                    setattr(lateral, item, detector_config[item])
                except KeyError:
                    self._logger.debug("Using default value for {}".format(item))
                    try:
                        setattr(lateral,item,config['lateral']['defaults'][item])
                    except KeyError:
                        raise KeyError("Needed default value for {} but not defined!".format(item))

    # Method to set up the range detector
    def _setup_range(self,config,detectors):
        # Is the detector name specified.
        try:
            range_detector_name = config['range']['detector']
        except KeyError:
            raise KeyError("Detector is not defined for bay's range. This is required!")
        # Try to get the detector.
        try:
            self._detectors['range'] = detectors[range_detector_name]
        except KeyError:
            raise KeyError("Provided detector name '{}' does not exist.".format(range_detector_name))
        # Add the required range parameters.
        self._logger.info("Setting range detector offset to: {}".format(config['range']['offset']))
        self._detectors['range'].offset = config['range']['offset']
        self._logger.info("Setting range detector bay depth to: {}".format(config['range']['bay_depth']))
        self._detectors['range'].bay_depth = config['range']['bay_depth']