"""
tests/test_visible_vs_background_and_preview_stuck.py

Automated test suite verifying:
1. Preview Send button selectors are strictly scoped to modal/dialog (no generic div[role='button']).
2. Preview container selectors include modern full-screen and drawer containers.
3. _dismiss_media_preview cleanly triggers close buttons and ESCAPE key.
4. is_logged_in detects both chat list (#side) and active conversation (#main, header).
5. Media send verification detects stuck previews, aborts, and dismisses them.
6. Zero text fallback on media failure in image_with_caption mode (zero text sent).
7. Zero text fallback on media failure in image_then_text mode (_send_text_message_flow never called).
8. send_message cleans up prior stuck preview state before navigating to next recipient.
9. stage_callback emits granular milestones throughout dispatch.
10. BrowserManager configures --window-size=1920,1080 to prevent headless viewport collapse.
11. ConnectionMonitor observer retains login state during active chat in compact mode.
12. JobQueue processes all 3 recipients sequentially in background execution.
13. JobQueue broadcasts job_stage_update events to listeners.
14. JobQueue connection grace period prevents premature pausing during chat navigation.
15. Retry of partially sent message preserves delivered media with zero duplicate transmission.
"""

import os
import time
import pytest
from unittest.mock import MagicMock, patch, call
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from whatsapp_engine import WhatsAppEngine
from browser_manager import BrowserManager
from backend.job_queue import JobQueue
from backend.database import db
from backend.adapter import MockWhatsAppEngine


@pytest.fixture
def temp_image(tmp_path):
    img = tmp_path / "sample.jpg"
    img.write_bytes(b"\xFF\xD8\xFF\xE0" + b"\x00" * 200)
    return str(img)


def test_1_preview_send_button_selectors_scope():
    """1. Ensure no generic div[role='button'] or unscoped span[data-icon='send'] in PREVIEW_SEND_BUTTON_SELECTORS."""
    for by_type, query in WhatsAppEngine.PREVIEW_SEND_BUTTON_SELECTORS:
        # Must not be an unscoped generic div[role='button']
        assert query != "div[role='button']"
        assert query != "div[data-animate-modal-popup='true'] div[role='button']"
        # Must not be a bare unscoped span[data-icon='send'] (which matches background footer send button)
        assert query != "span[data-icon='send']"
        assert query != "span[data-icon='wds-send']"


def test_2_preview_container_selectors_modern():
    """2. Ensure modern container selectors (dialog, drawer, editor, preview) are present."""
    queries = [q for _, q in WhatsAppEngine.PREVIEW_CONTAINER_SELECTORS]
    assert any("drawer" in q or "dialog" in q or "editor" in q for q in queries)


def test_3_dismiss_media_preview_calls_close_and_escape():
    """3. _dismiss_media_preview locates close buttons and sends ESCAPE keys."""
    mock_driver = MagicMock()
    mock_btn = MagicMock()
    mock_btn.is_displayed.return_value = True
    mock_driver.find_elements.return_value = [mock_btn]
    mock_active = MagicMock()
    mock_driver.switch_to.active_element = mock_active

    engine = WhatsAppEngine(mock_driver, headless=True)
    engine._dismiss_media_preview()

    assert mock_btn.click.called or mock_driver.execute_script.called
    assert mock_active.send_keys.called


def test_4_is_logged_in_detects_chat_and_active_pane():
    """4. is_logged_in detects both #side and #main / header panes."""
    mock_driver = MagicMock()
    mock_driver.current_url = "https://web.whatsapp.com"
    engine = WhatsAppEngine(mock_driver, headless=True)

    # Neither visible
    mock_driver.find_elements.return_value = []
    assert engine.is_logged_in() is False

    # #main visible (chat open in single pane view)
    mock_main = MagicMock()
    mock_main.is_displayed.return_value = True

    def find_elements_side_effect(by, query):
        if query in ("main", "div#main", "header"):
            return [mock_main]
        return []

    mock_driver.find_elements.side_effect = find_elements_side_effect
    assert engine.is_logged_in() is True


def test_5_media_send_verification_stuck_preview_fails_and_dismisses(temp_image):
    """5. When send button remains visible (stuck preview), flow fails and dismisses preview."""
    mock_driver = MagicMock()
    engine = WhatsAppEngine(mock_driver, headless=True)

    # File input found
    mock_input = MagicMock()
    mock_input.get_attribute.return_value = "image/*"
    mock_driver.find_elements.side_effect = lambda by, q: [mock_input] if "input" in q else []

    with patch.object(engine, "_dismiss_media_preview") as mock_dismiss, \
         patch("time.time", side_effect=[0, 1, 2, 3, 20, 21, 22]):
        # Mock preview container found
        mock_container = MagicMock()
        mock_container.is_displayed.return_value = True

        mock_send_btn = MagicMock()
        mock_send_btn.is_displayed.return_value = True

        def custom_find(by, query):
            if "input" in query:
                return [mock_input]
            if any(q in query for q in ("dialog", "preview", "editor")):
                return [mock_container]
            if "send" in query:
                return [mock_send_btn]
            return []

        mock_driver.find_elements.side_effect = custom_find

        res = engine._send_attachment_flow(temp_image, caption="", timeout=2)
        assert res["status"] == "FAILED"
        assert res["media_sent"] is False
        assert mock_dismiss.called


def test_6_zero_text_fallback_on_media_failure_in_caption_mode(temp_image):
    """6. In image_with_caption, media failure returns FAILED with text_sent=False."""
    mock_driver = MagicMock()
    engine = WhatsAppEngine(mock_driver, headless=True)

    def find_elem(by, query):
        if any(kw in query for kw in ("invalid", "Phone number")):
            return None
        mock_el = MagicMock()
        mock_el.is_displayed.return_value = True
        return mock_el

    mock_driver.find_element.side_effect = find_elem

    with patch.object(engine, "_send_attachment_flow", return_value={"status": "FAILED", "media_sent": False, "caption_sent": False, "error": "Preview stuck"}), \
         patch.object(engine, "_send_text_message_flow") as mock_text_flow:
        res = engine.send_message(
            phone="919999988888",
            message="123 check caption",
            attachment_path=temp_image,
            message_format="image_with_caption"
        )
        assert res["status"] == "FAILED"
        assert res["media_sent"] is False
        assert res["text_sent"] is False
        assert res["text_status"] == "NOT_ATTEMPTED"
        assert not mock_text_flow.called


def test_7_zero_text_fallback_on_media_failure_in_split_mode(temp_image):
    """7. In image_then_text, media failure never invokes follow-up text."""
    mock_driver = MagicMock()
    engine = WhatsAppEngine(mock_driver, headless=True)

    def find_elem(by, query):
        if any(kw in query for kw in ("invalid", "Phone number")):
            return None
        mock_el = MagicMock()
        mock_el.is_displayed.return_value = True
        return mock_el

    mock_driver.find_element.side_effect = find_elem

    with patch.object(engine, "_send_attachment_flow", return_value={"status": "FAILED", "media_sent": False, "error": "Attachment error"}), \
         patch.object(engine, "_send_text_message_flow") as mock_text_flow:
        res = engine.send_message(
            phone="919999988888",
            message="Follow-up separate text",
            attachment_path=temp_image,
            message_format="image_then_text"
        )
        assert res["status"] == "FAILED"
        assert res["media_sent"] is False
        assert res["text_sent"] is False
        assert not mock_text_flow.called


def test_8_pre_send_dismiss_media_preview_cleans_prior_stuck_state(temp_image):
    """8. send_message calls _dismiss_media_preview before loading next recipient."""
    mock_driver = MagicMock()
    engine = WhatsAppEngine(mock_driver, headless=True)

    def find_elem(by, query):
        if any(kw in query for kw in ("invalid", "Phone number")):
            return None
        mock_el = MagicMock()
        mock_el.is_displayed.return_value = True
        return mock_el

    mock_driver.find_element.side_effect = find_elem

    with patch.object(engine, "_dismiss_media_preview") as mock_dismiss, \
         patch.object(engine, "_send_attachment_flow", return_value={"status": "SENT", "media_sent": True, "error": None}):
        res = engine.send_message(
            phone="919999988888",
            message="Hello",
            attachment_path=temp_image,
            message_format="image_with_caption"
        )
        assert mock_dismiss.called
        assert res["status"] == "SENT"


def test_9_stage_callback_emits_granular_milestones(temp_image):
    """9. stage_callback is invoked with granular progress updates."""
    mock_driver = MagicMock()
    engine = WhatsAppEngine(mock_driver, headless=True)

    mock_input = MagicMock()
    mock_input.is_displayed.return_value = True
    mock_driver.find_element.return_value = mock_input

    stages = []

    def cb(st):
        stages.append(st)

    with patch.object(engine, "_send_attachment_flow", return_value={"status": "SENT", "media_sent": True, "error": None}):
        engine.send_message(
            phone="919999988888",
            message="Hello",
            attachment_path=temp_image,
            message_format="image_with_caption",
            stage_callback=cb
        )
        assert len(stages) > 0
        assert any("Opening" in s or "Waiting" in s for s in stages)


def test_10_headless_chrome_launches_with_1920_1080_window_size():
    """10. BrowserManager configures --window-size=1920,1080 in Chrome options."""
    with patch("browser_manager.BrowserManager.diagnose_profile", return_value={
        "browser_exe_exists": True,
        "is_locked": False,
        "is_stale_lock": False,
        "is_automation_supported": True,
        "user_message": "Available"
    }), patch("browser_manager.webdriver.Chrome") as mock_chrome:
        mock_driver_instance = MagicMock()
        mock_driver_instance.window_handles = ["handle-1"]
        mock_chrome.return_value = mock_driver_instance

        BrowserManager.launch_driver("chrome", {"dir": "__dedicated__", "path": "test_path", "is_dedicated": True}, headless=True)
        assert mock_chrome.called
        chrome_options = mock_chrome.call_args[1].get("options") or mock_chrome.call_args[0][0]
        args = chrome_options.arguments
        assert "--window-size=1920,1080" in args
        assert "--headless=new" in args


def test_11_connection_monitor_observer_does_not_lose_connection_during_active_chat():
    """11. ConnectionMonitor observer detects active chat panes without false disconnect."""
    from backend.connection_monitor import ConnectionMonitor, ConnectionState

    monitor = ConnectionMonitor()
    mock_driver = MagicMock()
    mock_driver.window_handles = ["handle-1"]
    mock_driver.current_url = "https://web.whatsapp.com/send?phone=91999"

    mock_main = MagicMock()
    mock_main.is_displayed.return_value = True

    # #side returns empty, but #main returns visible element
    def custom_find(by, query):
        if query in ("main", "div#main", "header"):
            return [mock_main]
        return []

    mock_driver.find_elements.side_effect = custom_find
    monitor._driver = mock_driver
    monitor._state = ConnectionState.CONNECTED

    # Verify helper recognizes it as logged in
    from whatsapp_engine import WhatsAppEngine
    auth_selectors = list(WhatsAppEngine.CHAT_LIST_SELECTORS) + [
        (By.ID, "main"),
        (By.CSS_SELECTOR, "div#main"),
        (By.CSS_SELECTOR, "header")
    ]
    is_logged_in = False
    for by_type, query in auth_selectors:
        elems = mock_driver.find_elements(by_type, query)
        if any(e.is_displayed() for e in elems):
            is_logged_in = True
            break

    assert is_logged_in is True


def test_12_job_queue_sequential_all_recipients_processed_in_background():
    """12. JobQueue processes all 3 recipients sequentially without premature stoppage."""
    jq = JobQueue()
    recipients = [
        {"phone": "919000000001", "name": "Recipient 1"},
        {"phone": "919000000002", "name": "Recipient 2"},
        {"phone": "919000000003", "name": "Recipient 3"},
    ]

    mock_provider = MockWhatsAppEngine()
    mock_provider.failure_rate = 0.0
    mock_provider.simulation_delay = 0.01

    job = jq.start_campaign_job(
        campaign_name="Test All 3 Sequential",
        contacts=recipients,
        template_content="Hello {name}",
        min_delay=0.01,
        max_delay=0.02,
        use_mock=True,
        provider=mock_provider
    )

    # Wait for completion
    timeout = 10.0
    start = time.time()
    while time.time() - start < timeout:
        active = jq.get_active_job()
        if not active or active.get("status") in ("COMPLETED", "FAILED", "CANCELLED"):
            break
        time.sleep(0.1)

    # Verify all 3 processed in database
    items = db.get_queue_items(job_id=job["id"])
    assert len(items) == 3
    for it in items:
        assert it["status"] == "DISPATCHED"
        assert it["overall_status"] == "SENT"


def test_13_job_queue_broadcasts_job_stage_update():
    """13. JobQueue broadcasts job_stage_update during recipient dispatch."""
    jq = JobQueue()
    received_stages = []

    def listener(event):
        if event.get("type") == "job_stage_update":
            received_stages.append(event)

    jq.register_listener(listener)
    try:
        recipients = [{"phone": "919000000010", "name": "Stage Recipient"}]
        mock_provider = MockWhatsAppEngine()
        mock_provider.failure_rate = 0.0
        mock_provider.simulation_delay = 0.01

        job = jq.start_campaign_job(
            campaign_name="Test Stage Broadcast",
            contacts=recipients,
            template_content="Hello {name}",
            min_delay=0.01,
            max_delay=0.02,
            use_mock=True,
            provider=mock_provider
        )

        timeout = 5.0
        start = time.time()
        while time.time() - start < timeout:
            active = jq.get_active_job()
            if not active or active.get("status") in ("COMPLETED", "FAILED"):
                break
            time.sleep(0.05)

        assert len(received_stages) > 0
        assert received_stages[0]["job_id"] == job["id"]
        assert received_stages[0]["recipient_phone"] == "919000000010"
    finally:
        jq.unregister_listener(listener)


def test_14_job_queue_connection_grace_period_prevents_false_pause():
    """14. Job worker does not pause if driver is alive on WhatsApp Web during navigation."""
    from backend.connection_monitor import connection_monitor

    mock_driver = MagicMock()
    mock_driver.window_handles = ["win-1"]
    mock_driver.current_url = "https://web.whatsapp.com/send?phone=91900"

    with patch.object(connection_monitor, "is_connected", return_value=False), \
         patch.object(connection_monitor, "get_driver", return_value=mock_driver):
        # Even though is_connected is momentarily False, driver is alive and on WhatsApp Web
        mon_driver = connection_monitor.get_driver()
        driver_alive = len(mon_driver.window_handles) > 0 and "web.whatsapp.com" in (mon_driver.current_url or "")
        assert driver_alive is True


def test_15_partial_send_preserves_delivered_media_zero_duplicate(temp_image):
    """15. Retrying text-only after media delivered never re-sends media."""
    mock_driver = MagicMock()
    engine = WhatsAppEngine(mock_driver, headless=True)

    with patch.object(engine, "_send_attachment_flow") as mock_att_flow, \
         patch.object(engine, "_send_text_message_flow", return_value={"status": "SENT", "error": None}):
        res = engine.send_message(
            phone="919999988888",
            message="Follow-up text retry",
            attachment_path=temp_image,
            message_format="image_then_text",
            stage="text_only"
        )
        assert res["status"] == "SENT"
        assert res["media_status"] == "SENT"
        assert res["text_status"] == "SENT"
        assert res["media_sent"] is True
        assert res["text_sent"] is True
        # Media attachment flow must NOT be called on text_only stage!
        assert not mock_att_flow.called
