"""
Cobra Bay tests for utilities
"""

import pytest
from pint import Quantity
from cobrabay.util import Convertomatic

#TODO: Fix temperature conversion test.

metric_to_imperial = [
    (Quantity("1 meter"), 39.37),
    # (Quantity("10 degC"), 50),
    (Quantity("50 kph"), 31.07),
    (Quantity("8923940 bytes"), 8.92),
    (Quantity("2.5 seconds"),2),
    (Quantity("5"),5)
]

imperial_to_metric = [
    (Quantity("10 feet"), 304.8),
    # (Quantity("10 degF"), -12.22),
    (Quantity("50 mph"), 80.47),
    (Quantity("8923940 bytes"), 8.92),
    (Quantity("2.5 seconds"),2),
    (Quantity("5"),5)
]
@pytest.fixture
def newConvertomatic_i():
    ConvertomaticInstance = Convertomatic("imperial")
    return ConvertomaticInstance

@pytest.fixture
def newConvertomatic_m():
    ConvertomaticInstance = Convertomatic("metric")
    return ConvertomaticInstance

@pytest.mark.parametrize("test_input,expected", metric_to_imperial)
def test_metric_to_imperial(test_input, expected, newConvertomatic_i):
    """ Length, Meters to Feet"""
    objectUnderTest = newConvertomatic_i
    assert objectUnderTest.convert(test_input) == expected

@pytest.mark.parametrize("test_input,expected", imperial_to_metric)
def test_imperial_to_metric(test_input, expected, newConvertomatic_m):
    """ Length, Meters to Feet"""
    objectUnderTest = newConvertomatic_m
    assert objectUnderTest.convert(test_input) == expected