####
# Cobray Bay - The Bay!
####
import pint.errors

from .detector import Detector, Range, Lateral
from pint import UnitRegistry, Quantity
from PIL import Image, ImageDraw
from .detector import CB_VL53L1X
import logging

class Bay:
    def __init__(self,config,detectors):
        # Set the Bay ID. This is static for testing, real config processing will come later.
        self._detectors = None
        self.bay_id = 'bay1'
        try:
            self.bay_name = config['name']
        except KeyError:
            self.bay_name = self.bay_id
        # Create a logger.
        self._logger = logging.getLogger("CobraBay").getChild(self.bay_id)
        self._logger.setLevel(logging.DEBUG)
        # Log our initialization.
        self._logger.info("Bay '{}' initializing...".format(self.bay_id))
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
        self._logger.debug("\tLongitudinal - ")
        for detector in self._detectors['longitudinal']:
            self._logger.debug("\t\t{} - {}".format(detector, hex(self._detectors['longitudinal'][detector].i2c_address)))
        self._logger.debug("\tLateral - ")
        for detector in self._detectors['lateral'].keys():
            self._logger.debug("\t\t{} - {}".format(detector, hex(self._detectors['lateral'][detector].i2c_address)))

        # Set the display height. This is needed for some display calculations
        self._matrix = {'width': 64, 'height': 32 }
        self._display_som = "imperial"
        self._state = 'ready'
        self._position = {}
        self._quality = {}
        self._logger.info("Bay '{}' initialization complete.".format(self.bay_id))

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

    # Method to get info to pass to the Network module and register.
    def discovery_info(self):
        # For discovery, the detector hierarchy doesn't matter, so we can flatten it.
        return_dict = {
            'bay_id': self.bay_id,
            'bay_name': self.bay_name,
            'detectors': []
        }
        for direction in self._detectors:
            for item in self._detectors[direction]:
                detector = {
                    'detector_id': item,
                    'name': self._detectors[direction][item].name
                }
                return_dict['detectors'].append(detector)

        return return_dict

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
        self._position = { 'longitudinal': {}, 'lateral': {} }
        self._quality = { 'longitudinal': {}, 'lateral': {} }
        self._logger.debug("Starting detector scan.")
        self._logger.debug("Have detectors: {}".format(self._detectors))
        # Longitudinal offset.
        self._logger.debug("Checking longitudinal detectors.")
        for detector in self._detectors['longitudinal']:
            value = self._detectors['longitudinal'][detector].value
            self._logger.debug("Read of longitudinal detector {} returned {}".format(detector, value))
            self._position['longitudinal'][detector] = self._detectors['longitudinal'][detector].value.to(self._output_unit)
            self._quality['longitudinal'][detector] = self._detectors['longitudinal'][detector].quality
        # Pick a reading for authoritative range.
        # If there's only one longitudinal sensor, we go with that.
        if len(self._detectors['longitudinal']) == 1:
            self._selected_range = list(self._detectors['longitudinal'].keys())[0]
        self._logger.debug("Selected range detector: {}".format(self._selected_range))
        for detector_name in self._detectors['lateral']:
            self._logger.debug("Checking {}".format(detector_name))
            # Give the lateral detector the current range reading.
            self._detectors['lateral'][detector_name].range_reading = self._position['longitudinal'][self._selected_range]
            # Now we can get the position and quality from the detector.
            self._position['lateral'][detector_name] = self._detectors['lateral'][detector_name].value.to(self._output_unit)
            self._quality['lateral'][detector_name] = self._detectors['lateral'][detector_name].quality
        #     # Has the vehicle reached the intercept range for this lateral sensor?
        #     # If not, we return "NI", Not Intercepted.
        #     if self._position['lo'] <= self._detectors['lateral'][detector_name]['intercept']:
        #         detector_value = self._detectors['lateral'][detector_name]['obj'].value
        #             if isinstance(detector_value,str):
        #             self._position['la'][detector_name] = 'BR'
        #                 self._quality['la'][detector_name] = 'BR'
        #             else:
        #                 self._position['la'][detector_name] = detector_value.to(self._output_unit)
        #                 self._quality['la'][detector_name] = self._detectors['lateral'][detector_name]['obj'].quality
        #         else:
        #             self._position['la'][detector_name] = 'NI'
        #             self._quality['la'][detector_name] = 'NI'
        #         i += 1
        # else:
        #     self._position['la'] = None
        #     self._quality['la'] = None

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
            self._detector_state('activate')
        if input not in ('docking','undocking') and self._state in ('docking', 'undocking'):
            self._detector_state('deactivate')

    # MQTT status methods. These generate payloads the core network handler can send upward.
    def mqtt_messages(self,verify=False):
        outbound_messages = [] # topic, message, repease, topic_mappings
        # State message.
        outbound_messages.append(
            {'topic_type': 'bay', 'topic': 'bay_state', 'message': self.state, 'repeat': False, 'topic_mappings': {'bay_id': self.bay_id}}
        )
        # Only generate  positioning messages if 1) we're  docking or undocking or 2)  a verify has been explicitly requested.
        if verify or self.state in ('docking','undocking'):
            outbound_messages.append(
                {'topic_type': 'bay', 'topic': 'bay_position', 'message': self.position, 'repeat': False, 'topic_mappings': {'bay_id': self.bay_id}}
            )
            outbound_messages.append(
                {'topic_type': 'bay', 'topic': 'bay_quality', 'message': self.quality, 'repeat': False, 'topic_mappings': {'bay_id': self.bay_id}}
            )
            outbound_messages.append(
                {'topic_type': 'bay', 'topic': 'bay_occupied', 'message': self.occupied, 'repeat': False, 'topic_mappings': {'bay_id': self.bay_id}}
            )
        return outbound_messages

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

    # Traverse the detectors dict, activate everything that needs activating.
    def _detector_state(self,mode):
        if mode not in ('activate','deactivate'):
            raise ValueError("Bay can only set detector states to 'activate', or 'deactivate'")
        # Traverse the dict looking for detectors that need activation.
        for direction in ('longitudinal','lateral'):
            for detector in self._detectors[direction]:
                if isinstance(self._detectors[direction][detector],CB_VL53L1X):
                    if mode == 'activate':
                        self._detectors[direction][detector].activate()
                    elif mode == 'deactivate':
                        self._detectors[direction][detector].deactivate()
                    else:
                        raise RuntimeError("Detector activation reached impossible state.")


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
        # Initialize the detector dicts.
        self._detectors = {
            'longitudinal': {},
            'lateral': {}
        }
        self._lateral_order = {}

        config_options = {
            'longitudinal': ('offset','spread_park','bay_depth'),
            'lateral': ('offset','spread_ok','spread_warn','spread_crit','side','intercept')
        }
        for direction in self._detectors.keys():
            self._logger.debug("Setting up {} detectors.".format(direction))
            for detector_config in config[direction]['detectors']:
                self._logger.debug("Provided detector config: {}".format(detector_config))
                try:
                    detector_obj = detectors[detector_config['detector']]
                except KeyError:
                    raise KeyError("Tried to create lateral zone with detector '{}' but detector not defined."
                                   .format(detector_config['detector']))
                # Set the object attributes from the configuration.
                for item in config_options[direction]:
                    try:
                        setattr(detector_obj, item, detector_config[item])
                    except KeyError:
                        self._logger.debug("Using default value for {}".format(item))
                        try:
                            setattr(detector_obj, item, config[direction]['defaults'][item])
                        except KeyError:
                            raise KeyError("Needed default value for {} but not defined!".format(item))
                # # If we're processing lateral, add the intercept range to the lateral order dict.
                # if direction == 'lateral':
                #     self._lateral_order[Quantity(detector_config['intercept'])] = detector_config['detector']
                # Append the object to the appropriate object store.
                self._detectors[direction][detector_config['detector']] = detector_obj

    # # Method to set up the range detector
    # def _setup_range(self,config,detectors):
    #     # Is the detector name specified.
    #     try:
    #         range_detector_name = config['range']['detector']
    #     except KeyError:
    #         raise KeyError("Detector is not defined for bay's range. This is required!")
    #     # Try to get the detector.
    #     try:
    #         self._detectors['range'] = detectors[range_detector_name]
    #     except KeyError:
    #         raise KeyError("Provided detector name '{}' does not exist.".format(range_detector_name))
    #     # Add the required range parameters.
    #     self._logger.info("Setting range detector offset to: {}".format(config['range']['offset']))
    #     self._detectors['range'].offset = config['range']['offset']
    #     self._logger.info("Setting range detector bay depth to: {}".format(config['range']['bay_depth']))
    #     self._detectors['range'].bay_depth = config['range']['bay_depth']
    #     self._logger.info("Setting parking spread to: {}".format(config['range']['spread_park']))
    #     self._detectors['range'].spread_park = config['range']['spread_park']
    #     try:
    #         self._logger.info("Setting range detector warn to: {}".format(config['range']['pct_warn']))
    #         self._detectors['range'].bay_depth = config['range']['pct_warn']
    #     except KeyError:
    #         pass
    #     try:
    #         self._logger.info("Setting range detector warn to: {}".format(config['range']['pct_crit']))
    #         self._detectors['range'].bay_depth = config['range']['pct_crit']
    #     except KeyError:
    #         pass