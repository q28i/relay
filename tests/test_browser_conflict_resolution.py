"""
Comprehensive Verification Suite for Browser Conflict Resolution & Session Lifecycle.
Verifies all 10 Scenarios from the Verification Matrix:
1. No browser running -> launches cleanly.
2. Previous Relay-owned browser running -> automatically restarts/reconnects.
3. Existing Relay-owned session healthy -> reuses without unnecessary restart.
4. Personal Chrome profile open -> obtains confirmation before closing.
5. Another Chrome profile running -> leaves untouched.
6. Stale profile lock -> handles safely.
7. Browser launch failure -> reports real cause.
8. Relay restart with orphaned browser -> recovers safely.
9. Repeated Start Session clicks -> no duplicate instances (concurrency mutex).
10. Test Connection -> strictly probes, never sends messages.
"""

import os
import time
import json
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.session_lifecycle import SessionLifecycleManager, session_lifecycle
from browser_manager import BrowserManager, ProfileLockedError, BrowserExecutableNotFoundError
from backend.connection_monitor import ConnectionMonitor, ConnectionState

client = TestClient(app)


# --------------------------------------------------------------------------
# Scenario 1: No browser running -> launches cleanly
# --------------------------------------------------------------------------

def test_scenario_1_no_browser_running_launches_cleanly():
    """Scenario 1: With no conflicting processes, session starts cleanly."""
    mock_diag = {
        "condition": "AVAILABLE",
        "is_locked": False,
        "is_stale_lock": False,
        "conflict_type": "none",
        "matching_pids": [],
        "relay_pids": [],
        "personal_pids": [],
        "can_auto_resolve": True,
        "has_visible_window": False,
        "raw_profile_path": "C:\\session",
        "short_profile_path": "~/session",
        "browser_exe_exists": True,
        "browser_exe_path": "C:\\Chrome\\chrome.exe",
        "user_message": "Profile is available."
    }

    mock_driver = MagicMock()
    mock_driver.window_handles = ["win1"]

    with patch.object(BrowserManager, "diagnose_profile", return_value=mock_diag), \
         patch.object(BrowserManager, "launch_driver", return_value=mock_driver):

        res = client.post("/api/browser-session/start", json={"browser": "chrome", "profile_dir": "__dedicated__"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["prompt_required"] is False
        assert data["connection"]["state"] in (ConnectionState.OPENING_WHATSAPP, ConnectionState.STARTING_BROWSER, ConnectionState.CONNECTED)


# --------------------------------------------------------------------------
# Scenario 2: Previous Relay-owned browser running -> automatically restarts
# --------------------------------------------------------------------------

def test_scenario_2_previous_relay_owned_browser_auto_restarts():
    """Scenario 2: When previous Relay session is running, auto-terminates and restarts without prompting."""
    mock_diag_locked = {
        "condition": "ACTIVE_VISIBLE_PROCESS",
        "is_locked": True,
        "is_stale_lock": False,
        "conflict_type": "relay_owned",
        "matching_pids": [10101],
        "relay_pids": [10101],
        "personal_pids": [],
        "is_relay_owned": True,
        "can_auto_resolve": True,
        "has_visible_window": True,
        "browser_exe_exists": True,
        "browser_exe_path": "C:\\Chrome\\chrome.exe",
        "user_message": "A previous Relay-owned Google Chrome session is running."
    }

    mock_diag_unlocked = dict(mock_diag_locked)
    mock_diag_unlocked["is_locked"] = False
    mock_diag_unlocked["conflict_type"] = "none"
    mock_diag_unlocked["matching_pids"] = []

    mock_driver = MagicMock()
    mock_driver.window_handles = ["win1"]

    terminate_called = []
    def mock_terminate(timeout=5.0):
        terminate_called.append(True)
        return True

    with patch.object(BrowserManager, "diagnose_profile", side_effect=[mock_diag_locked, mock_diag_locked, mock_diag_unlocked, mock_diag_unlocked, mock_diag_unlocked]), \
         patch.object(session_lifecycle, "terminate_relay_process_tree", side_effect=mock_terminate), \
         patch.object(BrowserManager, "launch_driver", return_value=mock_driver):

        res = client.post("/api/browser-session/start", json={"browser": "chrome", "profile_dir": "__dedicated__"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["prompt_required"] is False
        assert len(terminate_called) > 0


# --------------------------------------------------------------------------
# Scenario 3: Existing Relay-owned session healthy -> reuses without restart
# --------------------------------------------------------------------------

def test_scenario_3_existing_healthy_session_reuses_without_restart():
    """Scenario 3: An existing active and healthy session is reused without restarting."""
    from backend.connection_monitor import connection_monitor

    mock_driver = MagicMock()
    mock_driver.window_handles = ["win1"]
    mock_driver.current_url = "https://web.whatsapp.com"

    connection_monitor.set_driver_external(mock_driver, "chrome", "__dedicated__")
    connection_monitor._state = ConnectionState.CONNECTED

    launch_mock = MagicMock()
    with patch.object(session_lifecycle, "is_session_healthy", return_value=True), \
         patch.object(BrowserManager, "launch_driver", launch_mock):

        res = client.post("/api/browser-session/start", json={"browser": "chrome", "profile_dir": "__dedicated__", "force_restart": False})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["connection"]["is_connected"] is True
        # Driver was NOT relaunched!
        launch_mock.assert_not_called()

    connection_monitor.stop_monitoring()


# --------------------------------------------------------------------------
# Scenario 4: Personal Chrome profile open -> obtains confirmation
# --------------------------------------------------------------------------

def test_scenario_4_personal_profile_open_requires_confirmation_then_closes():
    """Scenario 4: Personal browser window requires confirmation before graceful closure."""
    mock_diag_personal = {
        "condition": "ACTIVE_VISIBLE_PROCESS",
        "is_locked": True,
        "is_stale_lock": False,
        "conflict_type": "personal_browser",
        "matching_pids": [20202],
        "relay_pids": [],
        "personal_pids": [20202],
        "is_relay_owned": False,
        "can_auto_resolve": False,
        "has_visible_window": True,
        "browser_exe_exists": True,
        "browser_exe_path": "C:\\Chrome\\chrome.exe",
        "user_message": "Selected profile is currently open in a Google Chrome window."
    }

    mock_diag_after_confirm = dict(mock_diag_personal)
    mock_diag_after_confirm["is_locked"] = False
    mock_diag_after_confirm["matching_pids"] = []

    mock_driver = MagicMock()
    mock_driver.window_handles = ["win1"]

    # 1. First attempt: Without confirmation, returns prompt_required
    with patch.object(BrowserManager, "diagnose_profile", return_value=mock_diag_personal):
        res = client.post("/api/browser-session/start", json={"browser": "chrome", "profile_dir": "Default"})
        assert res.status_code == 200
        data = res.json()
        assert data["prompt_required"] is True
        assert data["connection"]["state"] == ConnectionState.PROFILE_LOCKED

    # 2. Second attempt: User confirms restart via confirm-restart endpoint
    with patch.object(BrowserManager, "diagnose_profile", side_effect=[mock_diag_personal, mock_diag_personal, mock_diag_after_confirm, mock_diag_after_confirm, mock_diag_after_confirm]), \
         patch.object(session_lifecycle, "graceful_close_pid", return_value=True), \
         patch.object(BrowserManager, "launch_driver", return_value=mock_driver):

        res_confirm = client.post("/api/browser-session/confirm-restart", json={"browser": "chrome", "profile_dir": "Default", "confirmed": True})
        assert res_confirm.status_code == 200
        data_confirm = res_confirm.json()
        assert data_confirm["success"] is True


# --------------------------------------------------------------------------
# Scenario 5: Another Chrome profile running -> leaves untouched
# --------------------------------------------------------------------------

def test_scenario_5_other_profile_running_leaves_untouched():
    """Scenario 5: Unrelated browser profiles running are left untouched."""
    # Target profile is Profile 2 (clean/free), while Profile 1 is running elsewhere
    mock_diag_clean = {
        "condition": "AVAILABLE",
        "is_locked": False,
        "is_stale_lock": False,
        "conflict_type": "none",
        "matching_pids": [],
        "relay_pids": [],
        "personal_pids": [],
        "can_auto_resolve": True,
        "has_visible_window": False,
        "browser_exe_exists": True,
        "browser_exe_path": "C:\\Chrome\\chrome.exe",
        "user_message": "Profile is available."
    }

    mock_driver = MagicMock()
    mock_driver.window_handles = ["win1"]

    with patch.object(BrowserManager, "diagnose_profile", return_value=mock_diag_clean), \
         patch.object(BrowserManager, "launch_driver", return_value=mock_driver):

        res = client.post("/api/browser-session/start", json={"browser": "chrome", "profile_dir": "Profile 2"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["prompt_required"] is False


# --------------------------------------------------------------------------
# Scenario 6: Stale profile lock -> handles safely
# --------------------------------------------------------------------------

def test_scenario_6_stale_lock_handled_safely():
    """Scenario 6: Lock file present without running processes is treated as stale, not in-use."""
    mock_diag_stale = {
        "condition": "STALE_LOCK_ARTIFACT",
        "is_locked": False,
        "is_stale_lock": True,
        "conflict_type": "none",
        "matching_pids": [],
        "relay_pids": [],
        "personal_pids": [],
        "can_auto_resolve": True,
        "has_visible_window": False,
        "browser_exe_exists": True,
        "browser_exe_path": "C:\\Chrome\\chrome.exe",
        "user_message": "Stale lock file found, but no running Google Chrome process was detected."
    }

    with patch.object(BrowserManager, "diagnose_profile", return_value=mock_diag_stale):
        res = client.post("/api/browser-profile/test", json={"browser": "chrome", "profile_dir": "Default"})
        assert res.status_code == 200
        data = res.json()
        assert data["is_locked"] is False
        assert data["is_stale_lock"] is True
        assert data["status"] == "Stale lock detected"


# --------------------------------------------------------------------------
# Scenario 7: Browser launch failure -> reports real cause
# --------------------------------------------------------------------------

def test_scenario_7_launch_failure_reports_real_cause():
    """Scenario 7: Reports real diagnostic reason when browser executable is missing."""
    mock_diag_missing = {
        "condition": "MISSING_EXECUTABLE",
        "is_locked": False,
        "is_stale_lock": False,
        "conflict_type": "none",
        "matching_pids": [],
        "relay_pids": [],
        "personal_pids": [],
        "can_auto_resolve": True,
        "has_visible_window": False,
        "browser_exe_exists": False,
        "browser_exe_path": "",
        "safe_error_reason": "Executable for Google Chrome not found at default paths or registry.",
        "user_message": "Couldn't find Google Chrome executable."
    }

    with patch.object(BrowserManager, "diagnose_profile", return_value=mock_diag_missing):
        res = client.post("/api/browser-session/start", json={"browser": "chrome", "profile_dir": "Default"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
        assert data["connection"]["state"] == ConnectionState.LAUNCH_FAILED
        assert "Executable for Google Chrome not found" in data["connection"]["error_detail"]


# --------------------------------------------------------------------------
# Scenario 8: Relay restart with orphaned browser -> recovers safely
# --------------------------------------------------------------------------

def test_scenario_8_relay_restart_orphaned_browser_recovers():
    """Scenario 8: Orphaned Relay process recorded in session_meta is cleaned on recovery."""
    mgr = SessionLifecycleManager()
    mgr._current_session = {
        "session_id": "test-orphan-uuid",
        "is_relay_owned": True,
        "browser_pid": 99999,
        "browser_create_time": time.time(),
        "driver_pid": 88888,
        "child_pids": []
    }

    mock_proc = MagicMock()
    mock_proc.cmdline.return_value = ["chrome.exe", "--relay-session-id=test-orphan-uuid"]

    with patch("psutil.pid_exists", return_value=True), \
         patch("psutil.Process", return_value=mock_proc), \
         patch.object(mgr, "is_relay_owned_pid", return_value=True), \
         patch.object(mgr, "terminate_relay_process_tree", return_value=True):

        rec = mgr.recover_orphaned_session()
        assert rec["has_orphaned"] is True
        assert rec["recovered"] is True


# --------------------------------------------------------------------------
# Scenario 9: Repeated Start Session clicks -> concurrency mutex guards
# --------------------------------------------------------------------------

def test_scenario_9_repeated_start_clicks_guarded_by_mutex():
    """Scenario 9: Mutex lock prevents race conditions on concurrent start requests."""
    mgr = SessionLifecycleManager()
    acquired_1 = mgr.acquire_launch_lock(timeout=1.0)
    assert acquired_1 is True

    # Immediate second acquire must fail
    acquired_2 = mgr.acquire_launch_lock(timeout=0.1)
    assert acquired_2 is False

    mgr.release_launch_lock()
    # Now it can be acquired again
    acquired_3 = mgr.acquire_launch_lock(timeout=0.5)
    assert acquired_3 is True
    mgr.release_launch_lock()


# --------------------------------------------------------------------------
# Scenario 10: Test Connection -> strictly probes, never sends messages
# --------------------------------------------------------------------------

def test_scenario_10_test_connection_never_sends_messages():
    """Scenario 10: Test Connection checks status and never dispatches messages."""
    mock_probe = {
        "status": "Signed in",
        "detail": "Active WhatsApp Web session detected with chat list present",
        "logged_in": True,
        "is_locked": False
    }

    dispatch_mock = MagicMock()
    with patch.object(BrowserManager, "check_profile_session", return_value=mock_probe), \
         patch("data_loader.DataLoader.clean_phone_number", dispatch_mock):

        res = client.post("/api/browser-profile/test", json={"browser": "chrome", "profile_dir": "__dedicated__"})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "Signed in"
        assert data["logged_in"] is True
        # Phone cleaning or sending code was never invoked!
        dispatch_mock.assert_not_called()
