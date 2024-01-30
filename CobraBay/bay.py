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
from CobraBay.datatypes import Intercept, Vector

# FIXME: Test undock behavior, fix wonkiness.

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
                 longitudinal,
                 lateral,
                 system_detectors,
                 cbcore,
                 timeouts,
                 triggers={},
                 log_level="WARNING"):
        """
        :param id: ID for the bay. Cannot have spaces.
        :type id: str
        :param name: Long "friendly" name for the Bay, used in MQTT messages
        :type name: str
        :param depth: Absolute distance of the bay, from the range sensor to the end. Must be a linear Quantity.
        :type depth: Quantity(Distance)
        :param system_detectors: Dictionary of detector objects available on the system.
        :type system_detectors: dict
        :param longitudinal: Detectors which are arranged as longitudinal.
        :type longitudinal: dict
        :param lateral: Detectors which are arranged as lateral.
        :type lateral: dict
        :param cbcore: Object reference to the CobraBay core.
        :type cbcore: object
        :param timeouts: Dict with timeouts for 'dock','undock' and 'postroll' times.
        :type time_dock: dict
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
        self.depth_abs = depth
        self._timeouts = timeouts
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
        self._occupancy_score = None
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

        # Set the occupancy score. This is set statically so it doesn't change if/when sensors die.
        self._occupancy_score = self._calc_occupancy_score
        self._logger.info("Calculated occupancy score of '{}'".format(self._occupancy_score))

        # Activate detectors.
        # self._logger.info("Activating detectors...")
        # self._detector_state(SENSTATE_RANGING)
        # self._logger.info("Detectors activated.")

        # Motion timer for the current motion.
        self._current_motion = {
            'mark': time.monotonic() + 5
        }

        # Set our initial state.
        # self._scan_detectors()

        self._logger.info("Bay '{}' initialization complete.".format(self.id))

        self.state = BAYSTATE_READY

    ## Public Methods

    # Abort gets called when we want to cancel a docking.
    def abort(self):
        self.state = "ready"

    def check_timer(self):
        self._logger.debug("Evaluating for timer expiration.")
        # Update the dock timer.
        if self._detectors[self._selected_range].motion:
            # If motion is detected, update the time mark to the current time.
            self._logger.debug("Motion found, resetting dock timer.")
            self._current_motion['mark'] = time.monotonic()
        else:
            # Report the timer every 15s, to the info log level.
            time_elapsed = Quantity(time.monotonic() - self._current_motion['mark'], 's')
            if floor(time_elapsed.magnitude) % 15 == 0:
                self._logger.debug("Motion timer at {} seconds vs allowed {}s".
                                  format(floor(time_elapsed.magnitude), self._active_timeout))
            # No motion, check for completion
            if time_elapsed >= self._active_timeout:
                self._logger.info("Dock timer has expired, returning to ready")
                # Set self back to ready.
                self.state = 'ready'

        # Method to get info to pass to the Network module and register.

    @property
    def depth_abs(self):
        """
        Absolute distance from the range sensor to the end of the bay.

        :return: float
        """
        return self._depth_abs

    @depth_abs.setter
    def depth_abs(self, the_input):
        """
        Set the absolute depth.

        :param the_input:
        :return:
        """
        self._depth_abs = Quantity(the_input).to('cm')

    @property
    def depth(self):
        return self.depth_abs - self._detectors[self._selected_range].offset

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

    def check_triggers(self):
        for trigger_id in self._triggers:
            if self._triggers[trigger_id].triggered:
                self._logger.debug("Trigger '{}' is active.".format(trigger_id))
                self._logger.debug("Trigger has command stack - {}".format(self._triggers[trigger_id].cmd_stack))
                while self._triggers[trigger_id].cmd_stack:
                    # Pop the command from the object.
                    cmd = self._triggers[trigger_id].cmd_stack.pop(0)
                    self._logger.debug("Next command on stack. '{}' ({})".format(cmd, type(cmd)))
                    # Bay commands will trigger a motion or an abort.
                    # For nomenclature reasons, change the imperative form to the descriptive
                    if cmd.lower() == BAYCMD_DOCK:
                        self._logger.debug("Setting bay state to 'DOCKING'")
                        self.state = BAYSTATE_DOCKING
                        break
                    elif cmd.lower() == BAYCMD_UNDOCK:
                        self._logger.debug("Setting bay state to 'UNDOCKING'")
                        self.state = BAYSTATE_UNDOCKING
                        break
                    elif cmd.lower() == BAYCMD_ABORT:
                        self._logger.debug("Aborting bay motions.")
                        self.abort()
                    elif cmd.lower() == BAYSTATE_VERIFY:
                        self._logger.debug("Scanning sensors, calculating occupancy and sending to MQTT broker.")
                        self.state = BAYSTATE_VERIFY
                    else:
                        self._logger.debug("'{}' has no associated action as a bay command.".format(cmd))

    # Method to be called when CobraBay it shutting down.
    def shutdown(self):
        self._logger.critical("Beginning shutdown...")
        self._logger.critical("Shutting off detectors...")
        self._detector_state('disabled')
        self._logger.critical("Shutdown complete. Exiting.")

    ## Public Properties

    @property
    def active(self):
        """
        Activeness state of the bay. IE: Is it doing something? This is a useful shorthand
        :return: bool
        """
        if self._state in (BAYSTATE_DOCKING, BAYSTATE_UNDOCKING, BAYSTATE_VERIFY, BAYSTATE_POSTROLL):
            return True
        else:
            return False

    @property
    def occupied(self):
        """
        Occupancy state of the bay, determined based on what the sensors can hit.
        If positively occupied or not, returns that, otherwise 'unknown'.

        :returns: bay occupancy state
        :rtype: bool
        """
        self._logger.debug("Checking for occupancy.")
        # Status variable for occupancy. Start at unknown.
        occ = 'unknown'
        # Range detector is required to determine occupancy. If it's not ranging, return immediately.
        # Rely on other methods to have enabled sensors appropriately.
        if self._detectors[self._selected_range].state != SENSTATE_RANGING:
            self._logger.debug("Selected longitudinal sensor not ranging. Occupancy 'unknown'")
            occ = 'unknown'

        # Only hit the range quality once.
        range_quality = self._detectors[self._selected_range].quality
        if range_quality in (DETECTOR_QUALITY_NOOBJ, DETECTOR_QUALITY_DOOROPEN, DETECTOR_QUALITY_BEYOND):
            # Cases where there's no vehicle longitudinally means we jump straight to unoccupied.
            self._logger.debug("Longitudinal quality is '{}', not occupied.".format(range_quality))
            occ = "false"
        elif range_quality in (DETECTOR_QUALITY_EMERG, DETECTOR_QUALITY_BACKUP, DETECTOR_QUALITY_PARK,
                               DETECTOR_QUALITY_FINAL, DETECTOR_QUALITY_BASE, DETECTOR_QUALITY_OK):
            self._logger.debug("Matched longitudinal quality: {}".format(range_quality))
            # If the detector is giving us any of the 'close enough' qualities, there's something being found that
            # could be a vehicle. Check the lateral sensors to be sure that's what it is, rather than somebody blocking
            # the sensors or whatnot
            occ_score = 1
            for intercept in self.lateral_sorted:
                self._logger.debug("Checking quality for lateral detector '{}'.".format(intercept))
                if self._detectors[intercept.lateral].quality in (DETECTOR_QUALITY_OK, DETECTOR_QUALITY_WARN,
                                                                  DETECTOR_QUALITY_CRIT):
                    # No matter how badly parked the vehicle is, it's still *there*
                    occ_score += 1
            self._logger.debug("Achieved lateral score {} of {}".format(occ_score, self._occupancy_score))
            if occ_score >= self._occupancy_score:
                # All sensors have found something more or less in the right place, so yes, we're occupied!
                occ = 'true'
            else:
                occ = 'false'
        else:
            self._logger.warning(
                "Occupancy cannot be calculated, longitudinal sensor had quality '{}'".format(range_quality))
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
        self._logger.debug("Adjusted depth: {}".format(self.depth))
        if isinstance(self.range.value, Quantity):
            range_pct = self.range.value.to('cm') / self.depth.to('cm')
            # Singe this is dimensionless, just take the value and make it a Python scalar.
            range_pct = range_pct.magnitude
            return range_pct
        else:
            return 0


    @property
    def motion_timer(self):
        '''
        Reports time left on the current motion in M:S format. If no active motion, returns 'Inactive'.

        :return: str
        '''
        if self._active_timeout is not None:
            remaining_time = self._active_timeout - Quantity(time.monotonic() - self._current_motion['mark'], 's')
            # This catches the case were we're reporting a negative value to Home Assistant, which it reports in strange
            # ways. Instead, just clamp it to zero. This is *likely* due to not checking often enough, but this fix is
            # good enough for now.
            if remaining_time < 0:
                return Quantity("0s")
            else:
                return remaining_time
        else:
            # Return 0s if no active motion. This is because HA doesn't like it if we switch to a string representation.
            return Quantity("0s")

    @property
    def name(self):
        return self._name

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, input):
        self._id = input.replace(" ","_").lower()

    @name.setter
    def name(self, name):
        self._name = name

    @property
    def detectors(self):
        return self._detectors

    @property
    def state(self):
        """
        Operating state of the bay.
        See const.py 'BAYSTATE_*' for valid values.

        :returns Bay state
        :rtype: String
        """
        return self._state

    @state.setter
    def state(self, m_input):
        """
        Change the operating state of the bay.

        :param m_input:
        :return: None
        """
        # Trap invalid bay states.
        self._logger.debug("input: {}, {} {}".format(m_input, BAYSTATE_VERIFY, BAYSTATE_VERIFY == m_input))
        if m_input not in (BAYSTATE_READY, BAYSTATE_NOTREADY, BAYSTATE_DOCKING, BAYSTATE_UNDOCKING, BAYSTATE_VERIFY,
                           GEN_UNAVAILABLE):
            raise ValueError("{} is not a valid bay state.".format(m_input))
        self._logger.debug("Old state: {}, new state: {}".format(self._state, m_input))
        if m_input == self._state:
            self._logger.debug("Requested state {} is also current state. No action.".format(m_input))
            return
        # When requested to enter a motion state, DOCKING or UNDOCKING.
        if m_input in SYSSTATE_MOTION and self.state not in SYSSTATE_MOTION:
            self._logger.info("Entering state: {} (Previously '{}')".format(m_input, self.state))
            self._current_motion['mark'] = monotonic()
            self._logger.info("Start time: {}".format(self._current_motion['mark']))
            self._logger.info("Setting all detectors to ranging.")
            self._detector_state(SENSTATE_RANGING)
        # When requesting to leave a motion state.
        elif m_input not in SYSSTATE_MOTION and self.state in SYSSTATE_MOTION:
            self._logger.info("Entering state: {} (Previously '{}')".format(m_input, self.state))
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
        # When performing a verify, always report no motion, since we're not collecting enough data, any
        # values will be noise.
        if self.state == BAYSTATE_VERIFY:
            return Vector(speed=Quantity('0kph'), direction='still')
        else:
            return self._detectors[self._selected_range].vector


    ## Private Methods

    # Traverse the detectors dict, activate everything that needs activating.
    def _detector_state(self, target_status):
        """
        Set all of the Bay's detectors at once.
        :param target_status: Status to set the detectors to.
        :return: None
        """
        self._logger.info("{} - Starting detector state set.".format(time.monotonic()))
        if target_status in (SENSTATE_DISABLED, SENSTATE_ENABLED, SENSTATE_RANGING):
            # self._logger.debug("Traversing detectors to set status to '{}'".format(target_status))
            # Traverse the dict looking for detectors that need activation.
            for detector in self._detectors:
                self._logger.info("{} - Setting detector {}".format(time.monotonic(), detector))
                self._logger.debug("Changing detector {}".format(detector))
                self._detectors[detector].status = target_status
                self._logger.info("{} - Set complete.".format(time.monotonic()))
        else:
            raise ValueError("'{}' not a valid state for detectors.".format(target_status))

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

    def _setup_detectors(self, longitudinal, lateral, system_detectors):
        ''' Configure detectors for this bay.'''
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
                        self._logger.debug("Applying bay depth '{}' to longitudinal detector.".format(self.depth_abs))
                        setattr(configured_detectors[detector_id], "bay_depth", self.depth_abs)
                    elif direction is lateral:

                        setattr(configured_detectors[detector_id], "attached_bay", self )
                        self._logger.debug("Attaching bay object reference '{}' to lateral detector.".
                                           format(configured_detectors[detector_id].attached_bay))
        self._logger.debug("Configured detectors: {}".format(configured_detectors))
        return configured_detectors

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

    ## Private Properties
    @property
    def _active_timeout(self):
        ''' Utility method to determine which timeout to use.'''
        if self.state == BAYSTATE_DOCKING:
            return self._timeouts['dock']
        elif self.state == BAYSTATE_UNDOCKING:
            return self._timeouts['undock']
        elif self._state == BAYSTATE_POSTROLL:
            return self._timeouts['post-roll']
        else:
            return None

    @property
    def _calc_occupancy_score(self):
        max_score = len(self.lateral_sorted)
        score = floor(max_score * (2/3)) + 1  # Add 1 for the longitudinal sensor.
        return score

    ## Old stuff....

    # Trigger handling
    def register_trigger(self, trigger_obj):
        self._logger.debug("Registering trigger ID '{}'".format(trigger_obj.id))
        self._triggers[trigger_obj.id] = trigger_obj

    def deregister_trigger(self, trigger_id):
        self._logger.debug("Deregistering Trigger ID '{}'".format(trigger_id))
        del self._triggers[trigger_id]



