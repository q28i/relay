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


def test_15_sticker_message_is_rejected_and_never_satisfies_media_requirement():
    """Verify that an outgoing message containing a sticker is strictly rejected when require_media=True."""
    driver = MockWebDriver()
    engine = WhatsAppEngine(driver)

    initial_ids = {"msg_0"}
    # New message msg_1 appears, but it is a sticker!
    driver.script_return_values = [
        [
            {"data_id": "msg_0", "text": "old", "has_media": False},
            {"data_id": "msg_1", "text": "123 automation check", "has_media": False, "is_sticker": True}
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


def test_16_outgoing_message_data_identifies_sticker_by_alt_or_data_id():
    """Verify that _get_outgoing_message_data flags is_sticker=True when element matches sticker attributes."""
    driver = MockWebDriver()
    mock_el = MagicMock()
    mock_el.get_attribute.side_effect = lambda attr: "msg_sticker_123" if attr == "data-id" else None
    mock_el.text = "caption"

    mock_img = MagicMock()
    mock_img.get_attribute.side_effect = lambda attr: "Sticker with no label" if attr == "alt" else None
    mock_img.is_displayed.return_value = True

    mock_el.find_elements.side_effect = lambda by, q: [mock_img] if "img" in q else []
    driver.find_elements = lambda by, q: [mock_el] if "message-out" in q else []
    driver.execute_script = lambda script, *args: None

    engine = WhatsAppEngine(driver)
    data = engine._get_outgoing_message_data()

    assert len(data) == 1
    assert data[0]["is_sticker"] is True
    assert data[0]["has_media"] is False


def test_17_caption_input_selectors_strictly_exclude_footer():
    """Verify that WhatsAppEngine.CAPTION_INPUT_SELECTORS does NOT include any footer selector."""
    from selenium.webdriver.common.by import By
    for by_type, query in WhatsAppEngine.CAPTION_INPUT_SELECTORS:
        assert "footer" not in query.lower(), f"Forbidden footer query found in CAPTION_INPUT_SELECTORS: {query}"


def test_18_photo_file_upload_rejects_sticker_input():
    """Verify that file inputs with accept='image/*' without video are strictly rejected for photos."""
    driver = MockWebDriver()
    # Return sticker input
    sticker_input = MagicMock()
    sticker_input.get_attribute.side_effect = lambda attr: "image/*" if attr == "accept" else None

    driver.find_elements = lambda by, q: [sticker_input] if "input" in q else []
    engine = WhatsAppEngine(driver)

    # Test file
    test_file = os.path.abspath(__file__)
    # Pretend it is a jpg
    with patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=1024), \
         patch("os.path.splitext", return_value=("test", ".jpg")):
        res = engine._send_attachment_flow(test_file, caption="123", timeout=1)

    assert res["status"] == "FAILED"
    assert "Photos & videos" in res["error"] or "sticker" in res["error"].lower()


def test_19_photo_file_upload_selects_video_input():
    """Verify that file input with accept containing 'video' is selected for photos."""
    driver = MockWebDriver()
    photo_input = MagicMock()
    photo_input.get_attribute.side_effect = lambda attr: "image/*,video/mp4" if attr == "accept" else None

    driver.find_elements = lambda by, q: [photo_input] if "input" in q or "relay-active" in q else []
    engine = WhatsAppEngine(driver)

    test_file = os.path.abspath(__file__)
    with patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=1024), \
         patch("os.path.splitext", return_value=("test", ".jpg")), \
         patch.object(engine, "_dismiss_media_preview"):
        res = engine._send_attachment_flow(test_file, caption="", timeout=0.5)

    photo_input.send_keys.assert_called_once_with(os.path.abspath(test_file))


def test_20_candidate_caption_in_footer_is_filtered_out():
    """Verify that any candidate caption element located in the footer is rejected."""
    driver = MockWebDriver()
    photo_input = MagicMock()
    photo_input.get_attribute.side_effect = lambda a: "image/*,video/mp4" if a == "accept" else None

    footer_caption_el = MagicMock()
    footer_caption_el.is_displayed.return_value = True

    preview_container = MagicMock()
    preview_container.is_displayed.return_value = True

    def find_elems_mock(by, q):
        if "input" in q:
            return [photo_input]
        if "data-animate-modal-popup" in q or "media-caption-input-container" in q or "modal" in q:
            return [preview_container]
        if "contenteditable" in q:
            return [footer_caption_el]
        return []

    driver.find_elements = find_elems_mock
    # Script indicates element is in footer
    driver.execute_script = lambda script, *args: True if "closest('footer')" in script else None

    engine = WhatsAppEngine(driver)
    test_file = os.path.abspath(__file__)

    with patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=1024), \
         patch("os.path.splitext", return_value=("test", ".jpg")), \
         patch.object(engine, "_dismiss_media_preview"):
        res = engine._send_attachment_flow(test_file, caption="Check Caption", timeout=0.1)

    # Caption must fail because candidate was in footer!
    assert res["status"] == "FAILED"
    assert "could not insert caption" in res["error"]


def test_21_caption_insertion_aborts_without_sending_if_unverified():
    """Verify ZERO SILENT DROPPING: if caption text is not verified in rendered element, send is aborted."""
    driver = MockWebDriver()
    photo_input = MagicMock()
    photo_input.get_attribute.side_effect = lambda a: "image/*,video/mp4" if a == "accept" else None

    cand_el = MagicMock()
    cand_el.is_displayed.return_value = True
    cand_el.text = ""  # Empty text, caption failed to render!

    preview_container = MagicMock()
    preview_container.is_displayed.return_value = True

    def find_elems_mock(by, q):
        if "input" in q:
            return [photo_input]
        if "data-animate-modal-popup" in q or "media-caption-input-container" in q:
            return [preview_container]
        if "contenteditable" in q:
            return [cand_el]
        return []

    driver.find_elements = find_elems_mock
    driver.execute_script = lambda script, *args: False if "closest('footer')" in script else ""

    engine = WhatsAppEngine(driver)
    test_file = os.path.abspath(__file__)

    with patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=1024), \
         patch("os.path.splitext", return_value=("test", ".jpg")), \
         patch.object(engine, "_dismiss_media_preview") as mock_dismiss:
        res = engine._send_attachment_flow(test_file, caption="Mandatory Caption", timeout=0.1)

    assert res["status"] == "FAILED"
    assert "could not insert caption" in res["error"]
    mock_dismiss.assert_called_once_with(force=True, send_action_triggered=False)


def test_22_connection_monitor_yields_when_dispatch_lock_is_held():
    """Verify that ConnectionMonitor._observation_worker skips WebDriver probing while dispatch lock is held."""
    from backend.connection_monitor import ConnectionMonitor
    from backend.job_queue import _session_dispatch_lock

    monitor = ConnectionMonitor()
    driver_mock = MagicMock()
    monitor._driver = driver_mock
    monitor._monitoring_active = True

    _session_dispatch_lock.acquire()
    try:
        with patch("time.sleep") as mock_sleep:
            def sleep_side_effect(dur):
                if dur == 1.5:
                    # After yielding for the active dispatch lock, deactivate monitor to exit loop cleanly
                    monitor._monitoring_active = False
            mock_sleep.side_effect = sleep_side_effect
            monitor._observation_worker()
            mock_sleep.assert_any_call(1.5)
    finally:
        _session_dispatch_lock.release()

    driver_mock.find_elements.assert_not_called()


def test_23_multi_recipient_advances_after_permanent_failure():
    """Verify that if recipient 1 suffers a permanent failure (e.g. invalid number), the queue advances to recipient 2."""
    worker = BackgroundJobWorker()
    worker._is_paused = False
    worker._is_stopped = False

    mock_provider = MagicMock()
    # Contact 1 fails permanently; Contact 2 succeeds
    mock_provider.send_message.side_effect = [
        {"status": "INVALID_NUMBER", "error": "Number not registered on WhatsApp"},
        {"status": "SENT", "media_status": "SENT", "text_status": "SENT", "overall_status": "SENT"}
    ]

    contacts = [
        {"name": "Bad Number", "phone": "910000000000"},
        {"name": "Good Number", "phone": "917622029755"}
    ]

    with patch("backend.connection_monitor.connection_monitor.is_connected", return_value=True):
        job = worker.start_campaign_job(
            campaign_name="Test Multi-Recipient Permanent Skip",
            contacts=contacts,
            template_content="Hello",
            min_delay=0.01,
            max_delay=0.02,
            max_retries=1,
            use_mock=False,
            provider=mock_provider
        )
        time.sleep(1.0)

    assert mock_provider.send_message.call_count == 2
    items = db.get_queue_items(job_id=job["id"])
    assert len(items) == 2
    assert items[0]["status"] == "FAILED_PERMANENT"
    assert items[1]["status"] == "DISPATCHED"


def test_24_multi_recipient_pauses_only_on_uncertain_transmission():
    """Verify that an UNCERTAIN transmission on recipient 1 pauses the campaign to prevent duplicate send on recipient 2."""
    worker = BackgroundJobWorker()
    worker._is_paused = False
    worker._is_stopped = False

    mock_provider = MagicMock()
    mock_provider.send_message.return_value = {
        "status": "UNCERTAIN",
        "transmission_state": "UNCERTAIN",
        "recovery_eligibility": "reconcile_manual",
        "error": "Preview overlay lingered"
    }

    contacts = [
        {"name": "Uncertain Contact", "phone": "917622029755"},
        {"name": "Second Contact", "phone": "917041749093"}
    ]

    with patch("backend.connection_monitor.connection_monitor.is_connected", return_value=True):
        job = worker.start_campaign_job(
            campaign_name="Test Multi-Recipient Pause on Uncertain",
            contacts=contacts,
            template_content="Hello",
            min_delay=0.1,
            max_delay=0.2,
            max_retries=1,
            use_mock=False,
            provider=mock_provider
        )
        time.sleep(1.5)

    # Provider should ONLY be called once because campaign paused
    assert mock_provider.send_message.call_count == 1
    items = db.get_queue_items(job_id=job["id"])
    assert items[0]["status"] == "UNCERTAIN"
    assert items[1]["status"] == "PENDING"
    assert worker._is_paused is True


def test_25_recipient_activity_drawer_contains_reconciliation_and_delivery_fields():
    """Verify that get_recipient_activity_detail contains recovery_action and delivery_label for UI drawer."""
    test_phone = "917622029755"
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM campaign_queue_items WHERE recipient_phone = ?", (test_phone,))
        cursor.execute("""
            INSERT INTO campaign_queue_items (
                job_id, idempotency_key, recipient_name, recipient_phone,
                resolved_message, status, media_status, text_status, overall_status,
                recovery_eligibility, created_at
            ) VALUES (
                'test_job_rec', 'idem_rec_1', 'Test Recipient', ?,
                'Test Message', 'PARTIALLY_SENT', 'SENT', 'FAILED', 'PARTIALLY_SENT',
                'retry_text_only', datetime('now')
            )
        """, (test_phone,))
        item_id = cursor.lastrowid

    detail = db.get_recipient_activity_detail(item_id)
    assert detail is not None
    assert detail["recovery_action"] == "retry_text_only"
    assert detail["recovery_action_label"] == "Retry Text Only"
    assert "Partially" in detail["delivery_label"]
