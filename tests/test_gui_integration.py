"""
Integration tests for GUI configuration bindings and validation helpers.
"""

import pytest
from config_manager import ConfigManager, AppConfig
from validator import PreFlightValidator


def test_config_gui_binding_integration():
    # Verify that AppConfig can accept GUI-shaped dictionaries and serialize cleanly
    gui_dict = {
        "browser": "edge",
        "profile_index": 0,
        "data_file": "contacts_sample.xlsx",
        "default_country_code": "91",
        "default_message": "Hello {name}",
        "min_delay": 9.5,
        "max_delay": 16.0,
        "batch_size": 25,
        "batch_pause": 75.0,
        "daily_cap": 80,
        "attach_enabled": False,
        "attachment_path": "",
        "headless": True,
        "sched_enabled": False,
        "sched_time": "14:30",
        "dev_mode": True
    }

    cfg = AppConfig.from_dict(gui_dict)
    assert cfg.browser == "edge"
    assert cfg.min_delay == 9.5
    assert cfg.max_delay == 16.0
    assert cfg.batch_size == 25
    assert cfg.batch_pause == 75.0
    assert cfg.daily_cap == 80
    assert cfg.headless is True
    assert cfg.dev_mode is True

    is_valid, issues = cfg.validate()
    assert is_valid is True
    assert len(issues) == 0


def test_preflight_validator_gui_integration():
    contacts = [
        {"phone": "919876543210", "name": "John Doe", "message": "Hi John!"},
        {"phone": "919876543210", "name": "John Duplicate", "message": "Hi John duplicate!"},
        {"phone": "14155552671", "name": "Sarah", "message": "Hello Sarah!"}
    ]
    cfg = AppConfig(min_delay=8.0, max_delay=15.0, batch_size=20, batch_pause=60.0)
    report = PreFlightValidator.audit_contacts(contacts, cfg)

    assert report.total_contacts == 3
    assert report.duplicate_count == 1
    assert report.is_ready_to_send is True

    # Deduplicate
    deduped, removed = PreFlightValidator.deduplicate_contacts(contacts)
    assert removed == 1
    assert len(deduped) == 2
    assert deduped[0]["name"] == "John Doe"
    assert deduped[1]["name"] == "Sarah"

