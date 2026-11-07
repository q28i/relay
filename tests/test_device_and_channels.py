"""
Comprehensive Unit & Integration Tests for Relay Device Identity,
System Diagnostics, Update Channels, and Targeted Developer Rollouts.
"""

import os
import re
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.device_identity import (
    DeviceIdentityManager,
    generate_installation_id,
    is_valid_installation_id,
    UUIDV4_RELAY_PATTERN,
)
from backend.updater_service import (
    SemVer,
    RelayUpdaterService,
    CURRENT_VERSION,
)
from backend.app import app


@pytest.fixture
def temp_identity_env(tmp_path):
    """Provides an isolated environment for testing DeviceIdentityManager."""
    with patch.dict(os.environ, {"RELAY_USER_DATA_DIR": str(tmp_path)}):
        mgr = DeviceIdentityManager()
        yield mgr, tmp_path


@pytest.fixture
def api_client():
    return TestClient(app)


# =============================================================================
# 1. Persistent Installation ID & File Safety Tests
# =============================================================================

def test_installation_id_format():
    """Generates a valid UUIDv4-based Relay Installation ID."""
    new_id = generate_installation_id()
    assert is_valid_installation_id(new_id)
    assert new_id.startswith("relay-")
    assert re.match(UUIDV4_RELAY_PATTERN, new_id)


def test_installation_id_persistence_and_atomic_write(temp_identity_env):
    """Verifies that the installation ID is created atomically and survives reloads."""
    mgr, tmp_path = temp_identity_env
    id_file = os.path.join(str(tmp_path), "device_identity.json")

    assert not os.path.exists(id_file)
    ident = mgr.get_device_identity()
    first_id = ident["installation_id"]

    assert os.path.isfile(id_file)
    assert is_valid_installation_id(first_id)

    # Simulate fresh manager instance on app restart
    new_mgr = DeviceIdentityManager()
    second_ident = new_mgr.get_device_identity()
    assert second_ident["installation_id"] == first_id
    assert second_ident["created_at"] == ident["created_at"]


def test_corrupted_identity_file_recovery(temp_identity_env):
    """Recovers safely by regenerating a new ID if identity JSON is malformed."""
    mgr, tmp_path = temp_identity_env
    id_file = os.path.join(str(tmp_path), "device_identity.json")

    # Write corrupt JSON to disk
    with open(id_file, "w", encoding="utf-8") as f:
        f.write("{ invalid json corrupted content ")

    ident = mgr.get_device_identity()
    assert is_valid_installation_id(ident["installation_id"])
    assert ident["device_role"] == "standard"


def test_invalid_uuid_format_recovery(temp_identity_env):
    """Recovers safely if installation_id on disk does not follow UUIDv4 format."""
    mgr, tmp_path = temp_identity_env
    id_file = os.path.join(str(tmp_path), "device_identity.json")

    bad_data = {
        "schema_version": 1,
        "installation_id": "not-a-valid-uuid",
        "device_role": "standard"
    }
    with open(id_file, "w", encoding="utf-8") as f:
        json.dump(bad_data, f)

    ident = mgr.get_device_identity()
    assert is_valid_installation_id(ident["installation_id"])


def test_explicit_reset_identity(temp_identity_env):
    """Explicit reset generates a completely new Installation ID."""
    mgr, _ = temp_identity_env
    id_1 = mgr.get_device_identity()["installation_id"]

    mgr.set_device_label("Old Workstation")
    mgr.register_as_developer(label="Dev Workstation")

    reset_ident = mgr.reset_device_identity()
    id_2 = reset_ident["installation_id"]

    assert id_1 != id_2
    assert is_valid_installation_id(id_2)
    assert reset_ident["device_role"] == "standard"
    assert reset_ident["update_channel"] == "stable"


# =============================================================================
# 2. Local Device Hardware & Diagnostics Gathering
# =============================================================================

def test_system_info_collection(temp_identity_env):
    """Queries local OS and hardware specifications without crashing."""
    mgr, _ = temp_identity_env
    sys_info = mgr.get_system_info()

    assert "os_name" in sys_info
    assert "cpu_arch" in sys_info
    assert "cpu_logical_cores" in sys_info
    assert sys_info["cpu_logical_cores"] >= 1
    assert "total_ram_gb" in sys_info
    assert "free_disk_gb" in sys_info
    assert "locale" in sys_info
    assert "timezone" in sys_info


def test_application_info_collection(temp_identity_env):
    """Collects application execution mode, directories, and elevation status."""
    mgr, _ = temp_identity_env
    app_info = mgr.get_application_info()

    assert app_info["version"] == CURRENT_VERSION
    assert "execution_mode" in app_info
    assert "bundle_dir" in app_info
    assert "user_data_dir" in app_info
    assert "pid" in app_info
    assert "elevation" in app_info


def test_browser_environment_detection(temp_identity_env):
    """Detects installed browsers and active session state safely."""
    mgr, _ = temp_identity_env
    browser_env = mgr.get_browser_environment()

    assert "installed_browsers" in browser_env
    assert "session_dir" in browser_env
    assert "active_session" in browser_env


# =============================================================================
# 3. Privacy-Aware Redaction in Diagnostics
# =============================================================================

def test_diagnostics_report_redaction(temp_identity_env):
    """Redacts username, hostname, and path components when redact=True."""
    mgr, _ = temp_identity_env
    mgr.register_as_developer(label="Workstation-A", token="secret-token-12345")

    unredacted = mgr.get_diagnostics_report(redact=False)
    assert unredacted["privacy_redacted"] is False
    assert unredacted["identity"]["local_username"] != "[REDACTED_USER]"
    assert unredacted["identity"]["machine_name"] != "[REDACTED_HOST]"

    redacted = mgr.get_diagnostics_report(redact=True)
    assert redacted["privacy_redacted"] is True
    assert redacted["identity"]["local_username"] == "[REDACTED_USER]"
    assert redacted["identity"]["machine_name"] == "[REDACTED_HOST]"

    # Verify no sensitive campaign or contact fields exist
    report_json = mgr.export_diagnostics_json(redact=True)
    assert "contacts" not in report_json
    assert "messages" not in report_json
    assert "secret-token-12345" not in report_json


# =============================================================================
# 4. Developer Device Registration & Channel Preferences
# =============================================================================

def test_developer_registration_workflow(temp_identity_env):
    """Enrolls local device as Developer workstation and verifies persistence."""
    mgr, _ = temp_identity_env
    initial = mgr.get_device_identity()
    assert initial["device_role"] == "standard"
    assert initial["update_channel"] == "stable"

    enrolled = mgr.register_as_developer(
        label="Primary Development Workstation",
        token="dev-auth-key-test",
        channel="dev"
    )
    assert enrolled["device_role"] == "developer"
    assert enrolled["update_channel"] == "dev"
    assert enrolled["device_label"] == "Primary Development Workstation"
    assert enrolled["developer_enrolled_at"] is not None

    # Survives restart
    new_mgr = DeviceIdentityManager()
    reloaded = new_mgr.get_device_identity()
    assert reloaded["device_role"] == "developer"
    assert reloaded["update_channel"] == "dev"

    # Revert to standard
    unregistered = mgr.unregister_developer()
    assert unregistered["device_role"] == "standard"
    assert unregistered["update_channel"] == "stable"
    assert unregistered["developer_enrolled_at"] is None


def test_channel_switching_validation(temp_identity_env):
    """Validates allowed update channels and rejects invalid channel names."""
    mgr, _ = temp_identity_env
    mgr.set_update_channel("beta")
    assert mgr.get_device_identity()["update_channel"] == "beta"

    mgr.set_update_channel("dev")
    assert mgr.get_device_identity()["update_channel"] == "dev"

    mgr.set_update_channel("stable")
    assert mgr.get_device_identity()["update_channel"] == "stable"

    with pytest.raises(ValueError):
        mgr.set_update_channel("invalid_channel")


# =============================================================================
# 5. SemVer 2.0.0 & Channel Precedence Model
# =============================================================================

def test_semver_precedence_model():
    """Validates SemVer 2.0.0 channel comparison rules."""
    v200 = SemVer.parse("v2.0.0")
    v210_dev1 = SemVer.parse("v2.1.0-dev.1")
    v210_dev2 = SemVer.parse("v2.1.0-dev.2")
    v210_beta1 = SemVer.parse("v2.1.0-beta.1")
    v210_beta2 = SemVer.parse("v2.1.0-beta.2")
    v210_rc1 = SemVer.parse("v2.1.0-rc.1")
    v210_stable = SemVer.parse("v2.1.0")

    # Higher base version precedes lower version regardless of prerelease tag
    assert v210_dev1 > v200
    # Prerelease numeric increment
    assert v210_dev2 > v210_dev1
    # Channel hierarchy: dev < beta < rc < stable
    assert v210_beta1 > v210_dev2
    assert v210_beta2 > v210_beta1
    assert v210_rc1 > v210_beta2
    assert v210_stable > v210_rc1


def test_semver_channel_classification():
    assert SemVer.parse("2.0.0").get_channel() == "stable"
    assert SemVer.parse("2.1.0-rc.1").get_channel() == "beta"
    assert SemVer.parse("2.1.0-beta.2").get_channel() == "beta"
    assert SemVer.parse("2.1.0-dev.1").get_channel() == "dev"
    assert SemVer.parse("2.1.0-alpha.3").get_channel() == "dev"


# =============================================================================
# 6. Updater Channel Filtering & Targeted Rollout Tests
# =============================================================================

def test_updater_channel_filtering(temp_identity_env):
    """Verifies that release streams are correctly partitioned by channel."""
    updater = RelayUpdaterService()

    fake_releases = [
        {
            "tag_name": "v2.1.0-dev.1",
            "prerelease": True,
            "draft": False,
            "body": "Dev experimental build",
            "assets": [{"name": "Relay-Setup-2.1.0-dev.1.exe", "browser_download_url": "http://example.com/dev.exe", "size": 100}]
        },
        {
            "tag_name": "v2.1.0-beta.1",
            "prerelease": True,
            "draft": False,
            "body": "Beta preview build",
            "assets": [{"name": "Relay-Setup-2.1.0-beta.1.exe", "browser_download_url": "http://example.com/beta.exe", "size": 100}]
        },
        {
            "tag_name": "v2.0.0",
            "prerelease": False,
            "draft": False,
            "body": "Current stable release",
            "assets": [{"name": "Relay-Setup-2.0.0.exe", "browser_download_url": "http://example.com/stable.exe", "size": 100}]
        }
    ]

    with patch.object(updater, "_get_auth_headers", return_value={}):
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = json.dumps(fake_releases).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_url.return_value = mock_resp

            # 1. Stable channel check: should only see stable v2.0.0 (has_update=False since current is 2.0.0)
            stable_res = updater.check_for_updates(channel="stable")
            assert stable_res["has_update"] is False
            assert stable_res["tag_name"] == "v2.0.0"

            # 2. Beta channel check: should see v2.1.0-beta.1 as update
            beta_res = updater.check_for_updates(channel="beta")
            assert beta_res["has_update"] is True
            assert beta_res["tag_name"] == "v2.1.0-beta.1"
            assert beta_res["release_channel"] == "beta"

            # 3. Dev channel check: should see highest release v2.1.0-dev.1 as update (or v2.1.0-beta.1 if beta > dev)
            # In SemVer, beta > dev, so v2.1.0-beta.1 is selected
            dev_res = updater.check_for_updates(channel="dev")
            assert dev_res["has_update"] is True
            assert dev_res["tag_name"] == "v2.1.0-beta.1"


def test_targeted_device_rollout_filtering(temp_identity_env):
    """Verifies that releases with embedded target_devices only match designated installations."""
    mgr, _ = temp_identity_env
    target_id = mgr.get_device_identity()["installation_id"]
    updater = RelayUpdaterService()

    fake_releases = [
        {
            "tag_name": "v2.2.0-dev.targeted",
            "prerelease": True,
            "draft": False,
            "body": f"Developer experimental build <!-- target_devices: [\"{target_id}\"] -->",
            "assets": [{"name": "Relay-Setup-dev.exe", "browser_download_url": "http://example.com/dev.exe", "size": 100}]
        },
        {
            "tag_name": "v2.0.0",
            "prerelease": False,
            "draft": False,
            "body": "Stable",
            "assets": [{"name": "Relay-Setup-2.0.0.exe", "browser_download_url": "http://example.com/stable.exe", "size": 100}]
        }
    ]

    with patch("backend.device_identity.device_identity_manager.get_device_identity", return_value=mgr.get_device_identity()):
        with patch.object(updater, "_get_auth_headers", return_value={}):
            with patch("urllib.request.urlopen") as mock_url:
                mock_resp = MagicMock()
                mock_resp.status = 200
                mock_resp.read.return_value = json.dumps(fake_releases).encode("utf-8")
                mock_resp.__enter__.return_value = mock_resp
                mock_url.return_value = mock_resp

                # Matched installation receives update
                res = updater.check_for_updates(channel="dev")
                assert res["has_update"] is True
                assert res["tag_name"] == "v2.2.0-dev.targeted"

    # Now test with another installation ID that does NOT match
    fake_releases_other = [
        {
            "tag_name": "v2.2.0-dev.targeted",
            "prerelease": True,
            "draft": False,
            "body": "Developer experimental build <!-- target_devices: [\"relay-other-device-id\"] -->",
            "assets": [{"name": "Relay-Setup-dev.exe", "browser_download_url": "http://example.com/dev.exe", "size": 100}]
        },
        {
            "tag_name": "v2.0.0",
            "prerelease": False,
            "draft": False,
            "body": "Stable",
            "assets": [{"name": "Relay-Setup-2.0.0.exe", "browser_download_url": "http://example.com/stable.exe", "size": 100}]
        }
    ]
    with patch("backend.device_identity.device_identity_manager.get_device_identity", return_value=mgr.get_device_identity()):
        with patch.object(updater, "_get_auth_headers", return_value={}):
            with patch("urllib.request.urlopen") as mock_url:
                mock_resp = MagicMock()
                mock_resp.status = 200
                mock_resp.read.return_value = json.dumps(fake_releases_other).encode("utf-8")
                mock_resp.__enter__.return_value = mock_resp
                mock_url.return_value = mock_resp

                # Unmatched installation does NOT receive update
                res = updater.check_for_updates(channel="dev")
                assert res["has_update"] is False
                assert res["tag_name"] == "v2.0.0"


# =============================================================================
# 7. Update Safety Guards (Memory & SQLite Campaign Protection)
# =============================================================================

def test_update_blocked_during_in_memory_campaign(tmp_path):
    """Installer trigger is blocked when in-memory JobWorker has an active job."""
    updater = RelayUpdaterService()
    installer_path = str(tmp_path / "Relay-Setup.exe")
    with open(installer_path, "wb") as f:
        f.write(b"dummy installer binary")
    updater._downloaded_installer = installer_path

    with patch("backend.job_queue.job_worker.get_active_job", return_value={"id": "job-123"}):
        success, msg = updater.trigger_update_installer()
        assert success is False
        assert "Cannot install update while an active WhatsApp campaign is dispatching" in msg


def test_update_blocked_during_paused_sqlite_campaign(tmp_path):
    """Installer trigger is blocked when SQLite has an active or paused campaign."""
    updater = RelayUpdaterService()
    installer_path = str(tmp_path / "Relay-Setup.exe")
    with open(installer_path, "wb") as f:
        f.write(b"dummy installer binary")
    updater._downloaded_installer = installer_path

    # In-memory worker is idle, but database has a paused job
    with patch("backend.job_queue.job_worker.get_active_job", return_value=None):
        with patch("backend.database.db.get_connection") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [("job-paused-001", "Black Friday Campaign", "PAUSED")]
            mock_conn.return_value.__enter__.return_value.cursor.return_value = mock_cursor

            success, msg = updater.trigger_update_installer()
            assert success is False
            assert "Cannot install update: found 1 active, paused, or queued campaign" in msg


# =============================================================================
# 8. Device REST API Endpoint Integration Tests
# =============================================================================

def test_api_device_info(api_client):
    r = api_client.get("/api/device/info")
    assert r.status_code == 200
    data = r.json()
    assert "identity" in data
    assert is_valid_installation_id(data["identity"]["installation_id"])
    assert "system" in data
    assert "application" in data
    assert "browser" in data


def test_api_device_label_update(api_client):
    r = api_client.post("/api/device/label", json={"label": "New Office Workstation"})
    assert r.status_code == 200
    assert r.json()["identity"]["device_label"] == "New Office Workstation"

    # Empty label rejected
    r_empty = api_client.post("/api/device/label", json={"label": "   "})
    assert r_empty.status_code == 400


def test_api_device_channel_update(api_client):
    r = api_client.post("/api/device/channel", json={"channel": "beta"})
    assert r.status_code == 200
    assert r.json()["identity"]["update_channel"] == "beta"

    r_bad = api_client.post("/api/device/channel", json={"channel": "nightly"})
    assert r_bad.status_code == 400


def test_api_developer_registration_and_unregistration(api_client):
    r_reg = api_client.post(
        "/api/device/register-developer",
        json={"label": "Primary Development Workstation", "channel": "dev"}
    )
    assert r_reg.status_code == 200
    assert r_reg.json()["identity"]["device_role"] == "developer"
    assert r_reg.json()["identity"]["update_channel"] == "dev"

    r_unreg = api_client.post("/api/device/unregister-developer")
    assert r_unreg.status_code == 200
    assert r_unreg.json()["identity"]["device_role"] == "standard"
    assert r_unreg.json()["identity"]["update_channel"] == "stable"


def test_api_reset_identity(api_client):
    # Without confirmation
    r_fail = api_client.post("/api/device/reset-identity", json={"confirm": False})
    assert r_fail.status_code == 400

    # With confirmation
    r_ok = api_client.post("/api/device/reset-identity", json={"confirm": True})
    assert r_ok.status_code == 200
    assert is_valid_installation_id(r_ok.json()["identity"]["installation_id"])


def test_api_diagnostics_export(api_client):
    r_redacted = api_client.get("/api/device/diagnostics?redact=true")
    assert r_redacted.status_code == 200
    data = r_redacted.json()
    assert data["privacy_redacted"] is True
    assert data["identity"]["local_username"] == "[REDACTED_USER]"

    # Test download format
    r_dl = api_client.get("/api/device/diagnostics?redact=true&download=true")
    assert r_dl.status_code == 200
    assert "attachment" in r_dl.headers.get("Content-Disposition", "")
