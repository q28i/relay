"""
Unit & Integration Test Suite for Relay Cloud Edition & WhatsApp Phone Pairing.

Covers:
1. Cross-platform Linux / POSIX browser manager and device manager fallbacks.
2. Cloud Authentication Middleware (Tailscale header auth, Bearer tokens, Cookie sessions, Whitelists).
3. WhatsApp Phone Number Pairing Manager & REST Endpoints (/api/whatsapp/pair-phone, /pair-status, /pair-cancel).
"""

import os
import sys
import time
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from backend.app import app
from backend.auth_middleware import (
    is_auth_enabled,
    create_session,
    validate_session,
    destroy_session,
    get_allowed_tailscale_users
)
from backend.whatsapp_pairing import whatsapp_pairing, WhatsAppPairingManager
from browser_manager import BrowserManager, get_file_version_string, has_visible_window
from device_manager import DeviceManager


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. CROSS-PLATFORM & LINUX COMPATIBILITY TESTS
# ==============================================================================

class TestCrossPlatformCompatibility:
    """Verifies that Windows-specific functions gracefully degrade or use POSIX fallbacks."""

    def test_has_visible_window_non_windows_returns_false(self):
        """On non-Windows platforms, has_visible_window safely returns False without ctypes errors."""
        with patch("sys.platform", "linux"):
            res = has_visible_window(1234)
            assert res is False

    def test_get_file_version_string_linux_fallback(self):
        """When not on Windows, get_file_version_string falls back to running --version."""
        with patch("sys.platform", "linux"):
            with patch("os.path.isfile", return_value=True):
                mock_proc = MagicMock()
                mock_proc.returncode = 0
                mock_proc.stdout = "Google Chrome 132.0.6834.110\n"
                mock_proc.stderr = ""
                with patch("subprocess.run", return_value=mock_proc):
                    ver = get_file_version_string("/usr/bin/google-chrome")
                    assert ver == "132.0.6834.110"

    def test_device_manager_linux_machine_id_fallback(self, tmp_path):
        """When winreg is unavailable, DeviceManager reads /etc/machine-id."""
        from unittest.mock import mock_open
        m_open = mock_open(read_data="abcdef0123456789\n")

        with patch("device_manager.winreg", None):
            with patch("os.path.isfile", side_effect=lambda p: p in ("/etc/machine-id", "/var/lib/dbus/machine-id")):
                with patch("builtins.open", m_open):
                    DeviceManager._cached_info = None
                    info = DeviceManager.get_device_info()
                    assert info is not None
                    assert "device_id" in info
                    DeviceManager._cached_info = None  # Reset

    def test_find_executable_shutil_which_fallback(self):
        """BrowserManager._find_executable finds linux binaries via shutil.which."""
        with patch("shutil.which", return_value="/usr/bin/chromium"):
            with patch("os.path.isfile", return_value=True):
                exe = BrowserManager._find_executable("", ["/usr/bin/chromium"])
                assert exe == "/usr/bin/chromium"


# ==============================================================================
# 2. CLOUD AUTHENTICATION & TAILSCALE MIDDLEWARE TESTS
# ==============================================================================

class TestCloudAuthenticationMiddleware:
    """Verifies Tailscale header injection, Bearer tokens, cookies, and local mode."""

    def test_auth_disabled_by_default_allows_requests(self, client):
        """When RELAY_ENABLE_AUTH is not set, all API requests pass through transparently."""
        with patch.dict(os.environ, {"RELAY_ENABLE_AUTH": "0", "RELAY_AUTH_KEY": ""}):
            assert is_auth_enabled() is False
            res = client.get("/api/auth/me")
            assert res.status_code == 200
            data = res.json()
            assert data["authenticated"] is True
            assert data["auth_enabled"] is False

    def test_auth_enabled_blocks_unauthenticated_api(self, client):
        """When RELAY_ENABLE_AUTH=1, unauthenticated API requests receive HTTP 401."""
        with patch.dict(os.environ, {"RELAY_ENABLE_AUTH": "1", "RELAY_AUTH_KEY": "secret123"}):
            assert is_auth_enabled() is True
            res = client.get("/api/campaigns")
            assert res.status_code == 401
            assert "authentication required" in res.json()["detail"].lower()

    def test_auth_enabled_allows_public_endpoints(self, client):
        """Health check, manifest, and favicon remain public even when auth is enabled."""
        with patch.dict(os.environ, {"RELAY_ENABLE_AUTH": "1", "RELAY_AUTH_KEY": "secret123"}):
            res_health = client.get("/api/health")
            assert res_health.status_code == 200
            assert res_health.json()["status"] == "healthy"

            res_manifest = client.get("/manifest.json")
            assert res_manifest.status_code == 200
            assert "Relay" in res_manifest.text

    def test_tailscale_user_header_authentication(self, client):
        """Tailscale-User-Login header automatically authenticates requests."""
        with patch.dict(os.environ, {"RELAY_ENABLE_AUTH": "1", "ALLOWED_TAILSCALE_USERS": "user@gmail.com"}):
            # Allowed user
            headers = {
                "Tailscale-User-Login": "user@gmail.com",
                "Tailscale-User-Name": "User Name"
            }
            res = client.get("/api/auth/me", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert data["authenticated"] is True
            assert data["auth_type"] == "tailscale"
            assert data["user"]["email"] == "user@gmail.com"

            # Blocked user (not in allowlist)
            bad_headers = {"Tailscale-User-Login": "intruder@evil.com"}
            res_bad = client.get("/api/campaigns", headers=bad_headers)
            assert res_bad.status_code == 403
            assert "not authorized" in res_bad.json()["detail"].lower()

    def test_bearer_token_and_login_api(self, client):
        """Direct password login via /api/auth/login sets cookie and validates."""
        with patch.dict(os.environ, {"RELAY_ENABLE_AUTH": "1", "RELAY_AUTH_KEY": "master-pass-123"}):
            # Failed login
            bad_res = client.post("/api/auth/login", json={"password": "wrong-password"})
            assert bad_res.status_code == 401

            # Successful login
            good_res = client.post("/api/auth/login", json={"password": "master-pass-123"})
            assert good_res.status_code == 200
            cookie_val = good_res.cookies.get("relay_session")
            assert cookie_val is not None

            # Authenticated request using cookie
            client.cookies.set("relay_session", cookie_val)
            cookie_client_res = client.get("/api/auth/me")
            assert cookie_client_res.status_code == 200
            assert cookie_client_res.json()["authenticated"] is True
            client.cookies.clear()

            # Authenticated request using Bearer header
            token = good_res.json()["token"]
            bearer_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert bearer_res.status_code == 200
            assert bearer_res.json()["authenticated"] is True


# ==============================================================================
# 3. WHATSAPP PHONE NUMBER PAIRING TESTS
# ==============================================================================

class TestWhatsAppPhoneNumberPairing:
    """Verifies the phone-number linking mechanism and REST API endpoints."""

    def test_sanitize_phone_number(self):
        """Sanitizes raw user inputs into digits and optional leading '+'."""
        assert WhatsAppPairingManager.sanitize_phone_number("+1 (415) 555-2671") == "+14155552671"
        assert WhatsAppPairingManager.sanitize_phone_number("  91 98765-43210  ") == "919876543210"
        assert WhatsAppPairingManager.sanitize_phone_number("") == ""

    def test_invalid_phone_number_rejected(self, client):
        """Phone numbers with fewer than 7 digits are rejected immediately."""
        res = client.post("/api/whatsapp/pair-phone", json={"phone_number": "123"})
        assert res.status_code == 400
        assert "at least 7 digits" in str(res.json()).lower()

    def test_phone_pairing_already_connected(self, client):
        """If driver already has active chat pane, returns already_connected."""
        mock_driver = MagicMock()
        mock_chat_pane = MagicMock()
        mock_chat_pane.is_displayed.return_value = True
        mock_driver.find_elements.return_value = [mock_chat_pane]

        with patch("backend.whatsapp_pairing.connection_monitor.get_driver", return_value=mock_driver):
            res = client.post("/api/whatsapp/pair-phone", json={"phone_number": "+14155552671"})
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "already_connected"

    def test_successful_phone_pairing_flow(self, client):
        """Verifies full flow: link click, phone entry, next click, and code extraction."""
        mock_driver = MagicMock()
        mock_driver.current_url = "https://web.whatsapp.com"

        # Mock elements
        mock_link_elem = MagicMock()
        mock_link_elem.is_displayed.return_value = True

        mock_input_elem = MagicMock()
        mock_input_elem.is_displayed.return_value = True

        mock_next_btn = MagicMock()
        mock_next_btn.is_displayed.return_value = True

        mock_code_elem = MagicMock()
        mock_code_elem.text = "ABCD-1234"
        mock_code_elem.get_attribute.return_value = "ABCD-1234"

        # Sequential find_elements behavior
        def mock_find_elements(by, query):
            q_str = str(query).lower()
            if "pane-side" in q_str:
                return []  # Not logged in yet
            if "link with phone number" in q_str or "link-device" in q_str:
                return [mock_link_elem]
            if "input" in q_str or "tel" in q_str or "@type='text'" in q_str:
                return [mock_input_elem]
            if "next" in q_str or "continue" in q_str:
                return [mock_next_btn]
            if "link-code" in q_str or "aria-details" in q_str:
                return [mock_code_elem]
            return []

        mock_driver.find_elements.side_effect = mock_find_elements

        with patch("backend.whatsapp_pairing.connection_monitor.get_driver", return_value=mock_driver):
            res = client.post("/api/whatsapp/pair-phone", json={"phone_number": "+14155552671"})
            assert res.status_code == 200
            data = res.json()
            assert data["success"] is True
            assert data["status"] == "code_generated"
            assert data["code"] == "ABCD-1234"
            assert data["seconds_remaining"] == 120

            # Verify link click and input calls
            assert mock_link_elem.click.called
            assert mock_input_elem.send_keys.called

            # Check status endpoint
            status_res = client.get("/api/whatsapp/pair-status")
            assert status_res.status_code == 200
            status_data = status_res.json()
            assert status_data["status"] == "waiting_for_user"
            assert status_data["code"] == "ABCD-1234"

            # Now simulate successful authentication
            def mock_find_elements_auth(by, query):
                if "pane-side" in str(query):
                    m = MagicMock()
                    m.is_displayed.return_value = True
                    return [m]
                return []
            mock_driver.find_elements.side_effect = mock_find_elements_auth

            auth_res = client.get("/api/whatsapp/pair-status")
            assert auth_res.status_code == 200
            assert auth_res.json()["status"] == "authenticated"

            # Cancel pairing
            cancel_res = client.post("/api/whatsapp/pair-cancel")
            assert cancel_res.status_code == 200
            assert cancel_res.json()["success"] is True
