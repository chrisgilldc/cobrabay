####
# Cobra Bay - The Bay!
####
import time
from .detector import Detector
from pint import UnitRegistry, Quantity
from time import monotonic
from .detector import CB_VL53L1X
import logging


class Bay:
    def __init__(self, bay_id, config, detectors):
        # Get our settings.
        self._settings = config.bay(bay_id)
        # Create a logger.
        self._logger = logging.getLogger("CobraBay").getChild(self.bay_id)
        self._logger.setLevel(config.get_loglevel(bay_id))

        # Initialize variables.
        self._position = {}
        self._quality = {}
        self._lateral_order = {}
        self._detectors = {}
        self._state = None
        self._occupancy = None

        # Log our initialization.
        self._logger.info("Bay '{}' initializing...".format(self.bay_id))
        self._logger.debug("Bay received config: {}".format(config))
        # Create a unit registry.
        self._ureg = UnitRegistry

        # Set up the detectors.
        self._setup_detectors(detectors)
        self._logger.debug("Detectors configured:")
        self._logger.debug("\tLongitudinal - ")
        for detector in self._detectors['longitudinal'].keys():
            self._logger.debug("\t\t{} - {}".format(detector,
                                                self._detectors['longitudinal'][detector].sensor_interface.addr))
        for detector in self._detectors['lateral'].keys():
            self._logger.debug("\t\t{} - {}".
                               format(detector, self._detectors['lateral'][detector].sensor_interface.addr))

        # Dock timer.
        self._dock_timer = {
            'allowed': self._settings['park_time'],
            'mark': None
        }

        # Set our initial state.
        self._scan_detectors()
        if self._check_occupancy():
            self._occupancy = 'Occupied'
        else:
            self._occupancy = 'Unoccupied'

        self._logger.info("Bay '{}' initialization complete.".format(self.bay_id))
        self.state = "Ready"

    # Abort gets called when we want to cancel a docking.
    def abort(self):
        # Scan the detectors once
        self._scan_detectors()
        if self._check_occupancy():
            self._occupancy = 'Occupied'
        else:
            self._occupancy= 'Unoccupied'

    # Method to get info to pass to the Network module and register.
    @property
    def discovery_reg_info(self):
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
                    'name': self._detectors[direction][item].name,
                    'type': self._detectors[direction][item].detector_type
                }
                return_dict['detectors'].append(detector)

        return return_dict

    @property
    def display_reg_info(self):
        return_dict = {
            'bay_id': self.bay_id,
            'lateral_order': self._lateral_order
        }
        return return_dict

    # Bay properties
    @property
    def occupied(self):
        """
        Occupancy state of the bay, derived from the State.
        If positively occupied or not, returns that, otherwise 'unknown'.

        :returns: bay occupancy state
        :rtype: String
        """
        return self._occupancy

    # How good is the parking job?
    @property
    def quality(self):
        return {**self._quality['longitudinal'], **self._quality['lateral']}

    @property
    def position(self):
        return {**self._position['longitudinal'], **self._position['lateral']}

    # Get number of lateral detectors. This is used to pass to the display and set up layers correctly.
    @property
    def lateral_count(self):
        self._logger.debug("Lateral count requested. Lateral detectors: {}".format(self._detectors['lateral']))
        return len(self._detectors['lateral'])

    # Public method to scan detectors.
    def scan(self):
        # Scan the detectors and get fresh data.
        self._scan_detectors()

        # If we're in a dock/undock state, check for motion and if necessary reset the parking clock.
        if self.state in ('docking', 'undocking'):
            # Update the dock timer.
            if self._detectors['longitudinal'].motion:
                # If motion is detected, update the time mark to the current time.
                self._logger.debug("Motion found, resetting dock timer.")
                self._dock_timer['mark'] = time.monotonic()
            else:
                if self._detectors['longitudinal'].motion is not None:
                    self._logger.debug("No motion found, checking for dock timer expiry.")
                    # No motion, check for completion
                    if time.monotonic() - self._dock_timer['mark'] >= self._dock_timer['allowed']:
                        self._logger.debug("Motion timer expired. Doing an occupancy check.")
                        if self._check_occupancy():
                            self._occupancy = True
                        else:
                            self._occupancy = False

    # Tells the detectors to update.
    def _scan_detectors(self):
        self._position = {'longitudinal': {}, 'lateral': {}}
        self._quality = {'longitudinal': {}, 'lateral': {}}
        self._logger.debug("Starting detector scan.")
        self._logger.debug("Have detectors: {}".format(self._detectors))
        # Longitudinal offset.
        self._logger.debug("Checking longitudinal detector.")
        for detector_name in self._detectors['longitudinal']:
            value = self._detectors['longitudinal'][detector_name].value
            self._logger.debug("Read of longitudinal detector {} returned {}".format(
                self._detectors['longitudinal'][detector_name].name, value))
            if isinstance(value, Quantity):
                # If we got a proper Quantity, convert to our output unit.
                self._position['longitudinal'][detector_name] = value.to(self._settings['output_unit'])
            else:
                self._position['longitudinal'][detector_name] = value
            self._quality['longitudinal'][detector_name] = self._detectors['longitudinal'][detector_name].quality
        # Choose a detector to be the official range.
        # Currently only support one range detector, so this is easy!
        self._selected_longitudinal = list(self._position['longitudinal'].keys())[0]

        for detector_name in self._detectors['lateral']:
            self._logger.debug("Checking {}".format(detector_name))
            # Give the lateral detector the current range reading.
            self._detectors['lateral'][detector_name].range_reading = self._position['longitudinal']
            # Now we can get the position and quality from the detector.
            value = self._detectors['lateral'][detector_name].value
            if isinstance(value, Quantity):
                self._position['lateral'][detector_name] = value.to(self._settings['output_unit'])
            else:
                self._position['lateral'][detector_name] = value
            self._quality['lateral'][detector_name] = self._detectors['lateral'][detector_name].quality

    # Method to check occupancy.
    def _check_occupancy(self):
        self._logger.debug("Checking for occupancy.")
        self._logger.debug("Longitudinal is {}".format(self._quality['longitudinal']))
        # First cut is the range.
        if self._quality['longitudinal'] in ('No object', 'Door open'):
            # If the detector can hit the garage door, or the door is open, then clearly nothing is in the way, so
            # the bay is vacant.
            self._logger.debug("Longitudinal quality is {}, not occupied.".format(self._quality['longitudinal']))
            return False
        if self._quality['longitudinal'] in ('Emergency!', 'Back up', 'Park', 'Final', 'Base'):
            # If the detector is giving us any of the 'close enough' qualities, there's something being found that
            # could be a vehicle. Check the lateral sensors to be sure that's what it is, rather than somebody blocking
            # the sensors or whatnot
            self._logger.debug("Longitudinal quality is {}, could be occupied.".format(self._quality['longitudinal']))
            lat_score = 0
            for detector in self._quality['lateral']:
                if self._quality['lateral'][detector] in ('OK', 'Warning', 'Critical'):
                    # No matter how badly parked the vehicle is, it's still *there*
                    lat_score += 1
            self._logger.debug("Achieved lateral score {} of {}".format(lat_score, len(self._quality['lateral'])))
            if lat_score == len(self._quality['lateral']):
                # All sensors have found something more or less in the right place, so yes, we're occupied!
                return True
        # If for some reason we drop through to here, assume we're not occupied.
        return False

    # Method to check the range sensor for motion.
    def monitor(self):
        vector = self._detectors['longitudinal'][self._selected_longitudinal].vector
        # If there's motion, change state.
        if vector['direction'] == 'forward':
            self.state = 'docking'
        elif vector['direction'] == 'reverse':
            self.state = 'undocking'
        elif self._detectors['longitudinal'][self._selected_longitudinal].value == 'Weak':
            self.state = 'docking'

    @property
    def state(self):
        """
        Operating state of the bay.
        Can be one of 'docking', 'undocking', 'ready', 'unavailable'.

        :returns Bay state
        :rtype: String
        """
        return self._state

    @state.setter
    def state(self, m_input):
        self._logger.debug("State change requested to {} from {}".format(m_input, self._state))
        # Trap invalid bay states.
        if m_input.lower() not in ('ready', 'docking', 'undocking', 'unavailable'):
            raise ValueError("{} is not a valid bay state.".format(m_input))
        self._logger.debug("Old state: {}, new state: {}".format(self._state, m_input))
        if m_input.lower() in ('docking', 'undocking') and self._state not in ('docking', 'undocking'):
            self._logger.debug("Entering state: {}".format(m_input))
            self._logger.debug("Start time: {}".format(monotonic()))
            self._logger.debug("Detectors: {}".format(self._detectors))
            # When entering docking or undocking state, start ranging on the sensors.
            self._detector_state('activate')
            # Set the start time.
            self._dock_timer['mark'] = monotonic()
        if m_input.lower() not in ('docking', 'undocking') and self._state in ('docking', 'undocking'):
            self._logger.debug("Entering state: {}".format(input))
            # Deactivate the detectors.
            self._detector_state('deactivate')
            # Reset some variables.
            self._dock_timer['mark'] = None
        # Now store the state.
        self._state = m_input

    # MQTT status methods. These generate payloads the core network handler can send upward.
    def mqtt_messages(self, verify=False):
        # Initialize the outbound message list.
        # Always include the bay state and bay occupancy.
        outbound_messages = [
            # Bay state.
            {'topic_type': 'bay', 'topic': 'bay_state', 'message': self.state, 'repeat': False,
             'topic_mappings': {'bay_id': self.bay_id}},
            # Bay occupancy.
            {'topic_type': 'bay', 'topic': 'bay_occupied', 'message': self.occupied, 'repeat': False,
             'topic_mappings': {'bay_id': self.bay_id}}]
        # State message.
        # Only generate positioning messages if
        # 1) we're  docking or undocking or
        # 2) a verify has been explicitly requested.
        if verify or self.state in ('docking', 'undocking'):
            outbound_messages.append(
                {'topic_type': 'bay',
                 'topic': 'bay_position',
                 'message': self.position,
                 'repeat': False,
                 'topic_mappings': {'bay_id': self.bay_id}}
            )
            outbound_messages.append(
                {'topic_type': 'bay',
                 'topic': 'bay_quality',
                 'message': self.quality,
                 'repeat': False,
                 'topic_mappings': {'bay_id': self.bay_id}}
            )

            outbound_messages.append(
                {'topic_type': 'bay',
                 'topic': 'bay_speed',
                 'message': self._detectors['longitudinal'][self._selected_longitudinal].vector,
                 'repeat': False, 'topic_mappings': {'bay_id': self.bay_id}}
            )
            outbound_messages.append(
                {'topic_type': 'bay',
                 'topic': 'bay_motion',
                 'message': self._detectors['longitudinal'][self._selected_longitudinal].motion,
                 'repeat': False, 'topic_mappings': {'bay_id': self.bay_id}}
            ),
            outbound_messages.append(
                {'topic_type': 'bay',
                 'topic': 'bay_dock_time',
                 'message': self._dock_timer['allowed'] - (monotonic() - self._dock_timer['mark']),
                 'repeat': True,
                 'topic_mappings': {'bay_id': self.bay_id}}
            )
        self._logger.debug("Have compiled outbound messages. {}".format(outbound_messages))
        return outbound_messages

    # Send collect data needed to send to the display. This is syntactically shorter than the MQTT messages.
    def display_data(self):
        return_data = {'bay_id': self.bay_id}
        # Give only the range reading of the selected range sensor. The display will only use one of them.
        return_data['range'] = self._position['longitudinal']
        # The range quality band. This is used for color coding.
        return_data['range_quality'] = self._quality['longitudinal']
        # Percentage of range covered. This is used to construct the strobe.
        # If it's not a Quantity, just return zero.
        if isinstance(return_data['range'], Quantity):
            return_data['range_pct'] = return_data['range'].to('cm') / self._settings['adjusted_depth'].to('cm')
        else:
            return_data['range_pct'] = 0
        # List for lateral state.
        return_data['lateral'] = []
        self._logger.debug("Using lateral order: {}".format(self._lateral_order))
        # Assemble the lateral data with *closest first*.
        # This will result in the display putting things together top down.
        # Lateral ordering is determined by intercept range when bay is started up.
        if self._lateral_order is not None:
            for lateral_detector in self._lateral_order:
                return_data['lateral'].append({
                    'name': lateral_detector,
                    'quality': self._quality['lateral'][lateral_detector],
                    'side': self._detectors['lateral'][lateral_detector].side}
                )
        return return_data

    # Method to be called when CobraBay it shutting down.
    def shutdown(self):
        self._logger.error("Beginning shutdown...")
        self._logger.error("Shutting off detectors...")
        self._shutdown_detectors(self._detectors)
        self._logger.error("Shutdown complete. Exiting.")

    # Traverse the detectors dict, activate everything that needs activating.
    def _detector_state(self, mode):
        if mode not in ('activate', 'deactivate'):
            raise ValueError("Bay can only set detector states to 'activate', or 'deactivate'")
        self._logger.debug("Traversing detectors to {}".format(mode))
        # Traverse the dict looking for detectors that need activation.
        for direction in ('longitudinal', 'lateral'):
            for detector in self._detectors[direction]:
                self._logger.debug("Changing detector {}".format(detector))
                if isinstance(self._detectors[direction][detector], CB_VL53L1X):
                    if mode == 'activate':
                        self._detectors[direction][detector].activate()
                    elif mode == 'deactivate':
                        self._detectors[direction][detector].deactivate()
                    else:
                        raise RuntimeError("Detector activation reached impossible state.")

    # Traverse the detectors and make sure they're all stopped.
    def _shutdown_detectors(self, detectors):
        if isinstance(detectors, list):
            for i in range(len(detectors)):
                # Call nested lists iteratively.
                if isinstance(detectors[i], list) or isinstance(detectors[i], dict):
                    self._shutdown_detectors(detectors[i])
                # If it's a Detector, it has shutdown, call it.
                elif isinstance(detectors[i], Detector):
                    detectors[i].shutdown()
        elif isinstance(detectors, dict):
            for item in detectors:
                # Call nested lists and dicts iteratively.
                if isinstance(detectors[item], list) or isinstance(detectors[item], dict):
                    self._shutdown_detectors(detectors[item])
                # If it's a Detector, it has shutdown, call it.
                elif isinstance(detectors[item], Detector):
                    detectors[item].shutdown()

    @property
    def bay_id(self):
        return self._settings['bay_id']

    @bay_id.setter
    def bay_id(self, input):
        self._settings['bay_id'] = input

    @property
    def bay_name(self):
        return self._settings['bay_name']

    @bay_name.setter
    def bay_name(self, input):
        self._settings['bay_name'] = input

    # Method to set up the detectors for the bay. This applies bay-specific options to the individual detectors, which
    # are initialized by the main routine.
    def _setup_detectors(self, detectors):
        # Initialize the detector dicts.
        self._detectors = {
            'longitudinal': {},
            'lateral': {}
        }
        lateral_order = {}
        config_options = {
            'longitudinal': ('offset', 'bay_depth', 'spread_park'),
            'lateral': ('offset', 'spread_ok', 'spread_warn', 'side', 'intercept')
        }
        for direction in self._detectors.keys():
            self._logger.debug("Checking for {} detectors.".format(direction))
            if direction in self._settings:
                self._logger.debug("Setting up {} detectors.".format(direction))
                for detector_config in self._settings[direction]['detectors']:
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
                                setattr(detector_obj, item, self._settings[direction]['defaults'][item])
                            except KeyError:
                                raise KeyError("Needed default value for {} but not defined!".format(item))
                    # # If we're processing lateral, add the intercept range to the lateral order dict.
                    if direction == 'lateral':
                        lateral_order[detector_config['detector']] = Quantity(detector_config['intercept'])
                    # Append the object to the appropriate object store.
                    self._detectors[direction][detector_config['detector']] = detector_obj
            else:
                self._logger.debug("No detectors defined.")
        # Check for lateral order.
        if lateral_order is not None:
            self._logger.debug("Now have lateral order: {}".format(lateral_order))
            self._lateral_order = sorted(lateral_order, key=lateral_order.get)
            self._logger.debug("Sorted lateral order: {}".format(self._lateral_order))
