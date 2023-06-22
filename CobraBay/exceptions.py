####
# Cobra Bay - Exceptions
#
# Custom Exceptions for CobraBay to raise
####

class CobraBayException(Exception):
    """CobraBay Exceptions"""

class SensorException(CobraBayException):
    """Sensor failure"""
