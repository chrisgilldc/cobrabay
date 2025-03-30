"""
Cobra Bay Validator
"""

# import logging
# import yaml
# from pathlib import Path
import pint
import cerberus
# from pprint import pformat
# import importlib.resources
# from datetime import datetime
# from cobrabay.datatypes import CBValidation, ENVOPTIONS_EMPTY

class CBValidator(cerberus.Validator):
    """
    Cerberus Validator with custom rules and types.

    Supports the 'quantity' type, constraining on dimensionality and coercing values to 'seconds' or 'cm'.
    """
    types_mapping = cerberus.Validator.types_mapping.copy()
    types_mapping['quantity'] = cerberus.TypeDefinition('quantity', (pint.Quantity,), ())

    # # Checks to see if a value can be converted by Pint, and if it has a given dimensionality.
    def _validate_dimensionality(self, constraint, field, value):
        """
        {'type': 'string'}
        """
        if str(value.dimensionality) != constraint:
            self._error(field, "Not in proper dimension {}".format(constraint))

    # Coercers. Apparently you can't pass parameters, so each unit needs its own.
    @staticmethod
    def _normalize_coerce_pint_seconds(value):
        return pint.Quantity(value).to('seconds')

    @staticmethod
    def _normalize_coerce_pint_ms(value):
        return pint.Quantity(value).to('milliseconds')

    @staticmethod
    def _normalize_coerce_pint_cm(value):
        return pint.Quantity(value).to('cm')

    @staticmethod
    def _normalize_coerce_percent(value):
        if value > 1:
            return value / 100

