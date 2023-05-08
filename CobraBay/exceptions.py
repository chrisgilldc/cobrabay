####
# Cobra Bay - Exceptions
#
# Custom Exceptions for CobraBay to raise
####

class CobraBayException(Exception):
    """CobraBay Exceptions"""

class SensorValueException(CobraBayException):
    """Raised when a sensor reads a value that indicates a non-range state."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self._status = kwargs['status']

    @property
    def status(self):
        return self._status