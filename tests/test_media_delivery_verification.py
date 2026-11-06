"""
Regression test suite for Phase 8: Rigorous Media Delivery Verification.
Ensures Relay never falsely claims media success when only ordinary text is sent,
when old existing messages are present, or when attachment preparation fails.
"""

import os
import time
import pytest
from unittest.mock import MagicMock, patch

from whatsapp_engine import WhatsAppEngine
from backend.job_queue import BackgroundJobWorker
from backend.database import db


class MockWebDriver(object):
    """Custom non-MagicMock WebDriver for rigorous realistic testing."""
    def __init__(self):
        self.current_url = "https://web.whatsapp.com/send?phone=917622029755"
        self.title = "WhatsApp"
        self.window_handles = ["win1"]
        self.script_return_values = []
        self._script_call_count = 0

    def get(self, url):
        self.current_url = url

    def execute_script(self, script, *args):
        if self.script_return_values:
            idx = min(self._script_call_count, len(self.script_return_values) - 1)
            self._script_call_count += 1
            val = self.script_return_values[idx]
            if callable(val):
                return val(script, *args)
            return val
        return []

    def find_elements(self, by, query):
        return []

    def find_element(self, by, query):
        raise Exception(f"Element not found: {query}")

    def save_screenshot(self, path):
        pass


def test_1_ordinary_text_message_does_not_satisfy_media_send():
    """Verify that when only an ordinary text message appears, require_media=True returns UNCERTAIN, NOT SENT."""
    driver = MockWebDriver()
    engine = WhatsAppEngine(driver)

    initial_ids = {"msg_1", "msg_2"}
    # New message appears (msg_3), but it has has_media=False (ordinary text only)
    driver.script_return_values = [
        [
            {"data_id": "msg_1", "text": "old text", "has_media": False},
            {"data_id": "msg_2", "text": "old image", "has_media": True},
            {"data_id": "msg_3", "text": "123 automation check", "has_media": False}  # Text only!
        ]
    ]

    res = engine._observe_outgoing_message(
        caption="123 automation check",
        initial_message_ids=initial_ids,
        require_media=True,
        timeout=0.5
    )

    assert res["status"] == "UNCERTAIN"
    assert res["transmission_state"] == "UNCERTAIN"
    assert res["recovery_eligibility"] == "reconcile_manual"


def test_2_existing_image_message_does_not_falsely_confirm_new_send():
    """Verify that an existing old image message in chat history cannot satisfy new media send verification."""
    driver = MockWebDriver()
    engine = WhatsAppEngine(driver)

    initial_ids = {"old_media_msg"}
    # Only old_media_msg is in the chat; no new media message appeared
    driver.script_return_values = [
        [
            {"data_id": "old_media_msg", "text": "123 automation check", "has_media": True}
        ]
    ]

    res = engine._observe_outgoing_message(
        caption="123 automation check",
        initial_message_ids=initial_ids,
        require_media=True,
        timeout=0.5
    )

    assert res["status"] == "UNCERTAIN"
    assert res["transmission_state"] == "UNCERTAIN"


def test_3_caption_mismatch_on_new_media_is_rejected():
    """Verify that if a new image appears but has wrong or missing caption, it is not confirmed."""
    driver = MockWebDriver()
    engine = WhatsAppEngine(driver)

    initial_ids = {"msg_1"}
    # New image message appeared, but with wrong text
    driver.script_return_values = [
        [
            {"data_id": "msg_1", "text": "hello", "has_media": False},
            {"data_id": "msg_2", "text": "completely different caption", "has_media": True}
        ]
    ]

    res = engine._observe_outgoing_message(
        caption="123 automation check",
        initial_message_ids=initial_ids,
        require_media=True,
        timeout=0.5
    )

    assert res["status"] == "UNCERTAIN"


def test_4_correct_new_image_and_caption_confirms_sent_observed():
    """Verify that when a genuine new image message with matching caption appears, it confirms SENT_OBSERVED."""
    driver = MockWebDriver()
    engine = WhatsAppEngine(driver)

    initial_ids = {"msg_1"}
    # New image message appeared with expected caption
    driver.script_return_values = [
        [
            {"data_id": "msg_1", "text": "hello", "has_media": False},
            {"data_id": "msg_2", "text": "123 automation check", "has_media": True, "delivered": False}
        ]
    ]

    res = engine._observe_outgoing_message(
        caption="123 automation check",
        initial_message_ids=initial_ids,
        require_media=True,
        timeout=0.5
    )

    assert res["status"] == "SENT"
    assert res["transmission_state"] == "SENT_OBSERVED"


def test_5_receipt_checkmark_confirms_delivered():
    """Verify that provider delivery checkmarks promote state from SENT_OBSERVED to DELIVERED."""
    driver = MockWebDriver()
    engine = WhatsAppEngine(driver)

    initial_ids = set()
    driver.script_return_values = [
        [
            {"data_id": "msg_1", "text": "123 automation check", "has_media": True, "delivered": True}
        ]
    ]

    res = engine._observe_outgoing_message(
        caption="123 automation check",
        initial_message_ids=initial_ids,
        require_media=True,
        timeout=0.5
    )

    assert res["status"] == "SENT"
    assert res["transmission_state"] == "DELIVERED"


def test_6_zero_text_fallback_when_media_missing_on_disk():
    """Verify that if media file is missing, the system aborts immediately with NO text fallback."""
    driver = MockWebDriver()
    engine = WhatsAppEngine(driver)

    res = engine.send_message(
        phone="917622029755",
        message="Important text",
        attachment_path="non_existent_file.jpg",
        message_format="image_with_caption"
    )

    assert res["status"] == "FAILED"
    assert res["media_status"] == "FAILED"
    assert res["text_status"] == "NOT_ATTEMPTED"
    assert res["media_sent"] is False
    assert res["text_sent"] is False
    assert "file not found" in res["error"].lower()


def test_7_zero_text_fallback_when_media_input_not_found(tmp_path):
    """Verify that if WhatsApp input element cannot be found, no text is sent."""
    dummy_img = tmp_path / "test.jpg"
    dummy_img.write_text("dummy")

    driver = MockWebDriver()
    engine = WhatsAppEngine(driver)
    # find_elements returns empty list -> input not found
    driver.find_elements = lambda by, q: []

    with patch.object(engine, "_dismiss_media_preview"):
        res = engine.send_message(
            phone="917622029755",
            message="Do not send alone",
            attachment_path=str(dummy_img),
            message_format="image_with_caption",
            wait_timeout=1
        )

    assert res["status"] == "FAILED"
    assert res["media_status"] == "FAILED"
    assert res["text_status"] == "NOT_ATTEMPTED"
    assert res["media_sent"] is False
    assert res["text_sent"] is False


def test_8_uncertain_media_send_pauses_campaign_and_prevents_subsequent_sends():
    """Verify that when a media send returns UNCERTAIN, the queue worker immediately pauses without dropping."""
    worker = BackgroundJobWorker()
    worker._is_paused = False
    worker._is_stopped = False

    mock_provider = MagicMock()
    # Recipient 1 returns UNCERTAIN
    mock_provider.send_message.return_value = {
        "status": "UNCERTAIN",
        "transmission_state": "UNCERTAIN",
        "recovery_eligibility": "reconcile_manual",
        "error": "Media preview cleared but bubble unobserved"
    }

    test_contacts = [
        {"phone": "917041749093", "name": "Vipin"},
        {"phone": "917600958393", "name": "Gaurav"}
    ]

    with patch("backend.connection_monitor.connection_monitor.is_connected", return_value=True):
        job_info = worker.start_campaign_job(
            campaign_name="Test Uncertain Pause",
            contacts=test_contacts,
            template_content="123 check",
            min_delay=0.1,
            max_delay=0.2,
            use_mock=False,
            provider=mock_provider
        )

        # Let thread execute item 1
        time.sleep(1.2)

    # Campaign must be paused
    assert worker._is_paused is True
    # mock_provider.send_message must NOT have been called for recipient 2!
    assert mock_provider.send_message.call_count == 1
    call_phone = mock_provider.send_message.call_args[1]["phone"]
    assert call_phone == "917041749093"


def test_9_new_campaign_cannot_inherit_old_component_success_states():
    """Verify queue items are staged with PENDING states, never inheriting historical success."""
    worker = BackgroundJobWorker()
    contacts = [{"phone": "917622029755", "name": "Me"}]

    job = worker.start_campaign_job(
        campaign_name="Test State Isolation",
        contacts=contacts,
        template_content="Test Check",
        attachment_path="sample.jpg",
        min_delay=0.1,
        max_delay=0.2,
        use_mock=True
    )
    job_id = job["id"]

    items = db.get_queue_items(job_id=job_id)
    assert len(items) == 1
    assert items[0]["media_status"] == "PENDING"
    assert items[0]["text_status"] == "PENDING"
    assert items[0]["overall_status"] == "PENDING"


def test_10_safe_cleanup_handles_discard_selection_popup():
    """Verify that _dismiss_media_preview clicks 'Discard' if the 'Discard selection?' confirmation popup is present."""
    driver = MockWebDriver()
    engine = WhatsAppEngine(driver)

    discard_btn = MagicMock()
    discard_btn.is_displayed.return_value = True
    discard_btn.text = "Discard"

    def mock_find_elements(by, query):
        if "Discard" in query:
            return [discard_btn]
        return []

    driver.find_elements = mock_find_elements
    engine._dismiss_media_preview(force=True)

    discard_btn.click.assert_called_once()


def test_11_uncertain_media_send_cannot_be_retried_automatically():
    """Verify that an UNCERTAIN send is flagged for manual reconciliation and not auto-retried."""
    worker = BackgroundJobWorker()
    worker._is_paused = False
    worker._is_stopped = False

    mock_provider = MagicMock()
    mock_provider.send_message.return_value = {
        "status": "UNCERTAIN",
        "transmission_state": "UNCERTAIN",
        "recovery_eligibility": "reconcile_manual",
        "error": "Preview closed but media unobserved"
    }

    test_contacts = [{"phone": "917622029755", "name": "Me"}]

    with patch("backend.connection_monitor.connection_monitor.is_connected", return_value=True):
        job = worker.start_campaign_job(
            campaign_name="Test No Auto-Retry on Uncertain",
            contacts=test_contacts,
            template_content="Test",
            min_delay=0.1,
            max_delay=0.2,
            max_retries=3,
            use_mock=False,
            provider=mock_provider
        )
        time.sleep(1.0)

    # Provider send_message MUST be called exactly once; NO auto-retries!
    assert mock_provider.send_message.call_count == 1
    items = db.get_queue_items(job_id=job["id"])
    assert len(items) == 1
    assert items[0]["recovery_eligibility"] == "reconcile_manual"


def test_12_headed_and_headless_apply_same_verification_contract():
    """Verify both headless=True and headless=False WhatsAppEngine instances enforce require_media strictly."""
    engine_headless = WhatsAppEngine(MockWebDriver(), headless=True)
    engine_headed = WhatsAppEngine(MockWebDriver(), headless=False)

    for eng in (engine_headless, engine_headed):
        eng.driver.script_return_values = [
            [
                {"data_id": "msg_text", "text": "only text", "has_media": False}
            ]
        ]
        res = eng._observe_outgoing_message(
            caption="only text",
            initial_message_ids=set(),
            require_media=True,
            timeout=0.2
        )
        assert res["status"] == "UNCERTAIN"


def test_13_campaign_completion_cannot_derive_media_success_from_generic_text_bubbles():
    """Verify that a job with media required will not mark queue item DISPATCHED with media SENT from text."""
    worker = BackgroundJobWorker()
    mock_provider = MagicMock()

    # Provider returns text only result
    mock_provider.send_message.return_value = {
        "status": "SENT",
        "media_status": "FAILED",
        "text_status": "SENT",
        "overall_status": "FAILED",
        "media_sent": False,
        "text_sent": True
    }

    contacts = [{"phone": "917622029755", "name": "Me"}]
    with patch("backend.connection_monitor.connection_monitor.is_connected", return_value=True):
        job = worker.start_campaign_job(
            campaign_name="Test No Text Derivation",
            contacts=contacts,
            template_content="123",
            attachment_path="sample.jpg",
            min_delay=0.1,
            max_delay=0.2,
            use_mock=False,
            provider=mock_provider
        )
        time.sleep(1.0)

    items = db.get_queue_items(job_id=job["id"])
    assert len(items) == 1
    # Media status must NOT be SENT
    assert items[0]["media_status"] != "SENT"


def test_14_reported_delivery_receipt_requires_evidence_for_particular_message():
    """Verify delivery receipt is checked on the specific new message, not historical messages."""
    driver = MockWebDriver()
    engine = WhatsAppEngine(driver)

    initial_ids = {"old_delivered_msg"}
    # Old message had receipt (delivered=True), but new media message does NOT have receipt (delivered=False)
    driver.script_return_values = [
        [
            {"data_id": "old_delivered_msg", "text": "old", "has_media": True, "delivered": True},
            {"data_id": "new_media_msg", "text": "test caption", "has_media": True, "delivered": False}
        ]
    ]

    res = engine._observe_outgoing_message(
        caption="test caption",
        initial_message_ids=initial_ids,
        require_media=True,
        timeout=0.5
    )

    assert res["status"] == "SENT"
    # Must be SENT_OBSERVED, NOT DELIVERED, because the receipt was on the old message!
    assert res["transmission_state"] == "SENT_OBSERVED"
