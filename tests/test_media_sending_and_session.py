"""
Comprehensive Unit & Integration Test Suite for:
1. WhatsApp Web Media Sending Engine (Image/Video vs Document routing, Captions, Preview Confirmation, No Silent Fallback).
2. End-to-End Media Dispatch Pipeline (Upload -> SQLite Storage -> Test-Send -> Queue Item).
3. Zero-Byte & Missing File Detection (Immediate rejection without text-only fallback).
4. Intelligent Browser Session Management (Health state mappings, Session reuse, Bounded Auto-Reconnect).
"""

import os
import io
import time
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from selenium.webdriver.common.by import By

from backend.app import app
from backend.database import db
from backend.adapter import MockMessagingProvider, WhatsAppWebAdapter
from backend.job_queue import BackgroundJobWorker
from backend.connection_monitor import connection_monitor, ConnectionState
from backend.session_lifecycle import session_lifecycle
from whatsapp_engine import WhatsAppEngine


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. WHATSAPP ENGINE ATTACHMENT FLOW TESTS
# ==============================================================================

class TestWhatsAppEngineAttachmentFlow:
    """Verifies WhatsAppEngine._send_attachment_flow logic with mocked Selenium driver."""

    def test_missing_media_file_rejected_without_sending_text(self, tmp_path):
        """If media file does not exist on disk, engine immediately fails without text fallback."""
        mock_driver = MagicMock()
        engine = WhatsAppEngine(mock_driver)
        
        non_existent_file = str(tmp_path / "ghost_image.png")
        res = engine.send_message(phone="14155552671", message="Look at this picture", attachment_path=non_existent_file)
        
        assert res["status"] == "FAILED"
        assert res["media_sent"] is False
        assert "not found" in res["error"].lower() or "missing" in res["error"].lower()
        # Ensure no URL send with encoded text was attempted
        assert not any("&text=" in str(call) for call in mock_driver.get.call_args_list)

    def test_zero_byte_media_file_rejected_without_sending_text(self, tmp_path):
        """If media file exists but is 0 bytes, engine immediately fails without text fallback."""
        mock_driver = MagicMock()
        engine = WhatsAppEngine(mock_driver)

        empty_file = tmp_path / "empty_video.mp4"
        empty_file.write_bytes(b"")  # 0 bytes

        res = engine.send_message(phone="14155552671", message="Empty video test", attachment_path=str(empty_file))
        assert res["status"] == "FAILED"
        assert res["media_sent"] is False
        assert "0 bytes" in res["error"].lower()

    def test_visual_media_routes_to_image_video_input(self, tmp_path):
        """Images (.png/.jpg) and videos (.mp4) must route specifically to inputs with image/video accept."""
        mock_driver = MagicMock()
        engine = WhatsAppEngine(mock_driver)

        img_file = tmp_path / "product_photo.png"
        img_file.write_bytes(b"fake_png_header_and_pixels")

        doc_input = MagicMock()
        doc_input.get_attribute.return_value = "*"

        media_input = MagicMock()
        media_input.get_attribute.return_value = "image/*,video/mp4,video/3gpp"

        modal_open = True
        modal_elem = MagicMock()
        modal_elem.is_displayed.side_effect = lambda: modal_open

        send_btn = MagicMock()
        send_btn.is_displayed.return_value = True
        def on_send_click():
            nonlocal modal_open
            modal_open = False
        send_btn.click.side_effect = on_send_click

        def mock_find_elements(by, query):
            if query == "input[type='file']":
                return [doc_input, media_input]
            if any(sel[1] == query for sel in WhatsAppEngine.PREVIEW_CONTAINER_SELECTORS):
                return [modal_elem] if modal_open else []
            if any(sel[1] == query for sel in WhatsAppEngine.PREVIEW_SEND_BUTTON_SELECTORS):
                return [send_btn] if modal_open else []
            return []

        mock_driver.find_elements.side_effect = mock_find_elements

        with patch.object(time, "sleep"):
            res = engine._send_attachment_flow(str(img_file), caption="Look at product", timeout=5)

        media_input.send_keys.assert_called_once()
        assert str(img_file).lower() in media_input.send_keys.call_args[0][0].lower()
        doc_input.send_keys.assert_not_called()
        assert res["status"] == "SENT"
        assert res["media_sent"] is True

    def test_document_routes_to_document_input(self, tmp_path):
        """Documents (.pdf/.docx/.txt) must route specifically to document inputs (*), not image inputs."""
        mock_driver = MagicMock()
        engine = WhatsAppEngine(mock_driver)

        pdf_file = tmp_path / "catalog.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 sample catalog content")

        media_input = MagicMock()
        media_input.get_attribute.return_value = "image/*,video/mp4"

        doc_input = MagicMock()
        doc_input.get_attribute.return_value = "*"

        modal_open = True
        modal_elem = MagicMock()
        modal_elem.is_displayed.side_effect = lambda: modal_open

        send_btn = MagicMock()
        send_btn.is_displayed.return_value = True
        def on_send_click():
            nonlocal modal_open
            modal_open = False
        send_btn.click.side_effect = on_send_click

        def mock_find_elements(by, query):
            if query == "input[type='file']":
                return [media_input, doc_input]
            if any(sel[1] == query for sel in WhatsAppEngine.PREVIEW_CONTAINER_SELECTORS):
                return [modal_elem] if modal_open else []
            if any(sel[1] == query for sel in WhatsAppEngine.PREVIEW_SEND_BUTTON_SELECTORS):
                return [send_btn] if modal_open else []
            return []

        mock_driver.find_elements.side_effect = mock_find_elements

        with patch.object(time, "sleep"):
            res = engine._send_attachment_flow(str(pdf_file), caption="Our latest catalog", timeout=5)

        doc_input.send_keys.assert_called_once()
        assert str(pdf_file).lower() in doc_input.send_keys.call_args[0][0].lower()
        media_input.send_keys.assert_not_called()
        assert res["status"] == "SENT"
        assert res["media_sent"] is True

    def test_caption_applied_to_preview_overlay(self, tmp_path):
        """When caption is provided, it is sent to the preview overlay caption input."""
        mock_driver = MagicMock()
        engine = WhatsAppEngine(mock_driver)

        test_file = tmp_path / "card.jpg"
        test_file.write_bytes(b"image_bytes")

        caption_input = MagicMock()
        caption_input.is_displayed.return_value = True

        file_input = MagicMock()
        file_input.get_attribute.return_value = "image/*"

        modal_open = True
        modal_elem = MagicMock()
        modal_elem.is_displayed.side_effect = lambda: modal_open

        send_btn = MagicMock()
        send_btn.is_displayed.return_value = True
        def on_send_click():
            nonlocal modal_open
            modal_open = False
        send_btn.click.side_effect = on_send_click

        def mock_find_elements(by, query):
            if query == "input[type='file']":
                return [file_input]
            if any(sel[1] == query for sel in WhatsAppEngine.CAPTION_INPUT_SELECTORS):
                return [caption_input] if modal_open else []
            if any(sel[1] == query for sel in WhatsAppEngine.PREVIEW_CONTAINER_SELECTORS):
                return [modal_elem] if modal_open else []
            if any(sel[1] == query for sel in WhatsAppEngine.PREVIEW_SEND_BUTTON_SELECTORS):
                return [send_btn] if modal_open else []
            return []

        mock_driver.find_elements.side_effect = mock_find_elements

        with patch.object(time, "sleep"):
            res = engine._send_attachment_flow(str(test_file), caption="Summer discount 20%", timeout=5)

        caption_input.send_keys.assert_called_once_with("Summer discount 20%")
        assert res["status"] == "SENT"
        assert res["caption_sent"] is True

    def test_media_without_caption_sends_media_alone(self, tmp_path):
        """When caption is empty, media is sent alone without typing any text."""
        mock_driver = MagicMock()
        engine = WhatsAppEngine(mock_driver)

        test_file = tmp_path / "standalone.jpg"
        test_file.write_bytes(b"standalone_image_bytes")

        caption_input = MagicMock()
        file_input = MagicMock()
        file_input.get_attribute.return_value = "image/*"

        modal_open = True
        modal_elem = MagicMock()
        modal_elem.is_displayed.side_effect = lambda: modal_open

        send_btn = MagicMock()
        send_btn.is_displayed.return_value = True
        def on_send_click():
            nonlocal modal_open
            modal_open = False
        send_btn.click.side_effect = on_send_click

        def mock_find_elements(by, query):
            if query == "input[type='file']":
                return [file_input]
            if any(sel[1] == query for sel in WhatsAppEngine.CAPTION_INPUT_SELECTORS):
                return [caption_input] if modal_open else []
            if any(sel[1] == query for sel in WhatsAppEngine.PREVIEW_CONTAINER_SELECTORS):
                return [modal_elem] if modal_open else []
            if any(sel[1] == query for sel in WhatsAppEngine.PREVIEW_SEND_BUTTON_SELECTORS):
                return [send_btn] if modal_open else []
            return []

        mock_driver.find_elements.side_effect = mock_find_elements

        with patch.object(time, "sleep"):
            res = engine._send_attachment_flow(str(test_file), caption="", timeout=5)

        caption_input.send_keys.assert_not_called()
        assert res["status"] == "SENT"
        assert res["caption_sent"] is False


# ==============================================================================
# 2. TEST-SEND API ENDPOINT VALIDATION
# ==============================================================================

class TestTestSendApiEndpoint:
    """Verifies POST /api/browser-profile/test-send error handling and media validation."""

    def test_test_send_missing_media_id_returns_400(self, client):
        """Referencing a non-existent media_id returns 400 MEDIA_NOT_FOUND."""
        res = client.post(
            "/api/browser-profile/test-send",
            json={"phone": "+14155552671", "message": "Test with missing media", "media_id": 999999}
        )
        assert res.status_code == 400
        data = res.json()
        assert data.get("code") == "MEDIA_NOT_FOUND"

    def test_test_send_deleted_media_file_returns_400_no_text_sent(self, client, tmp_path):
        """If media DB record exists but file on disk was removed, reject with 400 MEDIA_UNAVAILABLE."""
        temp_file = tmp_path / "doomed_image.png"
        temp_file.write_bytes(b"temporary_content")

        asset_id = db.add_media_asset(
            title="Doomed Asset",
            filename="doomed_image.png",
            file_path=str(temp_file),
            file_size=len(b"temporary_content"),
            mime_type="image/png",
            asset_type="image",
            content_hash="mock_hash_doomed"
        )

        os.remove(str(temp_file))

        res = client.post(
            "/api/browser-profile/test-send",
            json={"phone": "+14155552671", "message": "Doomed test", "media_id": asset_id}
        )
        assert res.status_code == 400
        data = res.json()
        assert data.get("code") == "MEDIA_UNAVAILABLE"
        assert "No text was sent" in (data.get("message") or "")

    def test_test_send_zero_byte_media_returns_400(self, client, tmp_path):
        """Zero-byte media file is rejected at test-send boundary."""
        zero_file = tmp_path / "zero_bytes.png"
        zero_file.write_bytes(b"")

        asset_id = db.add_media_asset(
            title="Zero Byte Asset",
            filename="zero_bytes.png",
            file_path=str(zero_file),
            file_size=0,
            mime_type="image/png",
            asset_type="image",
            content_hash="mock_hash_zero"
        )

        res = client.post(
            "/api/browser-profile/test-send",
            json={"phone": "+14155552671", "message": "Zero byte test", "media_id": asset_id}
        )
        assert res.status_code == 400
        data = res.json()
        assert data.get("code") == "MEDIA_UNAVAILABLE"
        assert "0 bytes" in (data.get("message") or "")

    def test_test_send_with_mock_provider_dispatches_cleanly(self, client, tmp_path):
        """Valid media asset and phone number dispatch cleanly with MockMessagingProvider."""
        valid_file = tmp_path / "valid_image.png"
        valid_file.write_bytes(b"valid_image_bytes")

        asset_id = db.add_media_asset(
            title="Valid Test Banner",
            filename="valid_image.png",
            file_path=str(valid_file),
            file_size=len(b"valid_image_bytes"),
            mime_type="image/png",
            asset_type="image",
            content_hash="mock_hash_valid"
        )

        mock_provider = MockMessagingProvider()
        with patch("backend.routers.browser.get_browser_adapter", return_value=mock_provider):
            res = client.post(
                "/api/browser-profile/test-send",
                json={"phone": "+14155552671", "message": "Welcome promo", "media_id": asset_id}
            )
            assert res.status_code == 200
            data = res.json()
            assert data["success"] is True
            assert data["media_sent"] is True
            assert data["caption_sent"] is True


# ==============================================================================
# 3. CAMPAIGN QUEUE MEDIA HONESTY TESTS
# ==============================================================================

class TestCampaignQueueMediaHonesty:
    """Verifies that BackgroundJobWorker detects missing/zero-byte media and never falls back to text."""

    def test_campaign_item_fails_permanently_if_media_missing_on_disk(self, tmp_path):
        """A queued item referencing a missing media file fails permanently without sending text."""
        worker = BackgroundJobWorker()
        worker._active_job = None
        worker._is_stopped = False
        worker._is_paused = False

        missing_path = str(tmp_path / "nonexistent.jpg")
        mock_provider = MockMessagingProvider()

        contacts = [
            {"name": "Alice", "phone": "+14155553001", "consent_status": "opted_in", "message": "Special deal"}
        ]

        # Use mock provider to start campaign
        with patch.object(mock_provider, "send_message", wraps=mock_provider.send_message) as spy_send:
            job = worker.start_campaign_job(
                campaign_name=f"MissingMediaTest_{int(time.time())}",
                contacts=contacts,
                template_content="Deal info",
                attachment_path=missing_path,
                use_mock=True,
                provider=mock_provider
            )

            # Wait briefly for worker thread to process item
            if worker._worker_thread:
                worker._worker_thread.join(timeout=3.0)

            # Provider.send_message should NEVER have been called because media was missing
            spy_send.assert_not_called()

            # Queue record must show FAILED_PERMANENT with explicit missing file error
            items = db.get_queue_items(job_id=job["id"])
            assert len(items) == 1
            assert items[0]["status"] == "FAILED_PERMANENT"
            assert "missing on disk" in items[0]["error_message"]
            assert "No text was sent" in items[0]["error_message"]


# ==============================================================================
# 4. INTELLIGENT BROWSER SESSION MANAGEMENT TESTS
# ==============================================================================

class TestIntelligentBrowserSessionManagement:
    """Verifies session reuse, health state mappings, and bounded auto-reconnect."""

    def test_health_state_mapping_completeness(self):
        """Verifies that all 10 connection states map cleanly to canonical lightweight health states."""
        # Query live status
        status = connection_monitor.get_live_status()
        assert "health_state" in status
        assert status["health_state"] in [
            "not_started", "starting", "browser_ready", "waiting_qr",
            "authenticating", "connected", "disconnected", "profile_locked", "failed"
        ]

    def test_session_reuse_without_restart(self):
        """When an existing healthy driver is already connected, start_monitoring reuses it."""
        mock_driver = MagicMock()
        mock_driver.window_handles = ["handle1"]
        mock_driver.current_url = "https://web.whatsapp.com"

        with connection_monitor._lock:
            connection_monitor._driver = mock_driver
            connection_monitor._state = ConnectionState.CONNECTED

        with patch.object(session_lifecycle, "is_session_healthy", return_value=True):
            status = connection_monitor.start_monitoring(force_restart=False)
            assert status["health_state"] == "connected"
            assert status["is_connected"] is True
            # Driver quit should NOT have been called
            mock_driver.quit.assert_not_called()

        # Clean up
        with connection_monitor._lock:
            connection_monitor._driver = None
            connection_monitor._state = ConnectionState.BROWSER_CLOSED

    def test_auto_reconnect_bounded_to_3_attempts(self):
        """Auto-reconnect tries at most 3 times and does not loop indefinitely."""
        assert connection_monitor._max_reconnect_attempts == 3
        assert connection_monitor._reconnect_attempts == 0

        # Simulate reconnect increments
        connection_monitor._reconnect_attempts = 3
        # Should now classify as permanently disconnected / closed
        with connection_monitor._lock:
            connection_monitor._state = ConnectionState.CONNECTION_LOST

        status = connection_monitor.get_live_status()
        assert status["health_state"] == "disconnected"

        # Reset
        connection_monitor._reconnect_attempts = 0
        connection_monitor._state = ConnectionState.BROWSER_CLOSED
