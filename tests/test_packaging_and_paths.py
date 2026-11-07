"""
Unit and integration tests for Relay desktop packaging, runtime path resolution,
and the GitHub self-update engine.
"""

import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.paths import (
    is_frozen,
    get_bundle_dir,
    get_user_data_dir,
    get_db_path,
    get_media_dir,
    get_session_dir,
    get_config_path,
    get_static_dir,
    get_logs_dir,
    ensure_data_dirs,
    migrate_legacy_data_if_needed,
)
from backend.updater_service import (
    parse_semver,
    RelayUpdaterService,
    CURRENT_VERSION,
)
from backend.app import app


@pytest.fixture
def client():
    return TestClient(app)


class TestPathResolution:
    """Verifies strict separation of bundle files from persistent user data."""

    def test_default_dev_paths(self):
        assert is_frozen() is False
        bundle = get_bundle_dir()
        assert os.path.isdir(bundle)
        assert os.path.exists(os.path.join(bundle, "backend"))

        # In dev mode without env overrides, user data defaults to repo root
        user_data = get_user_data_dir()
        assert user_data == bundle

    def test_override_user_data_dir(self, tmp_path):
        custom_dir = str(tmp_path / "CustomRelayData")
        # Temporarily clear RELAY_DB_PATH and RELAY_MEDIA_DIR so get_db_path uses user data dir
        with patch.dict(os.environ, {
            "RELAY_USER_DATA_DIR": custom_dir,
            "RELAY_DB_PATH": "",
            "RELAY_MEDIA_DIR": ""
        }):
            assert get_user_data_dir() == os.path.abspath(custom_dir)
            assert get_db_path() == os.path.join(custom_dir, "whatsapp_web.db")
            assert get_media_dir() == os.path.join(custom_dir, "uploads", "media")
            assert get_session_dir() == os.path.join(custom_dir, "whatsapp_browser_session")
            assert get_config_path() == os.path.join(custom_dir, "config.json")
            assert get_logs_dir() == os.path.join(custom_dir, "logs")

            ensure_data_dirs()
            assert os.path.isdir(custom_dir)
            assert os.path.isdir(os.path.join(custom_dir, "uploads", "media"))
            assert os.path.isdir(os.path.join(custom_dir, "whatsapp_browser_session"))
            assert os.path.isdir(os.path.join(custom_dir, "logs"))

    def test_legacy_data_migration(self, tmp_path):
        source_dir = tmp_path / "legacy_source"
        target_dir = tmp_path / "isolated_target"
        source_dir.mkdir()
        target_dir.mkdir()

        # Create dummy source files
        (source_dir / "whatsapp_web.db").write_text("dummy-sqlite-content", encoding="utf-8")
        (source_dir / "config.json").write_text("{\"key\": \"val\"}", encoding="utf-8")
        legacy_session = source_dir / "whatsapp_browser_session"
        legacy_session.mkdir()
        (legacy_session / "session.txt").write_text("session-data", encoding="utf-8")

        with patch.dict(os.environ, {"RELAY_USER_DATA_DIR": str(target_dir)}):
            migrate_legacy_data_if_needed(str(source_dir))

            assert os.path.exists(os.path.join(str(target_dir), "whatsapp_web.db"))
            assert os.path.exists(os.path.join(str(target_dir), "config.json"))
            assert os.path.exists(os.path.join(str(target_dir), "whatsapp_browser_session", "session.txt"))


class TestUpdaterService:
    """Verifies semantic versioning, GitHub Release parsing, and update flow."""

    def test_parse_semver(self):
        assert parse_semver("2.0.0") == (2, 0, 0)
        assert parse_semver("v2.0.0") == (2, 0, 0)
        assert parse_semver("V2.1.4") == (2, 1, 4)
        assert parse_semver("3.0.0-rc1") == (3, 0, 0)
        assert parse_semver("invalid") == (0, 0, 0)

    def test_semver_comparison(self):
        v200 = parse_semver("2.0.0")
        v201 = parse_semver("2.0.1")
        v210 = parse_semver("2.1.0")
        v300 = parse_semver("3.0.0")

        assert v201 > v200
        assert v210 > v201
        assert v300 > v210
        assert not (v200 > v200)

    @patch("urllib.request.urlopen")
    def test_check_for_updates_available(self, mock_urlopen, tmp_path):
        service = RelayUpdaterService(repo="q28i/relay")
        mock_response = MagicMock()
        mock_response.status = 200
        mock_payload = {
            "tag_name": "v2.1.0",
            "name": "Relay v2.1.0 Release",
            "body": "Fixed all edge cases.",
            "published_at": "2026-11-08T00:00:00Z",
            "assets": [
                {
                    "name": "Relay-Setup-v2.1.0-Windows-x64.exe",
                    "browser_download_url": "https://github.com/q28i/relay/releases/download/v2.1.0/Relay-Setup-v2.1.0-Windows-x64.exe",
                    "size": 52428800
                },
                {
                    "name": "SHA256SUMS.txt",
                    "browser_download_url": "https://github.com/q28i/relay/releases/download/v2.1.0/SHA256SUMS.txt",
                    "size": 128
                }
            ]
        }
        mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        with patch.dict(os.environ, {"RELAY_USER_DATA_DIR": str(tmp_path)}):
            res = service.check_for_updates()
            assert res["has_update"] is True
            assert res["tag_name"] == "v2.1.0"
            assert res["installer_name"] == "Relay-Setup-v2.1.0-Windows-x64.exe"
            assert res["installer_size"] == 52428800

    @patch("urllib.request.urlopen")
    def test_check_for_updates_already_latest(self, mock_urlopen, tmp_path):
        service = RelayUpdaterService(repo="q28i/relay")
        mock_response = MagicMock()
        mock_response.status = 200
        mock_payload = {
            "tag_name": "v2.0.0",
            "name": "Relay v2.0.0",
            "body": "Initial release.",
            "assets": []
        }
        mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        with patch.dict(os.environ, {"RELAY_USER_DATA_DIR": str(tmp_path)}):
            res = service.check_for_updates()
            assert res["has_update"] is False

    def test_active_campaign_blocks_update(self):
        service = RelayUpdaterService(repo="q28i/relay")
        from backend.job_queue import job_worker

        # Mock an active campaign
        with patch.object(job_worker, "get_active_job", return_value={"id": "job-1", "status": "running"}):
            with patch.object(service, "_downloaded_installer", "C:\\fake\\installer.exe"):
                with patch("os.path.isfile", return_value=True):
                    success, msg = service.trigger_update_installer()
                    assert success is False
                    assert "campaign is dispatching" in msg


class TestUpdateApiEndpoints:
    """Tests FastAPI router endpoints for updates."""

    def test_get_status(self, client):
        resp = client.get("/api/updates/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_version"] == CURRENT_VERSION
        assert "is_frozen" in data
        assert "repo" in data

    @patch("backend.updater_service.relay_updater.check_for_updates")
    def test_check_endpoint(self, mock_check, client):
        mock_check.return_value = {
            "has_update": True,
            "tag_name": "v2.1.0",
            "release_notes": "Note"
        }
        resp = client.post("/api/updates/check")
        assert resp.status_code == 200
        assert resp.json()["has_update"] is True

    def test_apply_endpoint_rejected_when_campaign_active(self, client):
        from backend.job_queue import job_worker
        with patch.object(job_worker, "get_active_job", return_value={"id": "job-1", "status": "running"}):
            resp = client.post("/api/updates/apply", json={"silent": False})
            assert resp.status_code == 409
            assert "actively dispatching" in resp.json()["detail"]
