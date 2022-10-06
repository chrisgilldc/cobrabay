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
    'display': {
        'matrix': {
            'width': 64, # Columns on the matrix
            'height': 32, # Rows on the matrix
            'gpio_slowdown': 4  # How much to slow down the matrix to prevent flicker. 4 works for a Pi4.
        },
        'mqtt_image': True,  # Should we sent updates to the MQTT Display target for a bay?
        'mqtt_update_interval': "5 s" # How often should a new image be spent. Keeps from spamming the server.
    },

    # Define detectors. Detectors
    'detectors': {
        'range': {  # Name of the detector
            'type': 'Range',  # Class of detector to use
            'sensor': {
                'i2c_bus': 1,
                'i2c_address': 0x30,  # Target address of the sensor.
                'enable_board': 0, # Use '0' to indicate the Pi itself, otherwise the I2C address of the AW9523 board.
                'enable_pin': 25,
                'timing': '200 ms',  # How long to waiting between readings.
            }
        },
        'lateral-front': {
            'type': 'Lateral',
            'sensor': {
                'i2c_bus': 1,
                'i2c_address': 0x33,
                'enable_board': 0x58,
                'enable_pin': 3,
                'distance_mode': 'medium',
                'timing': '200 ms'
            }
        },
        # 'lateral-middle': {
        #     'type': 'Lateral',
        #     'sensor': {
        #         'i2c_bus': 1,
        #         'i2c_address': 0x32,
        #         'enable_board': 0x58,
        #         'enable_pin': 2,
        #         'distance_mode': 'medium',
        #         'timing': '200 ms'
        #     }
        # },
        # 'lateral-rear': {
        #     'type': 'Lateral',
        #     'offset': '1 m',
        #     'timing': '200 ms',
        #     'sensor': {
        #         'i2c_bus': 1,
        #         'i2c_address': 0x31,
        #         'enable_board': 0x58,
        #         'enable_pin': 2,
        #         'distance_mode': 'medium',
        #         'timing_budget': 50
        #     }
        # }
    },
    'bay': {  # Bay definition. ONLY ONE IS SUPPORTED NOW!
        'active': True,  # Is the bay active?
        'id': 'bay1',  # Name to use for the bay in MQTT. Will be made all lower-case.
        'park_time': "2 min",  # How long until a stationary vehicle is counted as parked.
        # How to range-find the vehicle
        'range': {
            'offset': "42 in", # Ideal distance for the range sensor where the vehicle should stop.
            'bay_depth': "276 in", # Total depth of the garage. This should measure from where the sensor is mounted,
                                    # (presumably the back wall), not the stopping point.
            # Optionally, can set these parameters for what percentage of the distance between offset and bay_depth
            # will be considered 'warning' and what will be condiered 'critical'. Right now this is only used to
            # color text on the display. If not specified, will default out as shown.
            # 'pct_warn': 15,
            # 'pct_crit': 10,
            'detector': 'range' # Assigned detector for range finding
            },
        # Lateral alignment zones to check if the vehicle is too far left or right.
        # Will be sorted by intercept range on start-up.
        # If there aren't lateral sensors, this key still needs to exist, but it can be empty.
        'lateral': {
            # Settings for all the lateral zones. Can be individually overridden if desired.
            'defaults': {
                'offset': "24 in",  # Ideal distance of the vehicle from the sensor when correctly aligned.
                'spread_ok': "1 in",  # Allowable deviation to be considered "Okay"
                'spread_warn': "3 in ",  # Allowable devication to be considered a "Warning"
                'spread_crit': "5 in",  # Deviation beyond which alignment is considered "Critical"
                'side': "R" # Side of the bay the lateral sensors are on.
                # This lets the system know the direction positive and negative readings go.
            # Assigned lateral detectors. This is a an *ordered* list, from nearest to furthers from the range sensor.
            # IE: the lateral sensor furthest from the garage door should come first.
            # Each detector is a dict that *must* define a detector from the Detector section, and *may* include any
            # of the same config options from lateral defaults to override those defaults. This can be used to tune
            # sensors if they behave differently, or aren't all mounted on the same surface, etc.
            },
            'detectors': [
                { 'detector': 'lateral-front' },
                # { 'detector': 'lateral-middle' }
                # { 'detector': 'lateral-rear' }
                ]
            }
        }
    }
