"""
CobraBay tests for config
"""

import pytest
from cobrabay.config import CBCoreConfig, CBValidator

test_config_file = "./test_config.yaml"

def test_cbconfig_nofile():
    with pytest.raises(TypeError):
        CBCoreConfig()

def test_cbconfig_file():
    CBCoreConfig(config_file=test_config_file)