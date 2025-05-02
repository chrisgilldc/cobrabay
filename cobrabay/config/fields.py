"""
Custom fields for Cobrabay
"""
import pint
from marshmallow import fields, ValidationError

class Quantity(fields.Field):
    """
    Field that deserializes into a Pint Quantity and serializes into a string.
    """

    def _serialize(self, value, attr, obj, **kwargs):
        if value is None:
            return
        return str(value)

    def _deserialize(self, value, attr, data, **kwargs):
        try:
            return pint.Quantity(value)
        except pint.errors.UndefinedUnitError as error:
            raise ValidationError("Value could not be converted to a known Quantity.") from error
