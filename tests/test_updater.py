"""
Unit tests for updater.py (semver parsing, update checking, manifest building).
"""

import os
import pytest
from updater import Updater


def test_parse_semver():
    assert Updater.parse_semver("1.2.0") == (1, 2, 0)
    assert Updater.parse_semver("v1.2.1") == (1, 2, 1)
    assert Updater.parse_semver("V2.0.0") == (2, 0, 0)
    assert Updater.parse_semver("1.0") == (1, 0, 0)
    assert Updater.parse_semver("1") == (1, 0, 0)
    assert Updater.parse_semver("invalid") == (0, 0, 0)


def test_semver_precedence():
    v100 = Updater.parse_semver("1.0.0")
    v110 = Updater.parse_semver("1.1.0")
    v120 = Updater.parse_semver("1.2.0")
    v121 = Updater.parse_semver("1.2.1")
    v200 = Updater.parse_semver("2.0.0")

    assert v110 > v100
    assert v120 > v110
    assert v121 > v120
    assert v200 > v121
    assert not (v120 > v120)


def test_get_current_version():
    ver = Updater.get_current_version()
    assert isinstance(ver, str)
    assert len(ver.split(".")) >= 2


def test_get_manifest_url_default():
    url = Updater.get_manifest_url()
    assert "https://raw.githubusercontent.com/" in url
    assert "version.json" in url


def test_load_update_config():
    cfg = Updater.load_update_config()
    assert "github_repo" in cfg
    assert "branch" in cfg
    assert "auto_check_on_startup" in cfg

