"""
WhatsApp Automation Engine using Modern Selenium & WhatsApp Web
Supports:
- Direct click-to-chat URL navigation (saved and unsaved numbers)
- Media Attachments (Images, Videos, PDFs, Documents) with captions
- Spintax variation to reduce anti-spam hash detection
- Reddit-researched Anti-Ban pacing (randomized jitter, batch cooldown pauses)
- Real-time progress and delivery auditing
"""

import os
import re
import time
import random
import urllib.parse
from typing import List, Dict, Callable, Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


def process_spintax(text: str) -> str:
    """
    Recursively evaluates Spintax patterns: {Hi|Hello|Hey} -> randomly selected option.
    Does NOT affect non-spintax tags like {name} because they don't contain '|'.
    """
    pattern = re.compile(r"\{([^{}]+?\|[^{}]+?)\}")
    while pattern.search(text):
        text = pattern.sub(lambda m: random.choice(m.group(1).split("|")), text)
    return text


class WhatsAppEngine:
    URL_BASE = "https://web.whatsapp.com"

    CHAT_LIST_SELECTORS = [
        (By.ID, "pane-side"),
        (By.CSS_SELECTOR, "div[aria-label='Chat list']"),
        (By.CSS_SELECTOR, "div[data-tab='3']"),
        (By.XPATH, "//div[@id='side']")
    ]

    SEND_BUTTON_SELECTORS = [
        (By.CSS_SELECTOR, "span[data-icon='send']"),
        (By.CSS_SELECTOR, "button[aria-label='Send']"),
        (By.CSS_SELECTOR, "span[data-icon='wds-send']"),
        (By.XPATH, "//button[@aria-label='Send']"),
        (By.XPATH, "//span[@data-icon='send']/parent::button"),
    ]

    MESSAGE_INPUT_SELECTORS = [
        (By.CSS_SELECTOR, "div[contenteditable='true'][data-tab='10']"),
        (By.CSS_SELECTOR, "div[contenteditable='true'][aria-placeholder='Type a message']"),
        (By.CSS_SELECTOR, "div[contenteditable='true']"),
    ]

    ATTACH_BUTTON_SELECTORS = [
        (By.CSS_SELECTOR, "span[data-icon='plus']"),
        (By.CSS_SELECTOR, "span[data-icon='attach-menu-plus']"),
        (By.CSS_SELECTOR, "button[aria-label='Attach']"),
        (By.CSS_SELECTOR, "div[title='Attach']"),
    ]

    CAPTION_INPUT_SELECTORS = [
        (By.CSS_SELECTOR, "div[contenteditable='true'][aria-placeholder*='caption']"),
        (By.CSS_SELECTOR, "div[contenteditable='true'][data-tab='10']"),
        (By.CSS_SELECTOR, "div[contenteditable='true']"),
    ]

    INVALID_POPUP_SELECTORS = [
        (By.XPATH, "//*[contains(text(), 'Phone number shared via url is invalid')]"),
        (By.XPATH, "//*[contains(text(), 'url is invalid')]"),
        (By.XPATH, "//div[contains(text(), 'Phone number shared via url is invalid')]"),
    ]

    POPUP_OK_BUTTONS = [
        (By.XPATH, "//button//div[contains(text(), 'OK')]"),
        (By.XPATH, "//div[@role='button']//div[contains(text(), 'OK')]"),
        (By.XPATH, "//button[contains(., 'OK')]")
    ]

    def __init__(self, driver):
        self.driver = driver
        self._is_paused = False
        self._is_stopped = False

    def pause(self):
        self._is_paused = True

    def resume(self):
        self._is_paused = False

    def stop(self):
        self._is_stopped = True

    def ensure_logged_in(self, timeout: int = 90, status_callback: Optional[Callable[[str], None]] = None) -> bool:
        """Navigates to WhatsApp Web and confirms login status."""
        msg = "[INFO] Opening WhatsApp Web..."
        print(msg)
        if status_callback:
            status_callback(msg)

        self.driver.get(self.URL_BASE)
        start_time = time.time()
        qr_printed = False

        while time.time() - start_time < timeout:
            for by_type, query in self.CHAT_LIST_SELECTORS:
                try:
                    elem = self.driver.find_element(by_type, query)
                    if elem.is_displayed():
                        msg = "[OK] WhatsApp Web session is active and ready."
                        print(msg)
                        if status_callback:
                            status_callback(msg)
                        return True
                except Exception:
                    pass

            try:
                qr_elem = self.driver.find_element(By.CSS_SELECTOR, "canvas[aria-label='Scan this QR code to link a device']")
                if qr_elem.is_displayed() and not qr_printed:
                    msg = "[QR CODE] Please scan the QR code in the browser window to connect..."
                    print(msg)
                    if status_callback:
                        status_callback(msg)
                    qr_printed = True
            except Exception:
                pass

            time.sleep(2)

        return False

    def send_message(
        self,
        phone: str,
        message: str = "",
        attachment_path: Optional[str] = None,
        wait_timeout: int = 30
    ) -> Dict[str, str]:
        """
        Sends a message and/or media attachment to a phone number.
        Works for text only, media only, or media with text caption.
        """
        message = process_spintax(message)
        encoded_msg = urllib.parse.quote(message) if not attachment_path else ""

        # Open chat
        direct_url = f"{self.URL_BASE}/send?phone={phone}"
        if encoded_msg:
            direct_url += f"&text={encoded_msg}"

        try:
            self.driver.get(direct_url)
        except Exception as e:
            return {"status": "FAILED", "error": f"Failed to load chat URL: {e}"}

        start_time = time.time()
        while time.time() - start_time < wait_timeout:
            # 1. Check for invalid number popup
            for by_type, query in self.INVALID_POPUP_SELECTORS:
                try:
                    invalid_popup = self.driver.find_element(by_type, query)
                    if invalid_popup.is_displayed():
                        self._dismiss_invalid_popup()
                        return {"status": "INVALID_NUMBER", "error": "Number not registered on WhatsApp"}
                except Exception:
                    pass

            # 2. If Media Attachment is specified, attach file
            if attachment_path and os.path.isfile(attachment_path):
                # Verify chat input or chat area is loaded
                chat_loaded = False
                for by_type, query in self.MESSAGE_INPUT_SELECTORS:
                    try:
                        elem = self.driver.find_element(by_type, query)
                        if elem.is_displayed():
                            chat_loaded = True
                            break
                    except Exception:
                        pass

                if chat_loaded:
                    return self._send_attachment_flow(attachment_path, caption=message, timeout=wait_timeout)

            # 3. Text-only message flow
            else:
                for by_type, query in self.SEND_BUTTON_SELECTORS:
                    try:
                        send_btn = self.driver.find_element(by_type, query)
                        if send_btn.is_displayed():
                            time.sleep(1)
                            send_btn.click()
                            time.sleep(2.5)
                            return {"status": "SENT", "error": None}
                    except Exception:
                        pass

                for by_type, query in self.MESSAGE_INPUT_SELECTORS:
                    try:
                        inp = self.driver.find_element(by_type, query)
                        if inp.is_displayed() and inp.text.strip():
                            time.sleep(1)
                            inp.send_keys(Keys.ENTER)
                            time.sleep(2.5)
                            return {"status": "SENT", "error": None}
                    except Exception:
                        pass

            time.sleep(1.5)

        return {"status": "FAILED", "error": f"Timed out waiting for chat to initialize"}

    def _send_attachment_flow(self, file_path: str, caption: str = "", timeout: int = 30) -> Dict[str, str]:
        """Handles attaching images, videos, and documents with captions."""
        abs_path = os.path.abspath(file_path)
        ext = os.path.splitext(abs_path)[1].lower()
        is_media = ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov", ".3gp", ".m4v"]

        # Open attach menu if needed
        for by_type, query in self.ATTACH_BUTTON_SELECTORS:
            try:
                attach_btn = self.driver.find_element(by_type, query)
                if attach_btn.is_displayed():
                    attach_btn.click()
                    time.sleep(1)
                    break
            except Exception:
                pass

        # Locate file inputs
        file_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
        if not file_inputs:
            return {"status": "FAILED", "error": "Could not locate attachment file input in DOM"}

        target_input = None
        if is_media:
            for inp in file_inputs:
                acc = inp.get_attribute("accept") or ""
                if "image" in acc or "video" in acc:
                    target_input = inp
                    break
        else:
            for inp in file_inputs:
                acc = inp.get_attribute("accept") or ""
                if "*" in acc or "document" in acc or not acc:
                    target_input = inp
                    break

        if not target_input:
            target_input = file_inputs[0]

        try:
            target_input.send_keys(abs_path)
        except Exception as e:
            return {"status": "FAILED", "error": f"Failed to deliver file to input element: {e}"}

        # Wait for preview overlay
        start_t = time.time()
        preview_ready = False
        while time.time() - start_t < timeout:
            # Check for caption input or send button in preview overlay
            for by_type, query in self.SEND_BUTTON_SELECTORS:
                try:
                    s_btn = self.driver.find_element(by_type, query)
                    if s_btn.is_displayed():
                        preview_ready = True
                        break
                except Exception:
                    pass
            if preview_ready:
                break
            time.sleep(1)

        if not preview_ready:
            return {"status": "FAILED", "error": "Attachment preview did not appear"}

        # Add caption if provided
        if caption:
            for by_type, query in self.CAPTION_INPUT_SELECTORS:
                try:
                    c_inp = self.driver.find_element(by_type, query)
                    if c_inp.is_displayed():
                        time.sleep(0.5)
                        c_inp.send_keys(caption)
                        time.sleep(0.5)
                        break
                except Exception:
                    pass

        # Click send button
        for by_type, query in self.SEND_BUTTON_SELECTORS:
            try:
                send_btn = self.driver.find_element(by_type, query)
                if send_btn.is_displayed():
                    time.sleep(1)
                    send_btn.click()
                    time.sleep(4.0)  # Generous buffer for upload completion
                    return {"status": "SENT", "error": None}
            except Exception:
                pass

        return {"status": "FAILED", "error": "Could not click send on attachment preview"}

    def _dismiss_invalid_popup(self):
        """Clicks OK on invalid number alert."""
        for by_type, query in self.POPUP_OK_BUTTONS:
            try:
                ok_btn = self.driver.find_element(by_type, query)
                if ok_btn.is_displayed():
                    ok_btn.click()
                    return
            except Exception:
                pass

    def send_batch(
        self,
        contacts: List[Dict[str, str]],
        min_delay: float = 8.0,
        max_delay: float = 16.0,
        batch_size: int = 20,
        batch_cooldown_secs: float = 60.0,
        max_daily_limit: int = 150,
        global_attachment: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, Dict[str, str], Dict[str, str]], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> List[Dict[str, str]]:
        """
        Dispatches messages with anti-ban protections:
        - Randomized delay between messages
        - Cooldown pause after batch_size messages
        - Daily volume cap
        - Pause / Stop controls
        """
        results = []
        total = min(len(contacts), max_daily_limit)
        sent_in_batch = 0

        def log(msg: str):
            print(msg)
            if log_callback:
                log_callback(msg)

        log(f"\n[INFO] Starting bulk dispatch for {total} contacts (Safe Pacing: {min_delay}s-{max_delay}s)...")

        for idx, contact in enumerate(contacts[:total], 1):
            if self._is_stopped:
                log("[INFO] Automation stopped by user.")
                break

            while self._is_paused:
                time.sleep(1)
                if self._is_stopped:
                    break
            if self._is_stopped:
                break

            phone = contact["phone"]
            name = contact["name"]
            msg = contact.get("message", "")
            # Check row-specific attachment, fallback to global attachment
            attach = contact.get("attachment") or global_attachment

            log(f"[{idx}/{total}] Dispatching to {name} (+{phone})...")

            res = self.send_message(phone=phone, message=msg, attachment_path=attach)
            status = res["status"]
            error = res.get("error")

            record = {
                "name": name,
                "phone": phone,
                "status": status,
                "error": error or "",
                "attachment": attach or "",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            results.append(record)

            if status == "SENT":
                log(f"  -> [OK - SENT]")
                sent_in_batch += 1
            elif status == "INVALID_NUMBER":
                log(f"  -> [SKIPPED - INVALID NUMBER]")
            else:
                log(f"  -> [FAILED: {error}]")

            if progress_callback:
                progress_callback(idx, total, contact, record)

            # Check if batch cooldown pause is triggered
            if idx < total:
                if batch_size > 0 and sent_in_batch >= batch_size:
                    log(f"\n[COOLDOWN PAUSE] Sent {sent_in_batch} messages. Pausing for {batch_cooldown_secs}s to maintain account safety...")
                    time.sleep(batch_cooldown_secs)
                    sent_in_batch = 0
                else:
                    delay = random.uniform(min_delay, max_delay)
                    log(f"  Waiting {delay:.1f}s before next contact (randomized jitter)...")
                    time.sleep(delay)

        return results
