####
# Cobra Bay - The Bay!
####
import time
from pint import UnitRegistry, Quantity
from time import monotonic
from math import floor
# from .detectors import CB_VL53L1X
import logging
from functools import wraps
from operator import attrgetter
from CobraBay.const import *
from CobraBay.datatypes import Intercept

def log_changes(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        print("Log changes wrapper received:\n\tArgs - {}\n\tKwargs - {}".format(args, kwargs))
        # Call the function.
        retval = func(self, *args, **kwargs)
        if self._logger.level <= 20:
            if func.__name__ in self._previous:
                if self._previous[func.__name__] != retval:
                    self._logger.info("{} changed from '{}' ({}) to '{}' ({})".
                        format(func.__name__,
                               self._previous[func.__name__],
                               type(self._previous[func.__name__]),
                               retval,
                               type(retval)))
            else:
                self._logger.info("Initial value of '{}' set to '{}' ({})".format(func.__name__, retval, type(retval)))
        self._previous[func.__name__] = retval
        return retval
    return wrapper

class CBBay:
    def __init__(self, id,
                 name,
                 depth,
                 motion_timeout,
                 longitudinal,
                 lateral,
                 system_detectors,
                 cbcore,
                 triggers={},
                 log_level="WARNING"):
        """
        :param id: ID for the bay. Cannot have spaces.
        :type id: str
        :param name: Long "friendly" name for the Bay, used in MQTT messages
        :type name: str
        :param depth: Absolute distance of the bay, from the range sensor to the end. Must be a linear Quantity.
        :type depth: Quantity(Distance)
        :param motion_timeout: During a movement, how long the bay must be still to be considered complete.
        :type motion_timeout: Quantity(Time)
        :param system_detectors: Dictionary of detector objects available on the system.
        :type system_detectors: dict
        :param longitudinal: Detectors which are arranged as longitudinal.
        :type longitudinal: dict
        :param lateral: Detectors which are arranged as lateral.
        :type lateral: dict
        :param cbcore: Object reference to the CobraBay core.
        :type cbcore: object
        :param triggers: Dictionary of Triggers for this bay. Can be modified later with register_trigger.
        :type triggers: dict
        :param log_level: Log level for the bay, must be a Logging level.
        :type log_level: str
        """
        # Must set ID before we can create the logger.
        self._motion_timeout = None
        self.id = id

        self._logger = logging.getLogger("CobraBay").getChild(self.id)
        self._logger.setLevel(log_level.upper())
        self._logger.info("Initializing bay: {}".format(id))
        self._logger.debug("Bay received system detectors: {}".format(system_detectors))

        # Save the remaining parameters.
        self._name = name
        self._depth = depth
        self.motion_timeout = motion_timeout
        self._detectors = None
        self._triggers = triggers
        # Save the reference to the Core.
        self._cbcore = cbcore

        # Select a longitudinal detector to be the main range detector.
        # Only one supported currently.
        self._selected_range = self._select_range(longitudinal)
        self._logger.debug("Longitudinal detector '{}' selected for ranging".format(self._selected_range))
        # Sort the lateral detectors by intercept.
        self.lateral_sorted = self._sort_lateral(lateral['detectors'])

        # Initialize variables.
        self._position = {}
        self._quality = {}
        self._trigger_registry = {}
        self._previous_scan_ts = 0
        self._state = None
        self._occupancy = None
        self._previous = {}

        # Create a unit registry.
        self._ureg = UnitRegistry

        # Apply our configurations to the detectors.
        self._detectors = self._setup_detectors(longitudinal=longitudinal, lateral=lateral, system_detectors=system_detectors)

        # Report configured detectors
        self._logger.info("Detectors configured:")
        for detector in self._detectors.keys():
            try:
                addr = hex(self._detectors[detector].sensor_interface.addr)
            except TypeError:
                addr = self._detectors[detector].sensor_interface.addr
            self._logger.info("\t\t{} - {}".format(detector,addr))

        # Activate detectors.
        self._logger.info("Activating detectors...")
        self._detector_state(SENSTATE_RANGING)
        self._logger.info("Detectors activated.")

        # Motion timer for the current motion.
        self._current_motion = {
            'mark': time.monotonic() + 5
        }

        # Set our initial state.
        # self._scan_detectors()

        self._logger.info("Bay '{}' initialization complete.".format(self.id))

        self.state = "ready"

    # Abort gets called when we want to cancel a docking.
    def abort(self):
        self.state = "ready"

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    @property
    def detectors(self):
        return self._detectors

    def check_timer(self):
        self._logger.debug("Evaluating for timer expiration.")
        # Update the dock timer.
        if self._detectors[self._selected_range].motion:
            # If motion is detected, update the time mark to the current time.
            self._logger.info("Motion found, resetting dock timer.")
            self._current_motion['mark'] = time.monotonic()
        else:
            # Report the timer every 15s, to the info log level.
            time_elapsed = Quantity(time.monotonic() - self._current_motion['mark'], 's')
            if floor(time_elapsed.magnitude) % 15 == 0:
                self._logger.info("Motion timer at {} vs allowed {}".format(time_elapsed, self.motion_timeout))
            # No motion, check for completion
            if time_elapsed >= self.motion_timeout:
                self._logger.info("Dock timer has expired, returning to ready")
                # Set self back to ready.
                self.state = 'ready'

    # Method to get info to pass to the Network module and register.
    @property
    def discovery_reg_info(self):
        # For discovery, the detector hierarchy doesn't matter, so we can flatten it.
        return_dict = {
            'id': self.id,
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
    def id(self):
        return self._id

    @id.setter
    def id(self, input):
        self._id = input.replace(" ","_").lower()

    @property
    def motion_timeout(self):
        return self._motion_timeout

    @motion_timeout.setter
    def motion_timeout(self, mto_input):
        if isinstance(mto_input, Quantity):
            if not mto_input.check('[time]'):
                raise ValueError("Motion timeout must have time dimensionality.")
            else:
                self._motion_timeout = mto_input
        else:
            raise TypeError("Motion timeout must be a Quantity.")

    @property
    def motion_timer(self):
        '''
        Reports time left on the current motion in M:S format. If no active motion, returns 'idle'.

        :return:
        '''
        if self.state not in ('docking', 'undocking'):
            return 'idle'
        else:
            return self.motion_timeout - Quantity(time.monotonic() - self._current_motion['mark'], 's')

    @property
    def _occupancy_score(self):
        max_score = len(self.lateral_sorted)
        score = floor(max_score * (2/3))
        # Never let score be less than one detector, because that makes no sense.
        if score < 1:
            score = 1
        return score

    # Bay properties
    @property
    def occupied(self):
        """
        Occupancy state of the bay, determined based on what the sensors can hit.
        If positively occupied or not, returns that, otherwise 'unknown'.

        :returns: bay occupancy state
        :rtype: bool
        """
        self._logger.debug("Checking for occupancy.")
        occ = 'unknown'
        # Range detector is required to determine occupancy. If it's not ranging, return immediately.
        if self._detectors[self._selected_range].state != SENSTATE_RANGING:
            occ = 'unknown'
        # Only hit the range quality once.
        range_quality = self._detectors[self._selected_range].quality
        if range_quality in (DETECTOR_QUALITY_NOOBJ, DETECTOR_QUALITY_DOOROPEN):
            # If the detector can hit the garage door, or the door is open, then clearly nothing is in the way, so
            # the bay is vacant.
            self._logger.debug("Longitudinal quality is {}, not occupied.".format(range_quality))
            occ = "false"
        elif range_quality in (DETECTOR_QUALITY_EMERG, DETECTOR_QUALITY_BACKUP, DETECTOR_QUALITY_PARK,
                               DETECTOR_QUALITY_FINAL, DETECTOR_QUALITY_BASE, DETECTOR_QUALITY_OK):
            self._logger.debug("Matched range quality: {}".format(range_quality))
            # If the detector is giving us any of the 'close enough' qualities, there's something being found that
            # could be a vehicle. Check the lateral sensors to be sure that's what it is, rather than somebody blocking
            # the sensors or whatnot
            lat_score = 0
            for intercept in self.lateral_sorted:
                self._logger.debug("Checking quality for lateral detector '{}'.".format(intercept))
                if self._detectors[intercept.lateral].quality in (DETECTOR_QUALITY_OK, DETECTOR_QUALITY_WARN,
                                                                  DETECTOR_QUALITY_CRIT):
                    # No matter how badly parked the vehicle is, it's still *there*
                    lat_score += 1
            self._logger.debug("Achieved lateral score {} of {}".format(lat_score, self._occupancy_score))
            if lat_score >= self._occupancy_score:
                # All sensors have found something more or less in the right place, so yes, we're occupied!
                occ = 'true'
            else:
                occ = 'false'
        else:
            occ = 'error'
        if occ != self._occupancy:
            self._logger.info("Occupancy has changed from '{}' to '{}'".format(self._occupancy, occ))
        self._occupancy = occ
        return occ

    @property
    def range(self):
        '''
        The selected range object for this bay.

        :return: detectors.Range
        '''
        return self._detectors[self._selected_range]

    @property
    def range_pct(self):
        '''
        Percentage of distance covered from the garage door to the stop point.
        :return: float
        '''
        # If it's not a Quantity, just return zero.
        self._logger.debug("Calculating range percentage")
        self._logger.debug("Range value: {} ({})".format(self.range.value,type(self.range.value)))
        adjusted_depth = self._depth - self._detectors[self._selected_range].offset
        self._logger.debug("Adjusted depth: {}".format(adjusted_depth))
        if isinstance(self.range.value, Quantity):
            range_pct = self.range.value.to('cm') / adjusted_depth.to('cm')
            # Singe this is dimensionless, just take the value and make it a Python scalar.
            range_pct = range_pct.magnitude
            return range_pct
        else:
            return 0

    # Method to be called when CobraBay it shutting down.
    def shutdown(self):
        self._logger.critical("Beginning shutdown...")
        self._logger.critical("Shutting off detectors...")
        self._detector_state('disabled')
        self._logger.critical("Shutdown complete. Exiting.")

    @property
    def state(self):
        """
        Operating state of the bay.
        Can be one of 'docking', 'undocking', 'verify', 'ready', or 'unavailable'.

        :returns Bay state
        :rtype: String
        """
        return self._state

    @state.setter
    def state(self, m_input):
        """

        :param m_input:
        :return:
        """
        self._logger.debug("State change requested to {} from {}".format(m_input, self._state))
        # Trap invalid bay states.
        if m_input not in (BAYSTATE_READY, BAYSTATE_DOCKING, BAYSTATE_UNDOCKING, BAYSTATE_NOTREADY, GEN_UNAVAILABLE):
            raise ValueError("{} is not a valid bay state.".format(m_input))
        self._logger.debug("Old state: {}, new state: {}".format(self._state, m_input))
        if m_input == self._state:
            self._logger.debug("Requested state {} is also current state. No action.".format(m_input))
            return
        if m_input in SYSSTATE_MOTION and self._state not in SYSSTATE_MOTION:
            self._logger.info("Entering state: {}".format(m_input))
            self._logger.info("Start time: {}".format(self._current_motion['mark']))
            self._logger.info("Setting all detectors to ranging.")
            self._detector_state(SENSTATE_RANGING)
            self._current_motion['mark'] = monotonic()
        if m_input not in SYSSTATE_MOTION and self._state in SYSSTATE_MOTION:
            self._logger.info("Entering state: {}".format(m_input))
            # Reset some variables.
            # Make the mark none to be sure there's not a stale value in here.
            self._current_motion['mark'] = None
        # Now store the state.
        self._state = m_input

    @property
    def vector(self):
        """
        The vector from the bay's selected range detector.

        :return:
        :rtype: namedtuple
        """
        return self._detectors[self._selected_range].vector

    def _detector_status(self):
        return_list = []
        # Positions for all the detectors.
        for detector in self._detectors.keys():
            # Template detector message, to get filled in.
            detector_message = {'topic_type': 'bay', 'topic': 'bay_detector',
                                'message': {
                                    'status': self._detectors[detector].status
                                },
                                'repeat': False,
                                'topic_mappings': {'id': self.id, 'detector_id': self._detectors[detector].id}
                                }

            # If the detector is actively ranging, add the values.
            self._logger.debug("Detector has status: {}".format(self._detectors[detector].status))
            if self._detectors[detector].status == SENSTATE_RANGING:
                detector_message['message']['adjusted_reading'] = self._detectors[detector].value
                detector_message['message']['raw_reading'] = self._detectors[detector].value_raw
                # While ranging, always send values to MQTT, even if they haven't changed.
                detector_message['repeat'] = True
            # Add the detector to the return list.
            self._logger.info("Adding detector message status: {}".format(detector_message))
            return_list.append(detector_message)
        return return_list

    def _select_range(self, longitudinal):
        """
        Select a primary longitudinal sensor to use for range from among those presented.

        :param longitudinal:
        :return: str
        """
        self._logger.debug("Detectors considered for selection: {}".format(longitudinal['detectors']))
        if len(longitudinal['detectors']) == 0:
            raise ValueError("No longitudinal detectors defined. Cannot select a range!")
        elif len(longitudinal['detectors']) > 1:
            raise ValueError("Cannot select a range! More than one longitudinal detector not currently supported.")
        else:
            return longitudinal['detectors'][0]['detector']

    # Calculate the ordering of the lateral sensors.
    def _sort_lateral(self, lateral_detectors):
        """
        Sort the lateral detectors by distance.

        :param lateral_detectors: List of lateral detector definition dicts.
        :type lateral_detectors: list
        :return:
        """

        self._logger.debug("Creating sorted intercepts from laterals: {}".format(lateral_detectors))
        lateral_sorted = []
        # Create named tuples and put it in the list.
        for item in lateral_detectors:
            # Make a named tuple out of the detector's config.
            this_detector = Intercept(item['detector'], item['intercept'])
            lateral_sorted.append(this_detector)
        lateral_sorted = sorted(lateral_sorted, key=attrgetter('intercept'))
        self._logger.debug("Lateral detectors sorted to order: {}".format(lateral_sorted))
        return lateral_sorted

    # Traverse the detectors dict, activate everything that needs activating.
    def _detector_state(self, target_status):
        if target_status in (SENSTATE_DISABLED, SENSTATE_ENABLED, SENSTATE_RANGING):
            self._logger.debug("Traversing detectors to set status to '{}'".format(target_status))
            # Traverse the dict looking for detectors that need activation.
            for detector in self._detectors:
                self._logger.debug("Changing detector {}".format(detector))
                self._detectors[detector].status = target_status
        else:
            raise ValueError("'{}' not a valid state for detectors.".format(target_status))

    # Configure system detectors for this bay.
    def _setup_detectors(self, longitudinal, lateral, system_detectors):
        # Output dictionary.
        configured_detectors = {}
        # Some debug output
        self._logger.debug("Available detectors on system: {}".format(system_detectors))
        self._logger.debug("Bay Longitudinal settings: {}".format(longitudinal))
        self._logger.debug("Bay Lateral settings: {}".format(lateral))

        for direction in ( longitudinal, lateral ):
            for detector_settings in direction['detectors']:
                # Merge in the defaults.
                for item in direction['defaults']:
                    if item not in detector_settings:
                        detector_settings[item] = direction['defaults'][item]
                detector_id = detector_settings['detector']
                del(detector_settings['detector'])
                try:
                    configured_detectors[detector_id] = system_detectors[detector_id]
                except KeyError:
                    self._logger.error("Bay references unconfigured detector '{}'".format(detector_id))
                else:
                    self._logger.info("Configuring detector '{}'".format(detector_id))
                    self._logger.debug("Settings: {}".format(detector_settings))
                    # Apply all the bay-specific settings to the detector. Usually these are defined in the
                    # detector-settings.
                    for item in detector_settings:
                        self._logger.info(
                            "Setting property {} to {}".format(item, detector_settings[item]))
                        setattr(configured_detectors[detector_id], item, detector_settings[item])
                    # Bay depth is a bay global. For range sensors, this also needs to get applied.
                    if direction is longitudinal:
                        self._logger.debug("Applying bay depth '{}' to longitudinal detector.".format(self._depth))
                        setattr(configured_detectors[detector_id], "bay_depth", self._depth)
                    elif direction is lateral:

                        setattr(configured_detectors[detector_id], "attached_bay", self )
                        self._logger.debug("Attaching bay object reference '{}' to lateral detector.".
                                           format(configured_detectors[detector_id].attached_bay))
        self._logger.debug("Configured detectors: {}".format(configured_detectors))
        return configured_detectors

    # Trigger handling
    def register_trigger(self, trigger_obj):
        self._logger.debug("Registering trigger ID '{}'".format(trigger_obj.id))
        self._triggers[trigger_obj.id] = trigger_obj

    def deregister_trigger(self, trigger_id):
        self._logger.debug("Deregistering Trigger ID '{}'".format(trigger_id))
        del self._triggers[trigger_id]

    def scan_triggers(self):
        self._logger.debug("Scanning triggers.")
        for trigger_id in self._triggers:
            self._logger.debug("Checking Trigger ID '{}'".format(trigger_id))
            if self._triggers[trigger_id].triggered:
                self._logger.debug("Trigger '{}' is active.".format(trigger_id))
                self._logger.debug("Trigger has command stack - {}".format(self._triggers[trigger_id].cmd_stack))
                while self._triggers[trigger_id].cmd_stack:
                    # Pop the command from the object.
                    cmd = self._triggers[trigger_id].cmd_stack.pop(0)
                    self._logger.debug("Next command on stack. '{}'".format(cmd))
                    # Bay commands will trigger a motion or an abort.
                    # For nomenclature reasons, change the imperative form to the descriptive
                    if cmd.upper() == 'DOCK':
                        self._logger.debug("Setting bay state to 'DOCKING'")
                        self.state = 'docking'
                        break
                    elif cmd.upper() == 'UNDOCK':
                        self._logger.debug("Setting bay state to 'UNDOCKING'")
                        self.state = 'undocking'
                        break
                    elif cmd.upper() == 'ABORT':
                        self._logger.debug("Aborting bay motions.")
                        self.abort()
                    else:
                        self._logger.debug("'{}' is not a valid bay command.".format(cmd))

