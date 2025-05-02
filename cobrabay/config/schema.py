"""
Cobrabay Marshmallow Schema
"""
import os
import importlib
from pathlib import Path
import typing
from marshmallow import Schema, fields, validate, validates_schema, pre_load, post_load, ValidationError
from marshmallow.fields import Boolean
from marshmallow.experimental.context import Context
from pint import Quantity
from .fields import Quantity as FieldQuantity
from .validators import Dimensionality

# System Schemas

class CBSchemaHA(Schema):
    """
    Cobrabay Home Assistant Schema
    """
    discover = fields.Boolean(load_default=True)
    pd_send = fields.Integer(load_default=15)
    base = fields.String(load_default="homeassistant")
    suggested_area = fields.String(load_default="Garage")

class CBSchemaI2C(Schema):
    """
    Cobrabay I2C Schema
    """
    bus = fields.Int(load_default=1, validate=validate.Range(min=0, max=3))
    enable = fields.Str(load_default="D19")
    ready = fields.Str(load_default="D25")
    wait_ready = fields.Integer(load_default=10, validate=validate.Range(min=0))
    wait_reset = fields.Integer(load_default=10, validate=validate.Range(min=0))
    # wait_ready = FieldQuantity(load_default=Quantity("10 seconds"), validate=Dimensionality(dimensionality="[time]"))
    #wait_reset = fields.Integer(load_default=10, validate=validate.Range(min=0))



class CBSchemaLogging(Schema):
    """
    Cobrabay Logging Schema
    """
    console = fields.Boolean(load_default=True)
    file = fields.Boolean(load_default=False)
#TODO: Fix log path assembly.
    log_file = fields.String(load_default=Path.cwd() / 'cobrabay.log')
    log_format = fields.String(load_default="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    # Coerce all these to UPPER, limit to valid logging strings. ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    default = fields.Str(load_default='WARNING', validate=validate.OneOf(choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL']))
    bays = fields.String(validate=validate.OneOf(choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL']))
    config = fields.String(validate=validate.OneOf(choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL']))
    core = fields.String(validate=validate.OneOf(choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL']))
    display = fields.String(validate=validate.OneOf(choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL']))
    mqtt = fields.String(validate=validate.OneOf(choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL']))
    network = fields.String(validate=validate.OneOf(choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL']))
    triggers = fields.String(validate=validate.OneOf(choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL']))
    sensors = fields.String(validate=validate.OneOf(choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL']))

    @pre_load
    def preprocess_data(self, data, **kwargs):
        # Convert all the logging values to upper case.
        log_settings = ['default', 'bays', 'config', 'core', 'display', 'mqtt','network','triggers','sensors']
        for log in log_settings:
            if log in data:
                data[log] = data[log].upper()
        return data

class CBSchemaMQTT(Schema):
    """
    CobraBay MQTT Schema
    """
    broker = fields.String()
    port = fields.Integer(validate=validate.Range(min=1023, max=65536))
    base = fields.String(load_default="cobrabay")
    username = fields.String()
    password = fields.String()
    sensors_raw = fields.Bool(load_default=False)
    sensors_always_send = fields.Bool(load_default=False)
    #TODO: Better validation for Subscriptions. Maybe reorganize them?
    subscriptions = fields.List(fields.Dict())

    @pre_load
    def preprocess_data(self, data, **kwargs):
        # Appropriate override settings based on environment or command line.
        cmd_options = Context.get()['cmd_options']
        env_options = Context.get()['env_options']
        print("Got cmd options: {}".format(cmd_options))
        print("Got env options: {}".format(env_options))
        # Broker
        if cmd_options.mqttbroker is not None:
            data['broker'] = cmd_options.mqttbroker
        elif env_options.mqttbroker is not None:
            data['broker'] = env_options.mqttbroker
        elif data['broker'] is None:
            raise ValidationError("MQTT Broker must be defined!")

        # Port
        if cmd_options.mqttport is not None:
            data['port'] = cmd_options.mqttport
        elif env_options.mqttport is not None:
            data['port'] = env_options.mqttport
        else:
            data['port'] = 1883

        return data

class CBSchemaIcons(Schema):
    """
    Cobrabay Icons Schema
    """
    # This is a special syntax for field that aren't valid attribute names.
    class Meta:
        include = {
            'ev-battery': fields.Boolean(load_default=False),
            'ev-plug': fields.Boolean(load_default=False),
            'garage-door': fields.Boolean(load_default=False),
            'mini-vehicle': fields.Boolean(load_default=False)
        }

    network = fields.Boolean(load_default=True)
    sensors = fields.Boolean(load_default=False)

# Top level schemas

class CBSchemaDisplay(Schema):
    """
    Cobrabay Display Schema
    """
    def _default_font():
        return importlib.resources.files('cobrabay.data').joinpath('OpenSans-Light.ttf')

    width = fields.Integer(validate=validate.Range(min=0))
    height = fields.Integer(validate=validate.Range(min=0))
    gpio_slowdown = fields.Integer(load_default=5)
    font = fields.String(load_default=_default_font)
    font_size_clock = fields.Integer()
    font_size_range = fields.Integer()
    icons = fields.Nested(CBSchemaIcons)

class CBSchemaSensor(Schema):
    """
    Cobrabay Sensor Schema
    """
    name = fields.String(required=True)
    hw_type = fields.String(required=True, validate=validate.OneOf(['vl53l1x','tfmini']))
    distance_mode = fields.String(load_default='long')
    # TFMini fields
    port = fields.String(required=False)
    baud = fields.Integer(required=False, validate=validate.OneOf([115200, 57600, 38400, 28800, 19200, 9600, 4800, 2400]))
    clustering = fields.Integer(required=False, load_default=3)
    # VL53L1X fields
    i2c_bus = fields.Integer(required=False, validate=validate.OneOf([1,2]))
    i2c_address = fields.Integer(required=False, validate=validate.Range(min=0, min_inclusive=True, max=127, max_inclusive=True))
    enable_board = fields.Integer(required=False, validate=validate.Range(min=0, min_inclusive=True, max=127, max_inclusive=True))
    enable_pin = fields.Integer(required=False, validate=validate.Range(min=0, min_inclusive=True, max=15, max_inclusive=True))
    timing = fields.String(required=False)

    @pre_load
    def preprocess_data(self, data, **kwargs):
        # Ensure string fields wind up properly lower-case.
        for lc_field in ['hw_type', 'distance_mode']:
            if lc_field in data:
                data[lc_field] = data[lc_field].lower()

        return data

    @validates_schema
    def validate_requires(self, data, **kwargs):
        missing_fields = []
        if data['hw_type'] == 'vl53l1x':
            required_fields = ["i2c_bus", "i2c_address", "enable_board", "enable_pin", "timing"]
        elif data['hw_type'] == 'tfmini':
            required_fields = ["port", "baud", "clustering"]
        else:
            raise ValidationError("Hardware is of an unknown type. ({})".format(data['hw_type']))

        for field in required_fields:
            if field not in data:
                missing_fields.append(field)

        if len(missing_fields) > 0:
            raise ValidationError({missing_field:["Missing data for required field."] for missing_field in missing_fields})

class CBSchemaSystem(Schema):
    """
    Cobrabay System Schema
    """
    unit_system = fields.Str(load_default='metric', validate=validate.OneOf(['metric','imperial']))
    system_name = fields.String()
    interface = fields.String(required=True)
    i2c = fields.Nested(CBSchemaI2C, required=True)
    logging = fields.Nested(CBSchemaLogging, required=True)
    mqtt = fields.Nested(CBSchemaMQTT, required=True)
    ha = fields.Nested(CBSchemaHA, load_default=CBSchemaHA)

    @pre_load
    def preprocess_data(self, data, **kwargs):
        # Make unit system lower-case so it string matches.
        if 'unit_system' in data:
            data['unit_system'] = data['unit_system'].lower()

        # Make sure the required base keys exist for sub-schemas.
        required_keys = ('i2c','logging','mqtt','ha')
        for subschema in required_keys:
            if subschema not in data:
                data[subschema] = {}
        return data

    def _systemname(self):
        return os.uname().nodename

class CBSchemaTrigger(Schema):
    """
    Cobrabay Trigger Schema
    """
    topic = fields.String()
    type = fields.String()
    bay = fields.String()
    payload_from = fields.String()
    payload_true = fields.String()
    action = fields.String(validate=validate.OneOf(['dock','undock','occupancy', 'abort']))

    @pre_load
    def preprocess_data(self, data, **kwargs):
        if 'payload_from' not in data and 'payload_to' not in data:
            raise ValidationError("Either 'payload_from' or 'payload_to' must be defined for MQTT triggers")
        return data

# Core Schema is here.

class CBSchema(Schema):
    """
    Base Cobrabay config file schema
    """
    system = fields.Nested(CBSchemaSystem)
    triggers = fields.Dict(keys=fields.String(), values=fields.Nested(CBSchemaTrigger()))
    display = fields.Nested(CBSchemaDisplay)
    sensors = fields.Dict(keys=fields.String(), values=fields.Nested(CBSchemaSensor()))
    #TODO: Flesh out bays into its own class to perform full validation.
    bays = fields.Dict()
