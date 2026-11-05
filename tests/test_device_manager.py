"""
Unit tests for device_manager.py (hardware identification, developer whitelisting).
"""

import pytest
from device_manager import DeviceManager, DEVELOPER_WHITELIST


def test_get_device_info_keys():
    info = DeviceManager.get_device_info()
    expected_keys = [
        "device_id",
        "short_id",
        "raw_guid",
        "node",
        "role",
        "is_developer",
        "machine_name",
        "os",
        "python_version"
    ]
    for k in expected_keys:
        assert k in info
        assert info[k] is not None


def test_short_id_format():
    info = DeviceManager.get_device_info()
    assert info["short_id"].startswith("DEV-")
    # DEV- plus 16 hex chars = 20 chars
    assert len(info["short_id"]) == 20


def test_is_developer_boolean():
    is_dev = DeviceManager.is_developer()
    assert isinstance(is_dev, bool)


def test_device_info_caching():
    d1 = DeviceManager.get_device_info()
    d2 = DeviceManager.get_device_info()
    assert d1 is d2  # identical cached object reference

