####
# Cobra Bay - The Bay!
####
import time
from .detector import Detector, Lateral, Range
from pint import UnitRegistry, Quantity
from time import monotonic
from .detector import CB_VL53L1X
import logging
import pprint
from functools import wraps


# Scan the detectors if we're asked for a property that needs a fresh can and we haven't scanned recently enough.
def scan_if_stale(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        time_delta = time.monotonic() - self._previous_scan_ts
        if time_delta > 1:  # 1s is too long, read the sensor.
            do_scan = True
            self._logger.debug("Stale, do scan.")
        else:
            do_scan = False
            self._logger.debug("Not stale, no scan needed.")

        # If flag is set, read the sensor and put its value into the history.
        if do_scan:
            self._scan_detectors()
            self._previous_scan_ts = time.monotonic()

        # Send whichever value it is into the function.
        return func(self)

    return wrapper


class Bay:
    def __init__(self, bay_id, config, detectors):
        pp = pprint.PrettyPrinter()
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
        self._previous_scan_ts = 0
        self._state = None
        self._occupancy = None

        # Log our initialization.
        self._logger.info("Bay '{}' initializing...".format(self.bay_id))
        self._logger.debug("Bay received config: {}".format(config))
        pp.pprint(self._settings)
        # Create a unit registry.
        self._ureg = UnitRegistry

        # Store the detector objects
        self._detectors = detectors
        # Apply our configurations to the detectors.
        self._setup_detectors()
        self._logger.debug("Detectors configured:")
        for detector in self._detectors.keys():
            self._logger.debug("\t\t{} - {}".format(detector,
                                                    self._detectors[detector].sensor_interface.addr))

        # Activate detectors.
        self._detector_state('activate')

        # Dock timer.
        self._dock_timer = {
            'allowed': self._settings['park_time'],
            'mark': None
        }

        # Set our initial state.
        self._scan_detectors()

        self._logger.info("Bay '{}' initialization complete.".format(self.bay_id))
        self.state = "Ready"

    # Abort gets called when we want to cancel a docking.
    def abort(self):
        self.state = "Ready"

    # Method to get info to pass to the Network module and register.
    @property
    def discovery_reg_info(self):
        # For discovery, the detector hierarchy doesn't matter, so we can flatten it.
        return_dict = {
            'bay_id': self.bay_id,
            'bay_name': self.bay_name,
            'detectors': []
        }
        for item in self._detectors:
            detector = {
                'detector_id': item,
                'name': self._detectors[item].name,
                'type': self._detectors[item].detector_type
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
    @scan_if_stale
    def occupied(self):
        """
        Occupancy state of the bay, derived from the State.
        If positively occupied or not, returns that, otherwise 'unknown'.

        :returns: bay occupancy state
        :rtype: String
        """
        if self._check_occupancy():
            return 'Occupied'
        else:
            return 'Unoccupied'

    # How good is the parking job?
    @property
    @scan_if_stale
    def quality(self):
        return self._quality

    @property
    @scan_if_stale
    def position(self):
        return self._position

    # Get number of lateral detectors. This is used to pass to the display and set up layers correctly.
    @property
    def lateral_count(self):
        self._logger.debug("Lateral count requested. Lateral detectors: {}".format(self._detectors['lateral']))
        return len(self._detectors['lateral'])

    # # Public method to scan detectors.
    # def scan(self):
    #     self._logger.debug("Running detector scan.")
    #     # Scan the detectors and get fresh data.
    #     self._scan_detectors()
    #     self._logger.debug("Evaluating for timer expiration.")
    #     # Update the dock timer.
    #     if self._detectors[self._settings['detectors']['selected_range']].motion:
    #         # If motion is detected, update the time mark to the current time.
    #         self._logger.debug("Motion found, resetting dock timer.")
    #         self._dock_timer['mark'] = time.monotonic()
    #     else:
    #         self._logger.debug("No motion found, checking for dock timer expiry.")
    #         # No motion, check for completion
    #         if time.monotonic() - self._dock_timer['mark'] >= self._dock_timer['allowed']:
    #             # Set self back to ready.
    #             self.state = 'Ready'

    # Tells the detectors to update.
    # Note, this does NOT trigger timer operations.
    def _scan_detectors(self, filter_lateral=True):
        self._logger.debug("Starting detector scan.")
        self._logger.debug("Have detectors: {}".format(self._detectors))
        # Staging dicts. This makes sure we wipe any items that need to be wiped.
        position = {}
        quality = {}
        # Check all the detectors.
        for detector_name in self._detectors:
            position[detector_name] = self._detectors[detector_name].value
            quality[detector_name] = self._detectors[detector_name].quality
            self._logger.debug("Read of detector {} returned value '{}' and quality '{}'".
                               format(self._detectors[detector_name].name, position[detector_name],
                                      quality[detector_name]))

        if filter_lateral:
            for lateral_name in self._settings['detectors']['lateral']:
                # If intercept range hasn't been met yet, we wipe out any value, it's meaningless.
                if self._settings['detectors']['intercepts'][lateral_name] < \
                        position[self._settings['detectors']['selected_range']]:
                    quality[lateral_name] = "Not Intercepted"

        self._position = position
        self._quality = quality

    # Method to check occupancy.
    def _check_occupancy(self):
        # Do a new scan and *don't* filter out non-intercepted laterals. We need to
        self._scan_detectors(filter_lateral=False)
        self._logger.debug("Checking for occupancy.")
        self._logger.debug("Longitudinal is {}".format(self._quality[self._settings['detectors']['selected_range']]))
        # First cut is the range.
        if self._quality[self._settings['detectors']['selected_range']] in ('No object', 'Door open'):
            # If the detector can hit the garage door, or the door is open, then clearly nothing is in the way, so
            # the bay is vacant.
            self._logger.debug("Longitudinal quality is {}, not occupied.".
                               format(self._quality[self._settings['detectors']['selected_range']]))
            return False
        if self._quality[self._settings['detectors']['selected_range']] in ('Emergency!', 'Back up', 'Park', 'Final', 'Base'):
            # If the detector is giving us any of the 'close enough' qualities, there's something being found that
            # could be a vehicle. Check the lateral sensors to be sure that's what it is, rather than somebody blocking
            # the sensors or whatnot
            self._logger.debug("Longitudinal quality is {}, could be occupied.".
                               format(self._quality[self._settings['detectors']['selected_range']]))
            lat_score = 0
            max_score = len(self._settings['detectors']['lateral'])
            for detector in self._settings['detectors']['lateral']:
                if self._quality[detector] in ('OK', 'Warning', 'Critical'):
                    # No matter how badly parked the vehicle is, it's still *there*
                    lat_score += 1
            self._logger.debug("Achieved lateral score {} of {}".format(lat_score, max_score))
            if lat_score == max_score:
                # All sensors have found something more or less in the right place, so yes, we're occupied!
                return True
        # If for some reason we drop through to here, assume we're not occupied.
        return False

    # Method to check the range sensor for motion.
    @scan_if_stale
    def monitor(self):
        vector = self._detectors[self._settings['detectors']['selected_range']].vector
        # If there's motion, change state.
        if vector['direction'] == 'forward':
            self.state = 'Docking'
        elif vector['direction'] == 'reverse':
            self.state = 'Undocking'
        elif self._detectors[self._settings['detectors']['selected_range']].value == 'Weak':
            self.state = 'Docking'

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
        if m_input not in ('Ready', 'Docking', 'Undocking', 'Unavailable'):
            raise ValueError("{} is not a valid bay state.".format(m_input))
        self._logger.debug("Old state: {}, new state: {}".format(self._state, m_input))
        if m_input == self._state:
            self._logger.debug("Requested state {} is also current state. No action.".format(m_input))
            return
        if m_input in ('Docking', 'Undocking') and self._state not in ('Docking', 'Undocking'):
            self._logger.debug("Entering state: {}".format(m_input))
            self._dock_timer['mark'] = monotonic()
            self._logger.debug("Start time: {}".format(self._dock_timer['mark']))
            self._logger.debug("Detectors: {}".format(self._detectors))
        if m_input not in ('Docking', 'Undocking') and self._state in ('Docking', 'Undocking'):
            self._logger.debug("Entering state: {}".format(m_input))
            # Reset some variables.
            self._dock_timer['mark'] = None
        # Now store the state.
        self._state = m_input

    # MQTT status methods. These generate payloads the core network handler can send upward.
    def mqtt_messages(self, verify=False):
        # Initialize the outbound message list.
        # Always include the bay state and bay occupancy.
        outbound_messages = [{'topic_type': 'bay', 'topic': 'bay_state', 'message': self.state, 'repeat': False,
                              'topic_mappings': {'bay_id': self.bay_id}},
                             {'topic_type': 'bay',
                              'topic': 'bay_occupied',
                              'message': self.occupied,
                              'repeat': True,
                              'topic_mappings': {'bay_id': self.bay_id}},
                             # {'topic_type': 'bay',
                             #  'topic': 'bay_position',
                             #  'message': self.position,
                             #  'repeat': True,
                             #  'topic_mappings': {'bay_id': self.bay_id}},
                             {'topic_type': 'bay',
                              'topic': 'bay_quality',
                              'message': self.quality,
                              'repeat': True,
                              'topic_mappings': {'bay_id': self.bay_id}},
                             {'topic_type': 'bay',
                              'topic': 'bay_speed',
                              'message': self._detectors[self._settings['detectors']['selected_range']].vector,
                              'repeat': True,
                              'topic_mappings': {'bay_id': self.bay_id}}]
        # Positions for all the detectors.
        for detector in self._detectors:
            outbound_messages.append(
                {'topic_type': 'bay',
                 'topic': 'bay_position',
                 'message': {
                     'adjusted_reading': self._detectors[detector].value,
                     'raw_reading': self._detectors[detector].value_raw
                    },
                 'repeat': False,
                 'topic_mappings': {'bay_id': self.bay_id, 'detector_id': self._detectors[detector].id }
                 }
            )

        if self._dock_timer['mark'] is None:
            message = 'offline'
        else:
            message = self._dock_timer['allowed'] - (monotonic() - self._dock_timer['mark'])
        outbound_messages.append(
            {'topic_type': 'bay',
             'topic': 'bay_dock_time',
             'message': message,
             'repeat': True,
             'topic_mappings': {'bay_id': self.bay_id}}
        )
        self._logger.debug("Have compiled outbound messages. {}".format(outbound_messages))
        return outbound_messages

    # Send collect data needed to send to the display. This is syntactically shorter than the MQTT messages.
    def display_data(self):
        return_data = {'bay_id': self.bay_id, 'bay_state': self.state,
                       'range': self._position[self._settings['detectors']['selected_range']],
                       'range_quality': self._quality[self._settings['detectors']['selected_range']]}
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
                    'quality': self._quality[lateral_detector],
                    'side': self._detectors[lateral_detector].side}
                )
        return return_data

    # Method to be called when CobraBay it shutting down.
    def shutdown(self):
        self._logger.error("Beginning shutdown...")
        self._logger.error("Shutting off detectors...")
        self._detector_state('deactivate')
        self._logger.error("Shutdown complete. Exiting.")

    # Traverse the detectors dict, activate everything that needs activating.
    def _detector_state(self, mode):
        if mode not in ('activate', 'deactivate'):
            raise ValueError("Bay can only set detector states to 'activate', or 'deactivate'")
        self._logger.debug("Traversing detectors to {}".format(mode))
        # Traverse the dict looking for detectors that need activation.
        for detector in self._detectors:
            self._logger.debug("Changing detector {}".format(detector))
            if isinstance(self._detectors[detector], CB_VL53L1X):
                if mode == 'activate':
                    self._detectors[detector].activate()
                elif mode == 'deactivate':
                    self._detectors[detector].deactivate()
                else:
                    raise RuntimeError("Detector activation reached impossible state.")

    # # Traverse the detectors and make sure they're all stopped.
    # def _shutdown_detectors(self, detectors):
    #     if isinstance(detectors, list):
    #         for i in range(len(detectors)):
    #             # Call nested lists iteratively.
    #             if isinstance(detectors[i], list) or isinstance(detectors[i], dict):
    #                 self._shutdown_detectors(detectors[i])
    #             # If it's a Detector, it has shutdown, call it.
    #             elif isinstance(detectors[i], Detector):
    #                 detectors[i].shutdown()
    #     elif isinstance(detectors, dict):
    #         for item in detectors:
    #             # Call nested lists and dicts iteratively.
    #             if isinstance(detectors[item], list) or isinstance(detectors[item], dict):
    #                 self._shutdown_detectors(detectors[item])
    #             # If it's a Detector, it has shutdown, call it.
    #             elif isinstance(detectors[item], Detector):
    #                 detectors[item].shutdown()

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

    # Apply specific config options to the detectors.
    def _setup_detectors(self):
        # For each detector we use, apply its properties.
        self._logger.debug("Detectors: {}".format(self._detectors.keys()))
        for dc in self._settings['detectors']['settings'].keys():
            self._logger.debug("Configuring detector {}".format(dc))
            self._logger.debug("Settings: {}".format(self._settings['detectors']['settings'][dc]))
            for item in self._settings['detectors']['settings'][dc]:
                self._logger.debug(
                    "Setting property {} to {}".format(item, self._settings['detectors']['settings'][dc][item]))
                setattr(self._detectors[dc], item, self._settings['detectors']['settings'][dc][item])

