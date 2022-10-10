####
# Cobray Bay - The Bay!
####
import pint.errors

from .detector import Detector, Range, Lateral
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
        self._output_unit = 'm'
        if 'units' in config:
            if config['units'].lower() == 'imperial':
                self._unit_system = 'imperial'
                self._output_unit = 'in'

        # Set up the detectors.
        self._setup_detectors(config,detectors)
        self._logger.debug(self._detectors)
        self._logger.debug("Detectors configured:")
        self._logger.debug("\tRange: {}".format(hex(self._detectors['range'].i2c_address)))
        lat_string = ""
        for detector in self._detectors['lateral']:
            lat_string = lat_string + " {}".format(hex(detector['obj'].i2c_address))
            # self._logger.debug("\t\t{}: {}".format(
        self._logger.debug("\tLateral: " + lat_string)

        # Set the display height. This is needed for some display calculations
        self._matrix = {'width': 64, 'height': 32 }
        self._display_som = "imperial"
        self._state = 'ready'
        self._position = {}
        self._quality = {}
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
    def quality(self):
        return self._quality

    @property
    def position(self):
        self._scan_detectors()
        return self._position

    # Get number of lateral detectors. This is used to pass to the display and set up layers correctly.
    @property
    def lateral_count(self):
        self._logger.debug("Lateral count requested. Lateral detectors: {}".format(self._detectors['lateral']))
        return len(self._detectors['lateral'])

    # Scans
    def _scan_detectors(self):
        self._position = {}
        self._quality = {}
        # Longitudinal offset.
        self._position['lo'] = self._detectors['range'].value.to(self._output_unit)
        self._quality['lo'] = self._detectors['range'].quality
        self._logger.debug("Scan Detector set longitudinal position to {} and quality to {}".
                           format(self._position['lo'],self._quality['lo']))
        if len(self._detectors['lateral']) > 0:
            i = 0
            self._position['la'] = {}
            self._quality['la'] = {}
            for lateral in self._detectors['lateral']:
                zone_name = 'zone_' + str( i + 1 )
                # Has the vehicle reached the intercept range for this lateral sensor?
                # If not, we return "NI", Not Intercepted.
                if self._position['lo'] <= self._detectors['lateral'][i]['intercept']:
                    detector_value = self._detectors['lateral'][i]['obj'].value
                    if isinstance(detector_value,str):
                        self._position['la'][zone_name] = 'BR'
                        self._quality['la'][zone_name] = 'BR'
                    else:
                        self._position['la'][zone_name] = detector_value.to(self._output_unit)
                        self._quality['la'][zone_name] = self._detectors['lateral'][i]['obj'].quality
                else:
                    self._position['la'][zone_name] = 'NI'
                    self._quality['la'][zone_name] = 'NI'
                i += 1
        else:
            self._position['la'] = None
            self._quality['la'] = None

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
            self._logger.debug("Entering state {}".format(input))
            self._logger.debug("Detectors: {}".format(self._detectors))
            # When entering docking or undocking state, start ranging on the sensors.
            for detector in self._detectors:
                self._logger.debug("Activating detector {}".format(detector))
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
            {'topic': 'bay_state', 'message': self.state, 'repeat': False, 'topic_mappings': {'bay_id': self._bay_id}}
        )
        # Only generate  positioning messages if 1) we're  docking or undocking or 2)  a verify has been explicitly requested.
        if verify or self.state in ('docking','undocking'):
            outbound_messages.append(
                {'topic': 'bay_position', 'message': self.position, 'repeat': False, 'topic_mappings': {'bay_id': self._bay_id}}
            )
            outbound_messages.append(
                {'topic': 'bay_quality', 'message': self.quality, 'repeat': False, 'topic_mappings': {'bay_id': self._bay_id}}
            )
            outbound_messages.append(
                {'topic': 'bay_occupied', 'message': self.occupied, 'repeat': False, 'topic_mappings': {'bay_id': self._bay_id}}
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
        self._logger.error("Beginning shutdown...")
        self._logger.error("Shutting off detectors...")
        self._shutdown_detectors(self._detectors)
        self._logger.error("Shutdown complete. Exiting.")

    # Traverse the detectors and make sure they're all stopped.
    def _shutdown_detectors(self,detectors):
        if isinstance(detectors,list):
            for i in range(len(detectors)):
                # Call nested lists iteratively.
                if isinstance(detectors[i],list) or isinstance(detectors[i],dict):
                    self._shutdown_detectors(detectors[i])
                # If it's a Detector, it has shutdown, call it.
                elif isinstance(detectors[i], Detector):
                    detectors[i].shutdown()
        elif isinstance(detectors,dict):
            for item in detectors:
                # Call nested lists and dicts iteratively.
                if isinstance(detectors[item],list) or isinstance(detectors[item],dict):
                    self._shutdown_detectors(detectors[item])
                # If it's a Detector, it has shutdown, call it.
                elif isinstance(detectors[item], Detector):
                    detectors[item].shutdown()

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
        self._logger.debug("Setting up range detector.")
        self._setup_range(config,detectors)
        # Lateral configuration.
        # Make the lateral array.
        self._detectors['lateral'] = []
        self._logger.debug("Setting up lateral detectors.")
        for detector_config in config['lateral']['detectors']:
            detector_name = detector_config['detector']
            try:
                lateral_obj = detectors[detector_name]
            except KeyError:
                raise KeyError("Tried to create lateral zone with detector '{}' but detector not defined."
                               .format(detector_name))
            # Now we have the detector, set it up right.
            for item in ('offset','spread_ok','spread_warn','spread_crit','side'):
                try:
                    setattr(lateral_obj, item, detector_config[item])
                except KeyError:
                    self._logger.debug("Using default value for {}".format(item))
                    try:
                        setattr(lateral_obj,item,config['lateral']['defaults'][item])
                    except KeyError:
                        raise KeyError("Needed default value for {} but not defined!".format(item))
            self._logger.debug("Lateral now has settings: {}".format(lateral_obj._settings))

            # Append it to the lateral array.
            self._detectors['lateral'].append({'obj': lateral_obj, 'intercept': Quantity(detector_config['intercept'])})

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
        self._logger.info("Setting parking spread to: {}".format(config['range']['spread_park']))
        self._detectors['range'].spread_park = config['range']['spread_park']
        try:
            self._logger.info("Setting range detector warn to: {}".format(config['range']['pct_warn']))
            self._detectors['range'].bay_depth = config['range']['pct_warn']
        except KeyError:
            pass
        try:
            self._logger.info("Setting range detector warn to: {}".format(config['range']['pct_crit']))
            self._detectors['range'].bay_depth = config['range']['pct_crit']
        except KeyError:
            pass