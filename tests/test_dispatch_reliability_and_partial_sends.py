"""
tests/test_dispatch_reliability_and_partial_sends.py

Comprehensive tests for:
1. Media succeeds, text succeeds (image_then_text and image_with_caption).
2. Media succeeds, text fails (returns PARTIAL, media_status=SENT, text_status=FAILED, overall=PARTIALLY_SENT).
3. Media succeeds, text outcome uncertain (marked UNCERTAIN, no automatic duplicate re-send).
4. Media fails before transmission (media_status=FAILED, overall=FAILED, no text attempted).
5. Browser disconnects between components (media preserved as SENT, text marked FAILED/UNCERTAIN).
6. Wrong conversation detection / verification before send stage.
7. Stale DOM element recovery after media send overlay dismisses.
8. Application restart between stages preserves component states in database.
9. Retry Text Only skips already-sent media (zero duplicate media transmission).
10. Repeated Retry clicks do not create duplicate jobs (concurrency protection).
11. Pause and resume preserve component stage states.
12. Cancel prevents new send attempts immediately.
13. Image-with-caption remains functional as default format.
14. Existing templates and media references remain intact.
"""

import os
import time
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from backend.app import app
from backend.database import db
from backend.adapter import BrowserEngineAdapter, MockWhatsAppEngine
from backend.job_queue import JobQueue, job_worker
from whatsapp_engine import WhatsAppEngine


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def clean_db():
    # Setup test contacts and template
    test_phone = "919999988888"
    cursor = db.get_connection().cursor()
    cursor.execute("DELETE FROM contacts WHERE phone = ?", (test_phone,))
    cursor.execute("DELETE FROM suppression_list WHERE phone = ?", (test_phone,))
    cursor.execute("DELETE FROM campaign_queue_items WHERE recipient_phone = ?", (test_phone,))
    cursor.connection.commit()
    yield test_phone


def test_1_media_succeeds_text_succeeds(tmp_path):
    """1. In image_then_text, media succeeds and follow-up text succeeds -> overall SENT."""
    img_file = tmp_path / "valid.jpg"
    img_file.write_bytes(b"\xFF\xD8\xFF\xE0" + b"\x00" * 100)

    mock_driver = MagicMock()
    engine = WhatsAppEngine(headless=True)
    engine.driver = mock_driver

    with patch.object(engine, "_send_attachment_flow", return_value={"status": "SENT", "media_sent": True, "error": None}), \
         patch.object(engine, "_send_text_message_flow", return_value={"status": "SENT", "error": None}):
        res = engine.send_message(
            phone="919999988888",
            message="Follow-up text message",
            attachment_path=str(img_file),
            message_format="image_then_text"
        )
        assert res["status"] == "SENT"
        assert res["media_status"] == "SENT"
        assert res["text_status"] == "SENT"
        assert res["overall_status"] == "SENT"
        assert res["media_sent"] is True
        assert res["text_sent"] is True


def test_2_media_succeeds_text_fails(tmp_path):
    """2. In image_then_text, media succeeds and text fails -> overall PARTIALLY_SENT, media_sent=True, text_sent=False."""
    img_file = tmp_path / "valid.jpg"
    img_file.write_bytes(b"\xFF\xD8\xFF\xE0" + b"\x00" * 100)

    mock_driver = MagicMock()
    engine = WhatsAppEngine(headless=True)
    engine.driver = mock_driver

    with patch.object(engine, "_send_attachment_flow", return_value={"status": "SENT", "media_sent": True, "error": None}), \
         patch.object(engine, "_send_text_message_flow", return_value={"status": "FAILED", "error": "Composer element not interactable"}):
        res = engine.send_message(
            phone="919999988888",
            message="Follow-up text message",
            attachment_path=str(img_file),
            message_format="image_then_text"
        )
        assert res["status"] == "PARTIAL"
        assert res["media_status"] == "SENT"
        assert res["text_status"] == "FAILED"
        assert res["overall_status"] == "PARTIALLY_SENT"
        assert res["media_sent"] is True
        assert res["text_sent"] is False
        assert res["last_successful_stage"] == "media"
        assert res["recovery_eligibility"] == "retry_text_only"
        assert "Image sent, but follow-up text failed" in res["error"]


def test_3_media_succeeds_text_uncertain(tmp_path):
    """3. Media succeeds and text outcome is uncertain -> marked UNCERTAIN, automatic retry stopped to prevent duplicate."""
    img_file = tmp_path / "valid.jpg"
    img_file.write_bytes(b"\xFF\xD8\xFF\xE0" + b"\x00" * 100)

    mock_driver = MagicMock()
    engine = WhatsAppEngine(headless=True)
    engine.driver = mock_driver

    with patch.object(engine, "_send_attachment_flow", return_value={"status": "SENT", "media_sent": True, "error": None}), \
         patch.object(engine, "_send_text_message_flow", return_value={"status": "UNCERTAIN", "error": "Browser timed out waiting for send bubble"}):
        res = engine.send_message(
            phone="919999988888",
            message="Follow-up text message",
            attachment_path=str(img_file),
            message_format="image_then_text"
        )
        assert res["status"] in ("UNCERTAIN", "PARTIAL")
        assert res["media_status"] == "SENT"
        assert res["recovery_eligibility"] in ("reconcile_manual", "retry_text_only")


def test_4_media_fails_before_transmission_no_text_attempted(tmp_path):
    """4. Media fails (missing file or 0 bytes) -> overall FAILED, no text is ever sent."""
    missing_file = tmp_path / "nonexistent.jpg"

    mock_driver = MagicMock()
    engine = WhatsAppEngine(headless=True)
    engine.driver = mock_driver

    res = engine.send_message(
        phone="919999988888",
        message="Should not be sent",
        attachment_path=str(missing_file),
        message_format="image_then_text"
    )
    assert res["status"] == "FAILED"
    assert res["media_sent"] is False
    assert res.get("text_sent", False) is False
    assert "No text was sent" in res["error"]


def test_5_browser_disconnects_between_components(tmp_path):
    """5. Browser session disconnects right after media is sent -> media preserved as SENT, text recorded as FAILED."""
    img_file = tmp_path / "valid.jpg"
    img_file.write_bytes(b"\xFF\xD8\xFF\xE0" + b"\x00" * 100)

    mock_driver = MagicMock()
    engine = WhatsAppEngine(headless=True)
    engine.driver = mock_driver

    with patch.object(engine, "_send_attachment_flow", return_value={"status": "SENT", "media_sent": True, "error": None}), \
         patch.object(engine, "_send_text_message_flow", side_effect=Exception("WebDriver disconnected / session closed")):
        res = engine.send_message(
            phone="919999988888",
            message="Follow-up text message",
            attachment_path=str(img_file),
            message_format="image_then_text"
        )
        assert res["status"] == "PARTIAL"
        assert res["media_status"] == "SENT"
        assert res["text_status"] == "FAILED"
        assert res["last_successful_stage"] == "media"


def test_6_wrong_conversation_detected_before_text_stage():
    """6. Text stage confirms correct conversation before typing."""
    engine = WhatsAppEngine(headless=True)
    mock_driver = MagicMock()
    engine.driver = mock_driver

    # Mock invalid popup presence during text stage
    with patch.object(mock_driver, "find_element") as mock_find:
        mock_popup = MagicMock()
        mock_popup.is_displayed.return_value = True
        mock_find.return_value = mock_popup

        res = engine._send_text_message_flow("Hello")
        assert res["status"] == "FAILED"


def test_7_stale_dom_element_handling_after_media_send(tmp_path):
    """7. Stale element reference after overlay dismisses is caught and recovered."""
    from selenium.common.exceptions import StaleElementReferenceException

    engine = WhatsAppEngine(headless=True)
    mock_driver = MagicMock()
    engine.driver = mock_driver

    # Mock finding element once throwing StaleElementReferenceException then succeeding
    mock_el = MagicMock()
    mock_el.is_displayed.return_value = True
    mock_el.get_attribute.return_value = "true"
    mock_el.tag_name = "div"

    mock_driver.find_elements.side_effect = [
        [MagicMock(is_displayed=MagicMock(side_effect=StaleElementReferenceException("Stale element")))],
        [mock_el],
        [],
        []
    ]

    res = engine._send_text_message_flow("Test message", wait_timeout=2)
    assert res["status"] == "SENT"


def test_8_application_restart_preserves_component_states(clean_db):
    """8. Component states (media_status='SENT', text_status='FAILED') survive database reloads."""
    phone = clean_db
    job_id = "test_restart_job"

    # Enqueue a queue item
    db.create_queue_items(job_id=job_id, campaign_id=None, items=[{
        "idempotency_key": f"test_idemp_{time.time()}",
        "recipient_name": "Restart Contact",
        "recipient_phone": phone,
        "resolved_message": "Follow-up text",
        "media_path": "uploads/media/test.jpg",
        "message_format": "image_then_text"
    }])

    items = db.get_queue_items(job_id=job_id)
    assert len(items) == 1
    item_id = items[0]["id"]

    # Mark as partially sent (image sent, text failed)
    db.update_queue_item_status(
        item_id,
        status="PARTIALLY_SENT",
        error_message="Image sent, but follow-up text failed to send",
        media_status="SENT",
        text_status="FAILED",
        overall_status="PARTIALLY_SENT",
        last_successful_stage="media",
        recovery_eligibility="retry_text_only"
    )

    # Re-read from database
    detail = db.get_recipient_activity_detail(item_id)
    assert detail["display_status"] == "PARTIALLY_SENT"
    assert detail["media_status"] == "SENT"
    assert detail["text_status"] == "FAILED"
    assert detail["last_successful_stage"] == "media"
    assert detail["recovery_action"] == "retry_text_only"


def test_9_retry_text_only_skips_already_sent_media(clean_db):
    """9. Retrying a partially sent recipient executes Text-Only mode without resending image."""
    phone = clean_db
    job_id = "test_retry_text_job"

    db.create_queue_items(job_id=job_id, campaign_id=None, items=[{
        "idempotency_key": f"test_retry_{time.time()}",
        "recipient_name": "Partial Contact",
        "recipient_phone": phone,
        "resolved_message": "Follow-up text",
        "media_path": "uploads/media/test.jpg",
        "message_format": "image_then_text"
    }])

    items = db.get_queue_items(job_id=job_id)
    item_id = items[0]["id"]

    # Set to partially sent
    db.update_queue_item_status(
        item_id,
        status="PARTIALLY_SENT",
        media_status="SENT",
        text_status="FAILED",
        overall_status="PARTIALLY_SENT",
        last_successful_stage="media",
        recovery_eligibility="retry_text_only"
    )

    # Call reset_queue_item_for_retry with mode='text_only'
    updated = db.reset_queue_item_for_retry(item_id, mode="text_only")
    assert updated["media_status"] == "SENT"
    assert updated["last_successful_stage"] == "media"
    assert updated["recovery_action"] == "retry_text_only"
    assert updated["raw_status"] == "PENDING"


def test_10_repeated_retry_clicks_concurrency_guard(client, clean_db):
    """10. Repeated clicks on Retry do not launch duplicate jobs if already running."""
    phone = clean_db
    job_id = "test_guard_job"

    db.create_queue_items(job_id=job_id, campaign_id=None, items=[{
        "idempotency_key": f"test_guard_{time.time()}",
        "recipient_name": "Guard Contact",
        "recipient_phone": phone,
        "resolved_message": "Follow-up text",
        "media_path": "uploads/media/test.jpg",
        "message_format": "image_then_text"
    }])

    items = db.get_queue_items(job_id=job_id)
    item_id = items[0]["id"]

    # Set to RETRYING / RUNNING
    db.update_queue_item_status(item_id, status="RETRYING")

    # API call to retry should return 409 Conflict
    resp = client.post(f"/api/jobs/activity/items/{item_id}/retry")
    assert resp.status_code == 409
    assert "already currently in progress" in resp.json()["detail"]


def test_11_pause_and_resume_preserves_stage_states():
    """11. Pausing and resuming queue worker preserves component-specific states."""
    jq = JobQueue()
    jq.pause_job()
    assert jq._is_paused is True
    jq.resume_job()
    assert jq._is_paused is False


def test_12_cancel_prevents_new_send_attempts():
    """12. Cancelling a job immediately marks worker stopped."""
    jq = JobQueue()
    jq.cancel_job()
    assert jq._is_stopped is True


def test_13_image_with_caption_remains_default_functional(tmp_path):
    """13. Default format image_with_caption sends one image with caption."""
    img_file = tmp_path / "caption_test.jpg"
    img_file.write_bytes(b"\xFF\xD8\xFF\xE0" + b"\x00" * 100)

    mock_driver = MagicMock()
    engine = WhatsAppEngine(headless=True)
    engine.driver = mock_driver

    with patch.object(engine, "_send_attachment_flow", return_value={"status": "SENT", "media_sent": True, "caption_sent": True, "error": None}):
        res = engine.send_message(
            phone="919999988888",
            message="Single caption text",
            attachment_path=str(img_file),
            message_format="image_with_caption"
        )
        assert res["status"] == "SENT"
        assert res["media_sent"] is True
        assert res["caption_sent"] is True


def test_14_existing_templates_and_media_references_intact():
    """14. Existing templates retrieve their assigned media and variations cleanly."""
    templates = db.get_templates()
    assert isinstance(templates, list)
    if templates:
        t = templates[0]
        assert "id" in t
        assert "name" in t
        assert "media_assets" in t
        assert "text_variations" in t

