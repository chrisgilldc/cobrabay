####
# Cobra Bay - The Bay!
####
import time
from pint import UnitRegistry, Quantity
from time import monotonic
from .detectors import CB_VL53L1X
import logging
from pprint import pformat
from functools import wraps
import sys
from .exceptions import SensorValueException
import CobraBay

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


class CBBay:
    def __init__(self, bay_id,
                 bay_name,
                 bay_depth,
                 stop_point,
                 park_time,
                 output_unit,
                 detectors,
                 detector_settings,
                 selected_range,
                 lateral,
                 longitudinal,
                 intercepts,
                 log_level="WARNING", **kwargs):
        """
        :param bay_id: ID for the bay. Cannot have spaces.
        :type bay_id: str
        :param bay_name: Long "friendly" name for the Bay, used in MQTT messages
        :type bay_name: str
        :param bay_depth: Absolute distance of the bay, from the range sensor to the end. Must be a linear Quantity.
        :type bay_depth: Quantity
        :param stop_point: Distance from the sensor where the vehicle should stop
        :type stop_point: Quantity
        :param park_time: int
        :param output_unit: Unit to output measurements in. Should be a distance unit understood by Pint (ie: 'in', 'cm', etc)
        :type output_unit: str
        :param detectors: Dictionary of detector objects.
        :type detectors: dict
        :param detector_settings: Dictionary of detector configuration settings.
        :type detector_settings: dict
        :param selected_range: Of longitudinal sensors, which should be used as the default range sensor.
        :type selected_range: str
        :param longitudinal: Detectors which are arranged as longitudinal.
        :type longitudinal: list
        :param lateral: Detectors which are arranged as lateral.
        :type lateral: list
        :param intercepts: For lateral sensors, the raw distance from the end of the bay each lateral crosses the parking area.
        :type intercepts: list
        :param log_level: Log level for the bay, must be a Logging level.
        :type log_level: str
        """
        # Save parameters
        self._bay_id = bay_id
        self._bay_name = bay_name
        self._bay_depth = bay_depth
        self._stop_point = stop_point
        self._park_time = park_time
        self._output_unit = output_unit
        self._detectors = detectors
        self._detector_settings = detector_settings
        self._lateral = lateral
        self._longitudinal = longitudinal
        self._intercepts = intercepts
        self._selected_range = selected_range
        # Create a logger.
        self._logger = logging.getLogger("CobraBay").getChild(self.bay_id)
        self._logger.setLevel(log_level)
        self._logger.info("Initializing bay: {}".format(bay_id))
        self._logger.debug("Bay received detectors: {}".format(detectors))

        # Initialize variables.
        self._position = {}
        self._quality = {}
        self._trigger_registry = {}
        self._previous_scan_ts = 0
        self._state = None
        self._occupancy = None

        # Create a unit registry.
        self._ureg = UnitRegistry

        # Store the detector objects
        self._detectors = detectors
        # Apply our configurations to the detectors.
        self._setup_detectors()
        self._logger.info("Detectors configured:")
        for detector in self._detectors.keys():
            try:
                addr = hex(self._detectors[detector].sensor_interface.addr)
            except TypeError:
                addr = self._detectors[detector].sensor_interface.addr
            self._logger.info("\t\t{} - {}".format(detector,addr))

        # Activate detectors.
        self._detector_state('activate')

        # Dock timer.
        self._dock_timer = {
            'allowed': self._park_time,
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
            'lateral_order': self._lateral
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
        self._logger.debug("Lateral count requested. Lateral detectors: {}".format(self._lateral))
        return len(self._lateral)

    def check_timer(self):
        self._logger.debug("Evaluating for timer expiration.")
        # Update the dock timer.
        if self._detectors[self._selected_range].motion:
            # If motion is detected, update the time mark to the current time.
            self._logger.debug("Motion found, resetting dock timer.")
            self._dock_timer['mark'] = time.monotonic()
        else:
            self._logger.debug("No motion found, checking for dock timer expiry.")
            # No motion, check for completion
            if time.monotonic() - self._dock_timer['mark'] >= self._dock_timer['allowed']:
                self._logger.info("Dock timer has expired and no motion found. Returning to ready.")
                # Set self back to ready.
                self.state = 'Ready'

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
            try:
                position[detector_name] = self._detectors[detector_name].value
            except SensorValueException:
                # For now, pass. Need to add logic here to actually set the overall bay status.
                pass

            quality[detector_name] = self._detectors[detector_name].quality
            self._logger.debug("Read of detector {} returned value '{}' and quality '{}'".
                               format(self._detectors[detector_name].name, position[detector_name],
                                      quality[detector_name]))

        if filter_lateral:
            # Pull the raw range value once, use it to test all the intercepts.
            raw_range = self._detectors[self._selected_range].value_raw
            for lateral_name in self._lateral:
                # If intercept range hasn't been met yet, we wipe out any value, it's meaningless.
                # Have a bug where this is sometimes erroring out due to a None range value.
                # Trapping and logging for now.
                try:
                    if raw_range > self._intercepts[lateral_name]:
                        quality[lateral_name] = "Not Intercepted"
                        self._logger.debug("Sensor {} with intercept {}. Range {}, not intercepted.".
                                           format(lateral_name,
                                                  self._intercepts[lateral_name].to('cm'),
                                                  raw_range.to('cm')))
                except ValueError:
                    self._logger.debug("For lateral sensor {} cannot compare intercept {} to range {}".
                                       format(lateral_name,
                                              self._intercepts[lateral_name],
                                              raw_range))
        self._position = position
        self._quality = quality

    # Method to check occupancy.
    def _check_occupancy(self):
        # Do a new scan and *don't* filter out non-intercepted laterals. We need to
        self._scan_detectors(filter_lateral=False)
        self._logger.debug("Checking for occupancy.")
        self._logger.debug("Longitudinal is {}".format(self._quality[self._selected_range]))
        # First cut is the range.
        if self._quality[self._selected_range] in ('No object', 'Door open'):
            # If the detector can hit the garage door, or the door is open, then clearly nothing is in the way, so
            # the bay is vacant.
            self._logger.debug("Longitudinal quality is {}, not occupied.".
                               format(self._quality[self._selected_range]))
            return False
        if self._quality[self._selected_range] in (
                'Emergency!', 'Back up', 'Park', 'Final', 'Base'):
            # If the detector is giving us any of the 'close enough' qualities, there's something being found that
            # could be a vehicle. Check the lateral sensors to be sure that's what it is, rather than somebody blocking
            # the sensors or whatnot
            self._logger.debug("Longitudinal quality is {}, could be occupied.".
                               format(self._quality[self._selected_range]))
            lat_score = 0
            max_score = len(self._lateral)
            for detector in self._lateral:
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
        vector = self._detectors[self._selected_range].vector
        # If there's motion, change state.
        if vector['direction'] == 'forward':
            self.state = 'Docking'
        elif vector['direction'] == 'reverse':
            self.state = 'Undocking'
        elif self._detectors[self._selected_range].value == 'Weak':
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
            # Make the mark none to be sure there's not a stale value in here.
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
                              'message': self._detectors[self._selected_range].vector,
                              'repeat': True,
                              'topic_mappings': {'bay_id': self.bay_id}}]

        # Add detector values, if applicable.
        outbound_messages = outbound_messages + self._detector_status()

        if self._dock_timer['mark'] is None:
            message = 'Not running'
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

    def _detector_status(self):
        return_list = []
        # Positions for all the detectors.
        for detector in self._detectors.keys():
            # Template detector message, to get filled in.
            detector_message = {'topic_type': 'bay', 'topic': 'bay_position',
                                'message': {
                                    'status': self._detectors[detector].status
                                },
                                'repeat': False,
                                'topic_mappings': {'bay_id': self.bay_id, 'detector_id': self._detectors[detector].id}
                                }

            # If the detector is actively ranging, add the values.
            self._logger.debug("Detector has status: {}".format(self._detectors[detector].status))
            if self._detectors[detector].status == 'ranging':
                detector_message['message']['adjusted_reading'] = self._detectors[detector].value
                detector_message['message']['raw_reading'] = self._detectors[detector].value_raw
                # While ranging, always send values to MQTT, even if they haven't changed.
                detector_message['repeat'] = True
            # Add the detector to the return list.
            self._logger.info("Adding detector message status: {}".format(detector_message))
            return_list.append(detector_message)
        return return_list

    # Send collect data needed to send to the display. This is syntactically shorter than the MQTT messages.
    def display_data(self):
        self._logger.debug("Collecting bay data for display. Have quality: {}".format(self._quality))
        return_data = {'bay_id': self.bay_id, 'bay_state': self.state,
                       'range': self._position[self._selected_range],
                       'range_quality': self._quality[self._selected_range]}
        # Percentage of range covered. This is used to construct the strobe.
        # If it's not a Quantity, just return zero.
        if isinstance(return_data['range'], Quantity):
            return_data['range_pct'] = return_data['range'].to('cm') / self._adjusted_depth.to('cm')
            # Singe this is dimensionless, just take the value and make it a Python scalar.
            return_data['range_pct'] = return_data['range_pct'].magnitude
        else:
            return_data['range_pct'] = 0
        # List for lateral state.
        return_data['lateral'] = []
        self._logger.debug("Using lateral order: {}".format(self._lateral))
        # Assemble the lateral data with *closest first*.
        # This will result in the display putting things together top down.
        # Lateral ordering is determined by intercept range when bay is started up.
        if self._lateral is not None:
            for lateral_detector in self._lateral:
                detector_dict = {
                    'name': lateral_detector,
                    'quality': self._quality[lateral_detector],
                }

                if self._position[lateral_detector] is None:
                    detector_dict['side'] = 'None'
                elif self._detectors[lateral_detector].side == 'Not Intercepted':
                    detector_dict['side'] = "DND"
                else:
                    # This is a little confusing. The detector side is relative to the bay, ie: looking out from the range
                    # sensor. The display position for indicator is relative to the display, ie: when looking (at) the
                    # display. I arguably should have made it consistent, but not going to rewrite it now.

                    if self._detectors[lateral_detector].side == 'R':
                        # Sensor is mounted on the right side of the bay.
                        if self._position[lateral_detector] > 0:
                            # Vehicle is shifted to the left side of the bay
                            # Put the indicators on the right side of the display (bay-left)
                            detector_dict['side'] = 'R'
                        elif self._position[lateral_detector] < 0:
                            # Vehicle is shifted to the right side of the bay.
                            # Pub the indicators on the left side of the display (bay-right)
                            detector_dict['side'] = 'L'
                        else:
                            # It's exactly zero? What're the odd!?
                            detector_dict['side'] = 'DND'
                    elif self._detectors[lateral_detector].side == 'L':
                        # Sensor is mounted on the left side of the bay.
                        if self._position[lateral_detector] > 0:
                            # Vehicle is shifted to the right side of the bay.
                            # Put the indicators on the left side of the display (bay-right)
                            detector_dict['side'] = 'L'
                        elif self._position[lateral_detector] < 0:
                            # Vehicle is shifted to the left side of the bay.
                            # Put the indicators on the right side of the display (bay-left)
                            detector_dict['side'] = 'R'
                        else:
                            detector_dict['side'] = 'DND'

                return_data['lateral'].append(detector_dict)
                # Calculate the side for placement.

        else:
            self._logger.debug("Not assembling laterals, lateral order is None.")
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
        return self._bay_id

    @bay_id.setter
    def bay_id(self, input):
        self._bay_id = input

    @property
    def bay_name(self):
        return self._bay_name

    @bay_name.setter
    def bay_name(self, input):
        self._bay_name = input

    # Apply specific config options to the detectors.
    def _setup_detectors(self):
        # For each detector we use, apply its properties.
        self._logger.debug("Detectors: {}".format(self._detectors.keys()))
        for dc in self._detector_settings.keys():
            self._logger.debug("Configuring detector {}".format(dc))
            self._logger.debug("Settings: {}".format(self._detector_settings[dc]))
            # Apply all the bay-specific settings to the detector. Usually these are defined in the detector-settings.
            for item in self._detector_settings[dc]:
                self._logger.debug(
                    "Setting property {} to {}".format(item, self._detector_settings[dc][item]))
                setattr(self._detectors[dc], item, self._detector_settings[dc][item])
            # Bay depth is a bay global. For range sensors, this also needs to get applied.
            if isinstance(self._detectors[dc], CobraBay.detectors.Range):
                setattr(self._detectors[dc], "bay_depth", self._bay_depth)
