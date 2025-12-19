"""
Custom Marshmallow Validators
"""

import pint
from marshmallow.validate import Validator
from marshmallow import ValidationError
from pint.registry import Quantity


class Dimensionality(Validator):
    """
    Validator which ensures a Pint Quantity has a given dimensionality.

    :param dimensionality: A valid Pint dimensionality to enforce

    """
    def __init__(self, dimensionality: str):
        self.dimensionality = dimensionality

    def __call__(self, value: Quantity) -> Quantity:
        if not value:
            raise ValidationError("No value provided.")
        if not isinstance(value, pint.Quantity):
            raise ValidationError("Value is not a pint quantity.")
        if str(value.dimensionality) != self.dimensionality:
            raise ValidationError("Value does not have required dimensionality '{}'. (Actually has {}).".
                                  format(self.dimensionality, str(value.dimensionality)))
        return value