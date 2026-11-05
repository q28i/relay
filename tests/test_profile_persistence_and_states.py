"""
Unit and Integration Tests for Persistent Browser Profiles, Smart Detection, and Honest States.
Verifies:
1. Profile preference persistence in SQLite (whatsapp auto / Profile 10).
2. Clean separation of saved_config, active_session, connection_health, and pending_transition.
3. Smart profile-specific process detection (no false 'In Use' locks across all profiles).
4. Honest states: available, browser_running, in_use, active_in_relay, profile_unavailable, stale_lock.
5. Non-destructive Test Connection (never sends messages).
6. Preference updates and startup restoration without silent fallback to dedicated session.
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from backend.app import app
from backend.database import db
from browser_manager import BrowserManager
from config_manager import ConfigManager
from backend.connection_monitor import connection_monitor, ConnectionState


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def setup_profile_preference():
    db.save_browser_profile_preference(
        browser_id="chrome",
        browser_family="chrome",
        profile_display_name="whatsapp auto",
        canonical_profile_dir="Profile 10",
        connection_mode="existing_profile",
        remember_profile=True,
        auto_connect=False
    )
    cm = ConfigManager()
    cfg = cm.get_config()
    cfg.browser = "chrome"
    cfg.profile_dir = "Profile 10"
    cfg.profile_name = "whatsapp auto"
    cm.save_config(cfg)


def test_browser_preferences_seeding_and_crud():
    """Verify preference persistence table, discovery of whatsapp auto, and CRUD operations."""
    pref = db.get_browser_profile_preference()
    assert pref is not None
    # User's Chrome has Profile 10 named 'whatsapp auto'
    assert pref.get("profile_display_name") == "whatsapp auto"
    assert pref.get("canonical_profile_dir") == "Profile 10"
    assert pref.get("browser_id") == "chrome"
    assert pref.get("remember_profile") == 1
    assert pref.get("auto_connect") == 0

    # Test saving preference
    db.save_browser_profile_preference(
        browser_id="chrome",
        browser_family="chrome",
        browser_exe_path="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        profile_display_name="whatsapp auto",
        canonical_profile_dir="Profile 10",
        connection_mode="existing_profile",
        remember_profile=True,
        auto_connect=True
    )
    updated = db.get_browser_profile_preference()
    assert updated["remember_profile"] == 1
    assert updated["auto_connect"] == 1

    # Test updating last connected
    db.update_browser_last_connected()
    after_conn = db.get_browser_profile_preference()
    assert after_conn["last_connected_at"] is not None


def test_get_browser_selection_structured_response(client):
    """GET /api/browser-profile/selection must return cleanly separated sections."""
    res = client.get("/api/browser-profile/selection")
    assert res.status_code == 200
    data = res.json()

    # Verify structured separation
    assert "saved_config" in data
    assert "active_session" in data
    assert "connection_health" in data
    assert "pending_transition" in data

    saved = data["saved_config"]
    assert saved["browser"] == "chrome"
    assert saved["profile_dir"] == "Profile 10"
    assert saved["profile_name"] == "whatsapp auto"
    assert saved["remember_profile"] is True

    health = data["connection_health"]
    assert "state" in health
    assert "health_state" in health
    assert "status" in health

    # Verify backwards compatibility flat keys
    assert data["browser"] == "chrome"
    assert data["profile_dir"] == "Profile 10"
    assert data["profile_name"] == "whatsapp auto"


def test_preference_restores_without_silent_fallback_to_dedicated(client):
    """Even if config.json defaults or was reset, saved preference restores whatsapp auto."""
    # Temporarily set config profile_dir to __dedicated__
    cm = ConfigManager()
    cfg = cm.get_config()
    cfg.profile_dir = "__dedicated__"
    cfg.profile_name = "Dedicated WhatsApp Session"
    cm.save_config(cfg)

    # Calling get_browser_selection should restore saved preference
    res = client.get("/api/browser-profile/selection")
    assert res.status_code == 200
    data = res.json()
    assert data["saved_config"]["profile_dir"] == "Profile 10"
    assert data["saved_config"]["profile_name"] == "whatsapp auto"
    assert data["profile_dir"] == "Profile 10"


def test_smart_detection_distinguishes_other_profiles():
    """Chrome running with another profile must return 'browser_running', NOT false 'in_use'."""
    # Mock psutil to simulate Chrome running on 'Profile 1'
    class MockProcess:
        def __init__(self, pid, name, cmdline):
            self.info = {'pid': pid, 'name': name, 'exe': 'chrome.exe', 'cmdline': cmdline}

    mock_proc = MockProcess(
        pid=12345,
        name='chrome.exe',
        cmdline=['chrome.exe', '--user-data-dir=C:\\Users\\Rift\\AppData\\Local\\Google\\Chrome\\User Data', '--profile-directory=Profile 1']
    )

    with patch('psutil.process_iter', return_value=[mock_proc]), \
         patch('browser_manager.has_visible_window', return_value=True), \
         patch('os.path.isfile', return_value=True), \
         patch('os.path.isdir', return_value=True), \
         patch('os.path.exists', return_value=False):

        # Diagnose target Profile 10 (whatsapp auto)
        diag = BrowserManager.diagnose_profile("chrome", profile_dir="Profile 10")
        assert diag["condition"] == "BROWSER_RUNNING_OTHER_PROFILE"
        assert diag["availability"] == "browser_running"
        assert diag["is_locked"] is False
        assert len(diag["matching_pids"]) == 0
        assert 12345 in diag["browser_running_pids"]

        # Diagnose target Profile 1 (the one actually open)
        diag_p1 = BrowserManager.diagnose_profile("chrome", profile_dir="Profile 1")
        assert diag_p1["condition"] == "ACTIVE_VISIBLE_PROCESS"
        assert diag_p1["availability"] == "in_use"
        assert diag_p1["is_locked"] is True
        assert 12345 in diag_p1["matching_pids"]


def test_smart_detection_identifies_active_in_relay():
    """When the matching process is owned by Relay, condition is ACTIVE_IN_RELAY and not locked."""
    class MockProcess:
        def __init__(self, pid, name, cmdline):
            self.info = {'pid': pid, 'name': name, 'exe': 'chrome.exe', 'cmdline': cmdline}

    mock_proc = MockProcess(
        pid=54321,
        name='chrome.exe',
        cmdline=['chrome.exe', '--user-data-dir=C:\\Users\\Rift\\AppData\\Local\\Google\\Chrome\\User Data', '--profile-directory=Profile 10']
    )

    with patch('psutil.process_iter', return_value=[mock_proc]), \
         patch('browser_manager.has_visible_window', return_value=True), \
         patch('os.path.isfile', return_value=True), \
         patch('os.path.isdir', return_value=True), \
         patch('os.path.exists', return_value=False), \
         patch('backend.session_lifecycle.session_lifecycle.is_relay_owned_pid', return_value=True):

        diag = BrowserManager.diagnose_profile("chrome", profile_dir="Profile 10")
        assert diag["condition"] == "ACTIVE_IN_RELAY"
        assert diag["availability"] == "active_in_relay"
        assert diag["is_locked"] is False
        assert diag["is_relay_owned"] is True


def test_smart_detection_identifies_stale_lock():
    """When lock exists on disk but no process is running, condition is STALE_LOCK_ARTIFACT."""
    with patch('psutil.process_iter', return_value=[]), \
         patch('os.path.isfile', return_value=True), \
         patch('os.path.isdir', return_value=True), \
         patch('os.path.exists', return_value=True), \
         patch('builtins.open', side_effect=PermissionError("Locked by OS")):

        diag = BrowserManager.diagnose_profile("chrome", profile_dir="Profile 10")
        assert diag["condition"] == "STALE_LOCK_ARTIFACT"
        assert diag["availability"] == "stale_lock"
        assert diag["is_locked"] is False
        assert diag["is_stale_lock"] is True


def test_preferences_api_endpoints(client):
    """GET and POST /api/browser-profile/preferences."""
    get_res = client.get("/api/browser-profile/preferences")
    assert get_res.status_code == 200
    pref = get_res.json()["preferences"]
    assert pref["profile_display_name"] == "whatsapp auto"

    # Update auto_connect
    post_res = client.post("/api/browser-profile/preferences", json={"auto_connect": True})
    assert post_res.status_code == 200
    assert post_res.json()["preferences"]["auto_connect"] == 1

    # Restore auto_connect to False
    client.post("/api/browser-profile/preferences", json={"auto_connect": False})
    restored = client.get("/api/browser-profile/preferences").json()["preferences"]
    assert restored["auto_connect"] == 0


def test_test_connection_never_sends_messages(client):
    """Test Connection must verify launcher and session without dispatching any messages."""
    with patch('backend.session_lifecycle.session_lifecycle.is_session_healthy', return_value=True), \
         patch.object(connection_monitor, 'is_connected', return_value=True), \
         patch.object(connection_monitor, 'get_driver', return_value=MagicMock()):

        res = client.post("/api/browser-profile/test")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "Signed in"
        assert data["reused_session"] is True

        # Verify no jobs were created or queued
        jobs = db.get_jobs(limit=10)
        recent_test_jobs = [j for j in jobs if "test" in str(j.get("campaign_name", "")).lower() and j.get("created_at", "") > "2026"]
        assert len(recent_test_jobs) == 0
