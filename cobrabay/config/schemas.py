"""
Cobra Bay Config Schemas
"""

from pathlib import Path
import importlib
import pint

SCHEMA_SENSOR_COMMON = {
    'name': {'type': 'string'},
    # 'error_margin': {'type': 'quantity', 'coerce': 'pint_cm', 'default': '2 cm'},
    'error_margin': {'type': 'string', 'default': '2 cm'},
    'always_range': {'type': 'boolean', 'default': False},
    'max_retries': {'type': 'integer', 'default': 3}
}

SCHEMA_SENSOR_VL53L1X = {**SCHEMA_SENSOR_COMMON,
    'hw_type': {'type': 'string', 'required': True, 'allowed': ['VL53L1X']},
    'i2c_bus': {'type': 'integer', 'default': 1},
    #TODO: Get this to validate correctly as none.
    # 'pin_scl': {'type': 'string', 'default': None},
    # 'pin_sda': {'type': 'string', 'default': None},
    'i2c_address': {'type': 'integer', 'required': True},
    'enable_board': {'type': 'integer', 'required': True},
    'enable_pin': {'type': 'integer', 'required': True},
    'distance_mode': {'type': 'string', 'allowed': ['long', 'short'], 'default': 'long'},
    #TODO: Fix type coersion.
    # Ideally this would get coerced to pint_ms, but this raises complications because of the subvalidation.
    'timing': {'type': 'string', 'default': '200ms'}
}

# Sub-schema for the TFMini Sensor
SCHEMA_SENSOR_TFMINI = {
    **SCHEMA_SENSOR_COMMON,
    'hw_type': {'type': 'string', 'required': True, 'allowed': ['TFMini']},
    'port': {'type': 'string', 'required': True},
    'baud': {'type': 'integer', 'default': 115200,
             'allowed': [9600, 14400, 19200, 56000, 115200, 460800, 921600]},
    'clustering': {'type': 'integer', 'default': 1, 'min': 1, 'max': 5}
}


CB_CORE = {
    'system': {
        'type': 'dict',
        'required': True,
        'schema': {
            'unit_system': {'type': 'string', 'allowed': ['metric', 'imperial'], 'default': 'metric'},
            'system_name': {'type': 'string'},
            'mqtt': {
                'type': 'dict',
                'schema': {
                    'broker': {'type': 'string'},
                    'port': {'type': 'integer', 'default': 1883},
                    'username': {'type': 'string'},
                    'password': {'type': 'string'},
                    'base': {'type': 'string', 'default': 'cobrabay'},
                    # 'accept_commands': {'type': 'boolean', 'default': True},
                    'ha': {'type': 'dict',
                           'schema': {
                               'discover': {'type': 'boolean', 'default': True},
                               'pdsend': {'type': 'integer', 'default': 15},
                               'base': {'type': 'string', 'default': 'homeassistant'}
                           },
                           'default': {
                               'discover': True,
                               'pdsend': 15,
                               'base': 'homeassistant'
                           }
                    },
                    'chattiness': {'type': 'dict',
                                   'schema': {
                                       'sensors_raw': {'type': 'boolean', 'default': False},
                                       'sensors_always_send': {'type': 'boolean', 'default': False}
                                   }
                    }
                }
            },
            'interface': {'type': 'string'},  # Define a method to determine default.
            'i2c': {
                'type': 'dict',
                'schema': {
                    'bus': {'type': 'integer', 'required': True},
                    'enable': {'type': 'string', 'required': True},
                    'ready': {'type': 'string', 'required': True},
                    'wait_ready': {'type': 'integer', 'default': 10},
                    'wait_reset': {'type': 'integer', 'default': 10}
                }
            },
            'logging': {
                'type': 'dict',
                'required': True,
                'schema': {
                    'console': {'type': 'boolean', 'required': True, 'default': False},
                    'file': {'type': 'boolean', 'required': True, 'default': True},
                    'file_path': {'type': 'string', 'default': str(Path.cwd() / 'cobrabay.log')},
                    'log_format': {'type': 'string',
                                   'default': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'},
                    'default_level': {'type': 'string',
                                      'allowed': ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                                      'required': True, 'default': 'warning',
                                      'coerce': str.upper},
                    'bays': {'type': 'string',
                             'allowed': ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], 'coerce': str.upper,
                             'default_setter': lambda doc: doc['default_level']},
                    'config': {'type': 'string', 'allowed': ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                               'coerce': str.upper, 'default_setter': lambda doc: doc['default_level']},
                    'core': {'type': 'string', 'allowed': ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                             'coerce': str.upper, 'default_setter': lambda doc: doc['default_level']},
                    'sensors': {'type': 'string', 'allowed': ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                                  'coerce': str.upper, 'default_setter': lambda doc: doc['default_level']},
                    'detector': {
                        'type': 'dict',
                        'keysrules': {
                            'type': 'string',
                            'regex': '[\w]+'
                        },
                        'valuesrules': {
                            'type': 'string', 'allowed': ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
                        }
                    },
                    'display': {'type': 'string', 'allowed': ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                                'coerce': str.upper, 'default_setter': lambda doc: doc['default_level']},
                    'mqtt': {'type': 'string',
                             'allowed': ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', 'DISABLE'],
                             'coerce': str.upper, 'default': 'DISABLE'},
                    'network': {'type': 'string', 'allowed': ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                                'coerce': str.upper, 'default_setter': lambda doc: doc['default_level']},
                    'triggers': {'type': 'string', 'allowed': ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                                 'coerce': str.upper, 'default_setter': lambda doc: doc['default_level']}
                }  # Figure out how to handle specific sensors detectors and bays.
            }
        }
    },
    'triggers': {
        'type': 'dict',
        'required': True,
        'keysrules': {
            'type': 'string',
            'regex': '[\w]+'
        },
        'valuesrules': {
            'type': 'dict',
            'schema': {
                'type': {'type': 'string', 'required': True, 'allowed': ['mqtt_state', 'syscmd', 'baycmd']},
                'bay': {'type': 'string', 'required': True, 'dependencies': {'type': 'mqtt_state'}},
                'topic': {'type': 'string', 'required': True},
                'to': {'type': 'string', 'dependencies': {'type': 'mqtt_state'}, 'excludes': 'from'},
                'from': {'type': 'string', 'dependencies': {'type': 'mqtt_state'}, 'excludes': 'to'},
                'action': {'type': 'string', 'required': True, 'allowed': ['dock', 'undock', 'occupancy']}
            },
            'empty': True
        }
    },
    'display': {
        'type': 'dict',
        'required': True,
        'schema': {
            'width': {'type': 'integer', 'required': True},
            'height': {'type': 'integer', 'required': True},
            'gpio_slowdown': {'type': 'integer', 'required': True, 'default': 4},
            'font': {'type': 'string',
                     'default_setter':
                         lambda doc: str(
                             importlib.resources.files('cobrabay.data').joinpath('OpenSans-Light.ttf'))},
            'font_size_clock': {'type': 'integer'},
            'font_size_range': {'type': 'integer'},
            'strobe_speed': {'type': 'quantity', 'coerce': 'pint_seconds'}
            # 'mqtt_image': {'type': 'boolean', 'default': True},
            # 'mqtt_update_interval': {'type': 'quantity', 'coerce': 'pint_seconds', 'default': '5s'}
        }
    },
    # 'sensors': {
    #     'type': 'dict',
    #     'keysrules': {
    #         'type': 'string',
    #         'regex': '[\w]+'
    #     },
    #     'valuesrules': {
    #         'type': 'dict',
    #         'schema': {
    #             'name': {'type': 'string'},
    #             'error_margin': {'type': 'quantity', 'coerce': 'pint_cm'},
    #             'always_range': {'type': 'boolean', 'default': False},
    #             'hw_type': {'type': 'string', 'required': True, 'allowed': ['TFMini', 'VL53L1X']},
    #             # 'timing': {'type': 'quantity', 'dimensionality': '[time]', 'coerce': pint.Quantity},
    #             'hw_settings': {
    #                 'type': 'dict',
    #                 'required': True,
    #                 'oneof': [
    #                     {'dependencies': {'hw_type': 'TFMini'}, 'schema': SCHEMA_SENSOR_TFMINI},
    #                     {'dependencies': {'hw_type': 'VL53L1X'}, 'schema': SCHEMA_SENSOR_VL53L1X}
    #                 ]
    #             }
    #         }
    #     },
    #     'default': {}
    # },
    'sensors': {
        'type': 'dict',
        'keysrules': {
            'type': 'string',
            'regex': '[\w]+'
        },
        'valuesrules': {
            'type': 'dict',
            'oneof_schema': [SCHEMA_SENSOR_TFMINI, SCHEMA_SENSOR_VL53L1X ]
        },
        'default': {}
    },
    'bays': {
        'type': 'dict',
        'required': True,
        'keysrules': {
            'type': 'string',
            'regex': '[\w]+'
        },
        'valuesrules': {
            'type': 'dict',
            # 'allow_unknown': True,
            'schema': {
                'name': {'type': 'string'},
                'timeouts': {
                    'type': 'dict',
                    'schema': {
                        'dock': {'type': 'quantity', 'coerce': 'pint_seconds', 'default': '2 minutes'},
                        'undock': {'type': 'quantity', 'coerce': 'pint_seconds', 'default': '5 minutes'},
                        'post-roll': {'type': 'quantity', 'coerce': 'pint_seconds', 'default': '10 seconds'}
                    },
                    'default': {
                        'dock': '2 minutes',
                        'undock': '5 minutes',
                        'post-roll': '10 seconds'
                    }
                },
                'depth': {'type': 'quantity', 'coerce': 'pint_cm'},
                'report_adjusted': {'type': 'boolean', 'default': True},
                'longitudinal': {
                    'type': 'dict',
                    'schema': {
                        'defaults': {
                            'type': 'dict',
                            'schema': {
                                'spread_park': {'type': 'quantity', 'coerce': 'pint_cm', 'default': '2 in'},
                                'zero_point': {'type': 'quantity', 'coerce': 'pint_cm', 'default': '0 in'},
                                'pct_warn': {'type': 'number', 'coerce': 'percent', 'min': 0, 'max': 100, 'default': 30},
                                'pct_crit': {'type': 'number', 'coerce': 'percent', 'min': 0, 'max': 100, 'default': 10}
                            }
                        },
                        'sensors': {
                            'type': 'list',
                            'schema': {
                                'type': 'dict',
                                'schema': {
                                    'name': {'type': 'string', 'required': True},
                                    'spread_park': {'type': 'quantity', 'coerce': 'pint_cm'},
                                    'zero_point': {'type': 'quantity', 'coerce': 'pint_cm'},
                                    'pct_warn': {'type': 'number', 'min': 0, 'max': 100},
                                    'pct_crit': {'type': 'number', 'min': 0, 'max': 100}
                                }
                            }
                        }
                    }
                },
                'lateral': {
                    'type': 'dict',
                    # 'allow_unknown': True,
                    'schema': {
                        'defaults': {
                            'type': 'dict',
                            'schema': {
                                'zero_point': {'type': 'quantity', 'coerce': 'pint_cm', 'default': '0 in'},
                                'spread_ok': {'type': 'quantity', 'coerce': 'pint_cm', 'default': '1 in'},
                                'spread_warn': {'type': 'quantity', 'coerce': 'pint_cm', 'default': '3 in'},
                                'limit': {'type': 'quantity', 'coerce': 'pint_cm', 'default': '96 in'},
                                'side': {'type': 'string', 'allowed': ['L', 'R']}
                            }
                        },
                        'sensors': {
                            'type': 'list',
                            'schema': {
                                'type': 'dict',
                                'schema': {
                                    'name': {'type': 'string', 'required': True},
                                    'zero_point': {'type': 'quantity', 'coerce': 'pint_cm'},
                                    'spread_ok': {'type': 'quantity', 'coerce': 'pint_cm'},
                                    'spread_warn': {'type': 'quantity', 'coerce': 'pint_cm'},
                                    'limit': {'type': 'quantity', 'coerce': 'pint_cm'},
                                    'intercept': {'type': 'quantity', 'required': True, 'coerce': 'pint_cm'},
                                    'side': {'type': 'string', 'allowed': ['L', 'R']}
                                }
                            },
                            'default': {}
                        }
                    }
                }
            }
        }
    }
}
