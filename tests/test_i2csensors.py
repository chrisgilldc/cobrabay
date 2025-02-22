"""
Cobra Bay tests for the VL53L1X sensor and supporting I2C infrastructure.
"""
import adafruit_aw9523
import pytest
from pint import Quantity
import busio
import board
from cobrabay.sensors import CBVL53L1X
import cobrabay.const
import cobrabay.datatypes
import cobrabay.util
from adafruit_aw9523 import AW9523

### Basic tests for the AW9523. If these fail, don't expect anything else to work.
@pytest.mark.i2c
@pytest.mark.aw9523
def test_aw9523_init():
    """ Can we initialize the AW9523 """
    i2c = busio.I2C(board.SCL, board.SDA)
    aw = AW9523(i2c)
    assert isinstance(aw, adafruit_aw9523.AW9523)

@pytest.mark.i2c
@pytest.mark.aw9523
def test_aw9523_badaddr():
    """ Do we get an exception with an incorrect address """
    i2c = busio.I2C(board.SCL, board.SDA)
    with pytest.raises(ValueError):
        aw = AW9523(i2c, 0x59)

@pytest.mark.i2c
@pytest.mark.aw9523
def test_aw9523_pinsoff():
    """ Test the process to be sure all pins are off. That should leave only one device on the bus. """
    i2c = busio.I2C(board.SCL, board.SDA)
    aw = AW9523(i2c)
    cobrabay.util.aw9523_reset(aw)
    active_bus_devices = cobrabay.util.scan_i2c()
    assert len(active_bus_devices) == 1

### VL53L1X Tests ###

@pytest.fixture
def new_cbvl53l1x():
    """ Fixture used to get a new CBVL53L1X instance """
    # Follows the factory pattern from here: https://docs.pytest.org/en/stable/how-to/fixtures.html#factories-as-fixtures
    created_objects = []
    # Statically define the I2C bus and the AW9523.
    i2c = busio.I2C(board.SCL, board.SDA)
    aw = AW9523(i2c, 0x59)
    # Reset all pins to be false. Initialization of the AW9523 can be wonky and depend on the address.
    cobrabay.util.aw9523_reset(aw)

    def _make_cbvl53l1x(name, i2c_address, enable_pin):
        sensor_object = CBVL53L1X(
            name="name",
            i2c_address=i2c_address,
            enable_board=aw,
            enable_pin=enable_pin,
            i2c_bus=i2c)
        created_objects.append(sensor_object)
        return sensor_object

    yield _make_cbvl53l1x

    for object in created_objects:
        del(object)

@pytest.mark.i2c
@pytest.mark.vl53l1x
def test_single_state_after_init(new_cbvl53l1x):
    """ Does a newly initialize sensor come up with the 'enabled' state? """
    sensor = new_cbvl53l1x("sensor1", 0x31, 1)
    assert sensor.state == cobrabay.const.SENSTATE_ENABLED

@pytest.mark.i2c
@pytest.mark.vl53l1x
def test_correct_address(new_cbvl53l1x):
    """ When initialized, does the sensor appear on the correct address? """
    sensor = new_cbvl53l1x("test_sensor", 0x61, 1)
    active_bus_devices = cobrabay.util.scan_i2c()
    # After sensor is active, it's address (0x61) should come back in a bus scan.
    assert '0x61' in active_bus_devices

@pytest.mark.i2c
@pytest.mark.vl53l1x
def test_state_disabled(new_cbvl53l1x):
    """ When a status of disabled is set, the sensor's state should become disabled
    and it should be shutoff, as shown by disappearing from the I2C bus. """
    errors = []
    sensor = new_cbvl53l1x("sensor1", 0x31, 1)
    sensor.status = cobrabay.const.SENSTATE_DISABLED
    active_devices = cobrabay.util.scan_i2c()
    # Once disabled the sensor should no longer appear on the bus.
    if '0x61' in active_devices:
        errors.append("Sensor still active on bus.")
    # The status is the actual reflection of what's happening, which should be what was requested.
    if sensor.state is not cobrabay.const.SENSTATE_DISABLED:
        errors.append("Sensor state is not disabled.")
    # Assert we shouldn't have errors.
    assert not errors, "Errors occurred:\n{}".format("\n".join(errors))

@pytest.mark.i2c
@pytest.mark.vl53l1x
def test_state_ranging(new_cbvl53l1x):
    """ Make sure the sensor returns a SensorReading"""
    sensor1 = new_cbvl53l1x("sensor1", 0x31, 1)
    sensor1.status = cobrabay.const.SENSTATE_RANGING
    reading = sensor1.reading()
    assert isinstance(reading, cobrabay.datatypes.SensorReading)

@pytest.mark.i2c
@pytest.mark.vl53l1x
def test_state_ranging_notranging(new_cbvl53l1x):
    """ A sensor in any state other than ranging should return the 'not_ranging' string as its reading."""
    sensor1 = new_cbvl53l1x("sensor1", 0x31, 1)
    reading = sensor1.reading()
    assert reading == cobrabay.const.SENSTATE_NOTRANGING

@pytest.mark.i2c
@pytest.mark.vl53l1x
@pytest.mark.hwstress
def test_state_stress(new_cbvl53l1x):
    """ A sensor in any state other than ranging should return the 'not_ranging' string as its reading."""
    sensor1 = new_cbvl53l1x("sensor1", 0x31, 1)
    result_array = []
    while len(result_array) < 100:
        result_array.append(sensor1.state)

    assert len(result_array) == 100

### VL53L1X Sensor in full array.
@pytest.mark.i2c
@pytest.mark.vl53l1x
@pytest.mark.vl53l1x_array
def test_array_state_after_init(new_cbvl53l1x):
    """ Test a set of VL53L1X sensors"""
    sensor1 = new_cbvl53l1x("sensor1", 0x31, 1)
    sensor2 = new_cbvl53l1x("sensor2", 0x32, 2)
    sensor3 = new_cbvl53l1x("sensor3", 0x33, 3)
    enabled = 0
    for obj in (sensor1, sensor2, sensor3):
        if obj.state == cobrabay.const.SENSTATE_ENABLED:
            enabled += 1
    assert enabled == 3

@pytest.mark.i2c
@pytest.mark.vl53l1x
@pytest.mark.vl53l1x_array
def test_array_correct_addresses(new_cbvl53l1x):
    """ When initialized, does the sensor appear on the correct address? """
    sensor1 = new_cbvl53l1x("sensor1", 0x31, 1)
    sensor2 = new_cbvl53l1x("sensor2", 0x32, 2)
    sensor3 = new_cbvl53l1x("sensor3", 0x33, 3)
    active_bus_devices = cobrabay.util.scan_i2c()

    # After sensor is active, it's address (0x61) should come back in a bus scan.
    assert '0x31' in active_bus_devices


