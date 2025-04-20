"""
Cobrabay Marshmallow Schema
"""
import typing
from marshmallow import Schema, fields, validate, validates_schema, pre_load, post_load, ValidationError
from marshmallow.fields import Boolean
from marshmallow.experimental.context import Context


# System Schemas

class CBSchemaI2C(Schema):
    """
    Cobrabay I2C Schema
    """
    bus = fields.Int(load_default=1, validate=validate.Range(min=0, max=3))
    enable = fields.Str(load_default="D19")
    ready = fields.Str(load_default="D25")
    wait_ready = fields.Integer(load_default=10, validate=validate.Range(min=0))
    wait_reset = fields.Integer(load_default=10, validate=validate.Range(min=0))

class CBSchemaLogging(Schema):
    """
    Cobrabay Logging Schema
    """
    console = fields.Boolean(load_default=True)
    file = fields.Boolean(load_default=False)
    # file_path - path.cwd() / 'cobrabay.log'
    # Coerce all these to UPPER, limit to valid logging strings. ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    default = fields.Str(load_default='warning', validate=validate.OneOf(choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL']))
    bays = fields.String(validate=validate.OneOf(choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL']))
    config = fields.String(validate=validate.OneOf(choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL']))
    core = fields.String(validate=validate.OneOf(choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL']))
    display = fields.String(validate=validate.OneOf(choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL']))
    mqtt = fields.String(validate=validate.OneOf(choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL']))
    network = fields.String(validate=validate.OneOf(choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL']))
    triggers = fields.String(validate=validate.OneOf(choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL']))
    sensors = fields.String(validate=validate.OneOf(choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL']))

    # @pre_load
    # def preprocess_data(self, data, **kwargs):
    #     # Convert all the logging values to upper case.
    #     log_settings = ['default_level', 'bays', 'config', 'core', 'display', 'mqtt','network','triggers','sensors']
    #     for log in log_settings:
    #         if log in data:
    #             data[log] = data[log].upper()
    #     print(data)
    #     return data

class CBSchemaMQTT(Schema):
    """
    CobraBay MQTT Schema
    """
    broker = fields.String()
    port = fields.Integer(validate=validate.Range(min=1023, max=65536))
    username = fields.String()
    password = fields.String()
    sensors_raw = fields.Bool(load_default=False)
    sensors_always_send = fields.Bool(load_default=False)
    #TODO: Better validation for Subscriptions. Maybe reorganize them?
    subscriptions = fields.List(fields.Dict())

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
    width = fields.Integer(validate=validate.Range(min=0))
    height = fields.Integer(validate=validate.Range(min=0))
    gpio_slowdown = fields.Integer(load_default=5)
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
    interface = fields.String()
    i2c = fields.Nested(CBSchemaI2C)
    logging = fields.Nested(CBSchemaLogging)
    mqtt = fields.Nested(CBSchemaMQTT)

    @pre_load
    def preprocess_data(self, data, **kwargs):
        if 'unit_system' in data:
            data['unit_system'] = data['unit_system'].lower()
        return data

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
