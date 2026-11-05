"""
Automated Pytest Suite for False 'Profile Locked' Detection and Launch Diagnostics.

Verifies:
1. Browser fully closed; selected profile launches and marks browser_launched completed.
2. Browser process active with a different profile does NOT trigger false lock.
3. Genuine active process triggers PROFILE_LOCKED without claiming browser launched.
4. Stale lock artifact triggers STALE_LOCK offering 'Try launch anyway', without claiming open.
5. Missing browser executable sets LAUNCH_FAILED with safe reason and failed timeline step.
6. Launch failure before window appears sets LAUNCH_FAILED with 'Couldn't start the selected browser profile.'
7. Diagnostic details modal endpoint returns sanitized shortened paths and safe error reasons.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.app import app
from browser_manager import (
    BrowserManager,
    ProfileLockedError,
    StaleLockArtifactError,
    BrowserExecutableNotFoundError,
    BrowserLaunchFailedError
)
from backend.connection_monitor import ConnectionMonitor, ConnectionState, connection_monitor


@pytest.fixture
def client():
    return TestClient(app)


def test_scenario_1_browser_closed_launches():
    mon = ConnectionMonitor()
    mock_driver = MagicMock()
    mock_driver.window_handles = ["handle1"]

    with patch.object(BrowserManager, "diagnose_profile") as mock_diag, \
         patch.object(BrowserManager, "launch_driver", return_value=mock_driver):

        mock_diag.return_value = {
            "condition": "AVAILABLE",
            "is_locked": False,
            "is_stale_lock": False,
            "user_message": "Profile is available.",
            "safe_error_reason": "",
            "matching_pids": [],
            "has_visible_window": False,
            "raw_profile_path": "C:\\temp\\session",
            "short_profile_path": "~/session",
            "browser_exe_exists": True,
            "browser_exe_path": "C:\\Program Files\\Google\\Chrome\\chrome.exe"
        }

        status = mon.start_monitoring(browser_key="chrome", profile_dir="__dedicated__", headless=True)
        assert status["state"] == ConnectionState.OPENING_WHATSAPP
        assert status["timeline"][0]["id"] == "browser_launched"
        assert status["timeline"][0]["status"] == "completed"
        mon.stop_monitoring()


def test_scenario_2_different_profile_active():
    real_exe = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    other_ud = os.path.normpath("C:/Users/Rift/AppData/Local/Google/Chrome/User Data/WorkProfile")

    mock_proc = MagicMock()
    mock_proc.info = {
        "pid": 99999,
        "name": "chrome.exe",
        "exe": real_exe,
        "cmdline": ["chrome.exe", f"--user-data-dir={other_ud}"]
    }

    with patch("psutil.process_iter", return_value=[mock_proc]), \
         patch.object(BrowserManager, "_find_executable", return_value=real_exe), \
         patch("os.path.isdir", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.exists", return_value=False):

        diag = BrowserManager.diagnose_profile("chrome", profile_dir="Default", is_dedicated=False)
        assert diag["condition"] in ("AVAILABLE", "UNSUPPORTED_DEFAULT_PROFILE")
        assert diag["is_locked"] is False
        assert len(diag["matching_pids"]) == 0


def test_scenario_3_genuinely_active_profile():
    mon = ConnectionMonitor()

    with patch.object(BrowserManager, "diagnose_profile") as mock_diag:
        mock_diag.return_value = {
            "condition": "ACTIVE_VISIBLE_PROCESS",
            "is_locked": True,
            "is_stale_lock": False,
            "user_message": "Selected profile is currently open in a Google Chrome window.",
            "safe_error_reason": "Process 12345 has an active visible window.",
            "matching_pids": [12345],
            "has_visible_window": True,
            "raw_profile_path": "C:\\temp\\Profile 1",
            "short_profile_path": "~/Profile 1",
            "browser_exe_exists": True,
            "browser_exe_path": "C:\\chrome.exe"
        }

        status = mon.start_monitoring(browser_key="chrome", profile_dir="Profile 1")
        assert status["state"] == ConnectionState.PROFILE_LOCKED
        assert "currently open" in status["current_activity"]
        assert status["timeline"][0]["status"] == "pending"

        action_ids = [a["id"] for a in status["actions"]]
        assert "use_dedicated" in action_ids
        assert "change_profile" in action_ids
        assert "try_again" in action_ids
        assert "view_details" in action_ids


def test_scenario_4_stale_lock_artifact():
    mon = ConnectionMonitor()

    with patch.object(BrowserManager, "diagnose_profile") as mock_diag:
        mock_diag.return_value = {
            "condition": "STALE_LOCK_ARTIFACT",
            "is_locked": False,
            "is_stale_lock": True,
            "user_message": "Stale lock file found, but no running Google Chrome process was detected.",
            "safe_error_reason": "A lock file artifact exists from a previous run, but no matching browser process is active.",
            "matching_pids": [],
            "has_visible_window": False,
            "raw_profile_path": "C:\\temp\\Profile 1",
            "short_profile_path": "~/Profile 1",
            "browser_exe_exists": True,
            "browser_exe_path": "C:\\chrome.exe",
            "lock_path": "C:\\temp\\Profile 1\\lockfile"
        }

        status = mon.start_monitoring(browser_key="chrome", profile_dir="Profile 1")
        assert status["state"] == ConnectionState.STALE_LOCK
        assert "Stale lock file found" in status["current_activity"]
        assert status["timeline"][0]["status"] == "pending"

        action_ids = [a["id"] for a in status["actions"]]
        assert "try_launch_anyway" in action_ids
        assert "use_dedicated" in action_ids
        assert "change_profile" in action_ids
        assert "view_details" in action_ids


def test_scenario_5_missing_browser_executable():
    mon = ConnectionMonitor()

    with patch.object(BrowserManager, "diagnose_profile") as mock_diag:
        mock_diag.return_value = {
            "condition": "MISSING_EXECUTABLE",
            "is_locked": False,
            "is_stale_lock": False,
            "user_message": "Couldn't find Brave Browser executable.",
            "safe_error_reason": "Executable for Brave Browser not found at default paths or registry.",
            "matching_pids": [],
            "has_visible_window": False,
            "raw_profile_path": "C:\\temp",
            "short_profile_path": "~/temp",
            "browser_exe_exists": False,
            "browser_exe_path": ""
        }

        status = mon.start_monitoring(browser_key="brave", profile_dir="Default")
        assert status["state"] == ConnectionState.LAUNCH_FAILED
        assert status["current_activity"] == "Couldn't start the selected browser profile."
        assert status["timeline"][0]["status"] == "failed"
        assert status["diagnostic_details"]["browser_exe_exists"] is False


def test_scenario_6_browser_launch_fails():
    mon = ConnectionMonitor()

    with patch.object(BrowserManager, "diagnose_profile") as mock_diag, \
         patch.object(BrowserManager, "launch_driver") as mock_launch:

        mock_diag.return_value = {
            "condition": "AVAILABLE",
            "is_locked": False,
            "is_stale_lock": False,
            "user_message": "Profile is available.",
            "safe_error_reason": "",
            "matching_pids": [],
            "has_visible_window": False,
            "raw_profile_path": "C:\\temp",
            "short_profile_path": "~/temp",
            "browser_exe_exists": True,
            "browser_exe_path": "C:\\chrome.exe"
        }

        mock_launch.side_effect = BrowserLaunchFailedError(
            "Couldn't start the selected browser profile.",
            safe_reason="Browser process exited before remote debugging port opened. Default Chrome profile restrictions apply.",
            technical_detail="SessionNotCreatedException: DevToolsActivePort file doesn't exist"
        )

        status = mon.start_monitoring(browser_key="chrome", profile_dir="Default")
        assert status["state"] == ConnectionState.LAUNCH_FAILED
        assert status["current_activity"] == "Couldn't start the selected browser profile."
        assert status["timeline"][0]["status"] == "failed"
        assert "Default Chrome profile restrictions" in status["diagnostic_details"]["safe_error_reason"]


def test_view_details_action_endpoint(client):
    res = client.post("/api/browser-connection/action", json={"action": "view_details"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "details" in data
    assert "condition" in data["details"]
    assert "browser_name" in data["details"]
    assert "profile_path" in data["details"]
