"""
Custom Marshmallow Validators
"""

import pint
from marshmallow.validate import Validator
from marshmallow import ValidationError
from pint.registry import Quantity


class Dimensionality(Validator):
    """
    Ensure a Quantity has a given dimensionality.

    :param dimensionality: A valid Pint dimensionality to enforce

    """
    def __init__(self):
        pass

    def _call_(self, value: Quantity, dimensionality: str) -> Quantity:
        if not value:
            raise ValidationError("No value provided.")
        if not isinstance(value, pint.Quantity):
            raise ValidationError("Value is not a pint quantity.")
        if str(value.dimensionality) != dimensionality:
            raise ValidationError("Value does not have required dimensionality '{}'. (Actually has {}).".
                                  format(dimensionality, str(value.dimensionality)))
        return value