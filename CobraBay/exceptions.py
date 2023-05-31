####
# Cobra Bay - Exceptions
#
# Custom Exceptions for CobraBay to raise
####

class CobraBayException(Exception):
    """CobraBay Exceptions"""

class SensorException(CobraBayException):
    """Sensor failure"""

class SensorWarning(CobraBayException):
    """Non-fatal sensor states"""

class SensorNotRangingWarning(SensorWarning):
    """Sensor reading when not ranging"""

class SensorFloodWarning(SensorWarning):
    """Sensor has been flooded"""

class SensorNoReadingWarning(SensorWarning):
    """Sensor returned no value"""

class SensorWeakWarning(SensorWarning):
    """Sensor is weak"""
