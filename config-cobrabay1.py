config = {
    # Define global settings.
    'global': {
        'units': 'imperial', # Defaults to 'metric' if set to anything other than 'imperial'.
        'system_name': 'CobraBay1', # ID of the system. Will be used for MQTT client ID, as well as name in MQTT Topics.
        'homeassistant': False,  # Integrate with Home Assistant?
        # 'syslog':
        #      {'host': 'tachyon.jumpbeacon.net',
        #       'facility': 'local7',
        #       'protocol': 'udp'}
        },
    'network': {
        'enable': True,  # If False, will run in a standalone, non-networked mode. Not Yet Implemented!
        # MQTT settings are in secrets.py, so that they don't accidentally get sent to the get repo!
        # See 'secrets-example.py' for a how-to.
    },
    # Define detectors. Detectors
    'detectors': {
        'range': {  # Name of the detector
            'type': 'Range',  # Class of detector to use
            'offset': '1 m',  # SEt the Zero point for the sensor this distance away from the sensor
            'timing': '200 ms',  # How long to waiting between readings.
            'sensor': {
                'i2c_bus': 1,
                'i2c_address': 0x30,  # Target address of the sensor.
                'enable_board': 0,
                'enable_pin': 25,
                'distance_mode': 'medium',  # Distance mode, can be 'short', 'medium', or 'long'
                'timing_budget': 50,  # Inter-measurement period, in milliseconds.
            }
        },
    },
    'bay': {  # Bay definition. ONLY ONE IS SUPPORTED NOW!
        'active': True,  # Is the bay active?
        'name': 'bay1',  # Name to use for the bay in MQTT. Will be made all lower-case.
        'park_time': "2 min",  # How long until a stationary vehicle is counted as parked.
        # How to range-find the vehicle
        'range': {
            'dist_max': "276 in", # Maximum range to report at
            'dist_stop': "10 in", # Distance from the range sensor where the vehicle should stop.
            'sensor': 'range-sensor' # Assigned sensor for range finding
            },
        # Lateral alignment zones to check if the vehicle is too far left or right.
        # Will be sorted by intercept range on start-up.
        # If there aren't lateral sensors, this key still needs to exist, but it can be empty.
        'lateral': [
            # { 'intercept_range': "100 in", # Distance at which an approaching vehicle should trigger this sensor.
            #    'dist_ideal': "10 in", # Ideal lateral distance of the vehicle from this sensor.
            #    'ok_spread': "1 in", # Within this distance of the ideal, still report it as good.
            #    'warn_spread': "3 in", # More than this distance off the ideal will throw a warning.
            #    'red_spread': "5 in", # More than this distance off the ideal will be critical
            #    'sensor': 'lat_front', # Assigned sensor
            #    'side': 'L' # Side of the bay the sensor is mounted on, 'L' or 'R'. This is relative to the range sensor.
            # },
            # { 'intercept_range': "50 in", # Distance at which an approaching vehicle should trigger this sensor.
            #   'dist_ideal': "10 in", # Ideal lateral distance of the vehicle from this sensor.
            #   'ok_spread': "1 in", # Within this distance of the ideal, still report it as good.
            #   'warn_spread': "3 in", # More than this distance off the ideal will throw a warning.
            #   'red_spread': "5 in", # More than this distance off the ideal will be critical
            #   'sensor': 'lat_rear', # Assigned sensor
            #   'side': 'L' # Side of the bay the sensor is mounted on, 'L' or 'R'. This is relative to the range sensor.
            #   }
            ]
        }
    }
