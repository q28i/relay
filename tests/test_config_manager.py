"""
Unit tests for config_manager.py (schema, validation, presets, persistence).
"""

import os
import pytest
from config_manager import AppConfig, ConfigManager, BUILTIN_PRESETS


def test_app_config_defaults():
    cfg = AppConfig()
    assert cfg.browser == "chrome"
    assert cfg.min_delay == 8.0
    assert cfg.max_delay == 15.0
    assert cfg.batch_size == 20
    assert cfg.batch_pause == 60.0
    assert cfg.daily_cap == 100
    assert cfg.schema_version == 1

    is_valid, issues = cfg.validate()
    assert is_valid is True
    assert len(issues) == 0


def test_apply_builtin_presets():
    cfg = AppConfig()

    # Apply Safe Warm-up
    ok = cfg.apply_preset("safe")
    assert ok is True
    assert cfg.min_delay == 12.0
    assert cfg.max_delay == 20.0
    assert cfg.batch_size == 15
    assert cfg.batch_pause == 90.0
    assert cfg.daily_cap == 30
    assert cfg.active_preset == "safe"

    # Apply Fast
    ok = cfg.apply_preset("fast")
    assert ok is True
    assert cfg.min_delay == 4.0
    assert cfg.max_delay == 8.0
    assert cfg.batch_size == 30
    assert cfg.batch_pause == 30.0
    assert cfg.daily_cap == 200

    # Non-existent preset returns False
    assert cfg.apply_preset("non_existent_preset") is False


def test_validation_invalid_bounds():
    # Min delay too small
    cfg1 = AppConfig(min_delay=0.2)
    is_valid, issues = cfg1.validate()
    assert is_valid is False
    assert any("Min delay" in i for i in issues)

    # Max delay < min delay
    cfg2 = AppConfig(min_delay=10.0, max_delay=5.0)
    is_valid, issues = cfg2.validate()
    assert is_valid is False
    assert any("cannot be less than Min delay" in i for i in issues)

    # Invalid browser
    cfg3 = AppConfig(browser="firefox_unsupported")
    is_valid, issues = cfg3.validate()
    assert is_valid is False
    assert any("Invalid browser" in i for i in issues)

    # Invalid schedule time
    cfg4 = AppConfig(sched_time="25:99")
    is_valid, issues = cfg4.validate()
    assert is_valid is False
    assert any("Invalid schedule time" in i for i in issues)


def test_serialization_round_trip(tmp_path):
    p = str(tmp_path / "test_config.json")
    cfg = AppConfig(
        browser="edge",
        default_country_code="91",
        min_delay=10.0,
        max_delay=18.0,
        daily_cap=150
    )

    saved = ConfigManager.save(cfg, file_path=p)
    assert saved is True
    assert os.path.isfile(p)

    loaded = ConfigManager.load(file_path=p)
    assert loaded.browser == "edge"
    assert loaded.default_country_code == "91"
    assert loaded.min_delay == 10.0
    assert loaded.max_delay == 18.0
    assert loaded.daily_cap == 150


def test_profile_export_import(tmp_path):
    p = str(tmp_path / "marketing_profile.json")
    cfg = AppConfig(daily_cap=50, active_preset="safe")

    assert ConfigManager.export_profile(cfg, p) is True
    imported = ConfigManager.import_profile(p)
    assert imported is not None
    assert imported.daily_cap == 50
    assert imported.active_preset == "safe"

