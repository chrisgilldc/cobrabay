"""
Cobra Bay tests for sensormgr
"""

import logging
import pytest
import queue
import cobrabay.sensormgr

# Logger for additional messages
LOGGER = logging.getLogger(__name__)

# Define testing queues
q_cbsmdata = queue.Queue(maxsize=1)
q_cbsmstatus = queue.Queue(maxsize=1)
q_cbsmcontrol = queue.Queue(maxsize=1)


good_sensor_config = {
    "range": {
            "name": "Range",
            "hw_type": "VL53L1X",
            "i2c_bus": 1,
            "i2c_address": 0x30,
            "enable_board": 0x58,
            "enable_pin": 1,
            "distance_mode": "long",
            "timing": "200 ms"
            },
    "front": {
        "name": "Front",
        "hw_type": "VL53L1X",
        "i2c_bus": 1,
        "i2c_address": 0x31,
        "enable_board": 0x58,
        "enable_pin": 2,
        "distance_mode": "long",
        "timing": "200 ms"
    },
    "middle": {
        "name": "Middle",
        "hw_type": "VL53L1X",
        "i2c_bus": 1,
        "i2c_address": 0x32,
        "enable_board": 0x58,
        "enable_pin": 3,
        "distance_mode": "long",
        "timing": "200 ms"
    }
}

good_i2c_config = {
            "bus": 1,
            "enable": "D20",
            "ready": "D21",
            "wait_ready": 10,
            "wait_reset": 10
        }

@pytest.fixture
def new_sensormgr():
    """ Fixture used to get a new sensor manager """

    created_objects = []
    def _make_sensormgr(
            sensor_config,
            i2c_config):
        sensormgr_object = cobrabay.sensormgr.CBSensorMgr(
            sensor_config=sensor_config,
            i2c_config=i2c_config,
            q_cbsmdata=q_cbsmdata,
            q_cbsmstatus=q_cbsmstatus,
            q_cbsmcontrol=q_cbsmcontrol,
            log_level="DEBUG"
        )
        created_objects.append(sensormgr_object)
        return sensormgr_object

    yield _make_sensormgr

    for object in created_objects:
        del(object)

def test_sensormgr_init(new_sensormgr):
    """
    Can the Sensor Manager be initialized.
    """
    sensormgr = new_sensormgr(
        sensor_config=good_sensor_config,
        i2c_config=good_i2c_config
    )

    assert isinstance(sensormgr, cobrabay.CBSensorMgr)

def test_sensormgr_range(new_sensormgr):
    """
    Load the sensor manager, loop it once and ensure it returns a SensorResponse.
    """
    sensormgr = new_sensormgr(
        sensor_config=good_sensor_config,
        i2c_config=good_i2c_config
    )

    # Put the RANGING command in the command queue.
    q_cbsmcontrol.put((cobrabay.const.SENSTATE_RANGING,None))
    sensormgr.loop()

    # Check the return queue.
    scan_data = q_cbsmdata.get()

    assert isinstance(scan_data, cobrabay.datatypes.SensorResponse)

def test_sensormgr_bus_disable(new_sensormgr):
    sensormgr = new_sensormgr(
            sensor_config=good_sensor_config,
            i2c_config=good_i2c_config
    )

    # Disable the bus
    sensormgr._disable_i2c_bus()

    assert not sensormgr._ctrl_ready.value


def test_sensormgr_bus_enable(new_sensormgr):
    sensormgr = new_sensormgr(
        sensor_config=good_sensor_config,
        i2c_config=good_i2c_config
    )

    # Disable the bus
    sensormgr._disable_i2c_bus()
    # Re-enable the bus.
    sensormgr._enable_i2c_bus()

    assert sensormgr._ctrl_ready.value
