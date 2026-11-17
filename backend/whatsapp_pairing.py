"""
WhatsApp Phone-Number Pairing & Linking Manager.

Provides single-phone friendly WhatsApp Web authentication.
Allows users accessing the dashboard from their phone (or headless cloud VM)
to link WhatsApp using an 8-character pairing code instead of scanning a QR code.
"""

import re
import time
import threading
from typing import Dict, Any, Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from logger import get_logger
from backend.connection_monitor import connection_monitor, ConnectionState

logger = get_logger("WhatsAppPairing")


class WhatsAppPairingManager:
    """Coordinates phone-number linking flow on WhatsApp Web via Selenium WebDriver."""

    _instance = None
    _singleton_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = super(WhatsAppPairingManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._lock = threading.RLock()
        self._current_pairing: Optional[Dict[str, Any]] = None
        self._initialized = True

    # --------------------------------------------------------------------------
    # Helper Methods
    # --------------------------------------------------------------------------

    @staticmethod
    def sanitize_phone_number(raw_phone: str) -> str:
        """Strips formatting spaces, hyphens, and parentheses, keeping digits and leading '+'."""
        if not raw_phone:
            return ""
        cleaned = re.sub(r"[^\d+]", "", raw_phone.strip())
        return cleaned

    @staticmethod
    def is_driver_logged_in(driver) -> bool:
        """Quickly checks whether WhatsApp Web is logged in with active chat list."""
        if not driver:
            return False
        chat_selectors = [
            (By.CSS_SELECTOR, "#pane-side"),
            (By.CSS_SELECTOR, "div[data-testid='chat-list']"),
            (By.CSS_SELECTOR, "div[contenteditable='true'][data-tab='3']"),
            (By.XPATH, "//div[@id='pane-side']"),
            (By.XPATH, "//*[@data-testid='chat-list']"),
        ]
        for by_type, query in chat_selectors:
            try:
                elems = driver.find_elements(by_type, query)
                if any(e.is_displayed() for e in elems):
                    return True
            except Exception:
                pass
        return False

    # --------------------------------------------------------------------------
    # Public API Flow
    # --------------------------------------------------------------------------

    def request_phone_pairing(self, phone_number: str) -> Dict[str, Any]:
        """
        Initiates the phone-number pairing workflow on WhatsApp Web.
        Enters the phone number and extracts the generated 8-character pairing code.
        """
        with self._lock:
            clean_phone = self.sanitize_phone_number(phone_number)
            digits_only = re.sub(r"[^\d]", "", clean_phone)
            if len(digits_only) < 7:
                return {
                    "success": False,
                    "status": "invalid_phone",
                    "error": "Phone number must contain at least 7 digits with country code (e.g. +1234567890)."
                }

            # 1. Ensure driver is active
            driver = connection_monitor.get_driver()
            if driver is None:
                logger.info("Driver not running. Launching persistent browser session for phone pairing...")
                import os
                headless_env = os.environ.get("RELAY_HEADLESS", "").lower() in ("1", "true", "yes")
                connection_monitor.start_monitoring(headless=headless_env)
                # Wait up to 15 seconds for driver to launch
                start_w = time.time()
                while time.time() - start_w < 15:
                    driver = connection_monitor.get_driver()
                    if driver is not None:
                        break
                    time.sleep(0.5)

            if driver is None:
                return {
                    "success": False,
                    "status": "browser_error",
                    "error": "Could not launch browser session. Please check browser configuration."
                }

            # 2. Check if already logged in
            if self.is_driver_logged_in(driver):
                return {
                    "success": True,
                    "status": "already_connected",
                    "message": "WhatsApp is already connected and authenticated."
                }

            # 3. Ensure WhatsApp Web is loaded
            try:
                curr_url = driver.current_url or ""
                if "web.whatsapp.com" not in curr_url:
                    driver.get("https://web.whatsapp.com")
                    time.sleep(3)
            except Exception as e:
                logger.warning(f"Error checking or loading WhatsApp Web URL: {e}")
                try:
                    driver.get("https://web.whatsapp.com")
                    time.sleep(3)
                except Exception as e2:
                    return {
                        "success": False,
                        "status": "network_error",
                        "error": f"Failed to load WhatsApp Web: {e2}"
                    }

            # 4. Wait for login interface (QR code or 'Link with phone number' link)
            link_phone_clicked = False
            start_search = time.time()
            while time.time() - start_search < 15:
                # Check if already authenticated during wait
                if self.is_driver_logged_in(driver):
                    return {
                        "success": True,
                        "status": "already_connected",
                        "message": "WhatsApp is already connected."
                    }

                # Try finding 'Link with phone number'
                link_selectors = [
                    (By.XPATH, "//span[contains(translate(text(), 'LINK', 'link'), 'link with phone number')]"),
                    (By.XPATH, "//*[contains(translate(text(), 'LINK', 'link'), 'link with phone number')]"),
                    (By.XPATH, "//*[contains(text(), 'Link with phone number')]"),
                    (By.XPATH, "//div[@role='button'][contains(., 'phone number')]"),
                    (By.CSS_SELECTOR, "span[data-testid='link-device-phone-number']"),
                ]
                for by_type, query in link_selectors:
                    try:
                        elems = driver.find_elements(by_type, query)
                        for elem in elems:
                            if elem.is_displayed():
                                elem.click()
                                link_phone_clicked = True
                                logger.info("Clicked 'Link with phone number' button.")
                                break
                        if link_phone_clicked:
                            break
                    except Exception:
                        pass

                if link_phone_clicked:
                    break
                time.sleep(1)

            if not link_phone_clicked:
                # Maybe already on the phone input screen?
                logger.debug("Could not find 'Link with phone number' button directly; checking if phone input is already visible.")

            # 5. Locate phone number input field
            phone_input = None
            start_input = time.time()
            while time.time() - start_input < 10:
                input_selectors = [
                    (By.XPATH, "//input[@type='text' and (contains(@aria-label, 'phone') or contains(@placeholder, 'phone') or @data-tab or @autocomplete='tel')]"),
                    (By.XPATH, "//form//input[@type='text']"),
                    (By.XPATH, "//input[@type='text']"),
                    (By.CSS_SELECTOR, "input[type='text']"),
                ]
                for by_type, query in input_selectors:
                    try:
                        elems = driver.find_elements(by_type, query)
                        for elem in elems:
                            if elem.is_displayed():
                                phone_input = elem
                                break
                        if phone_input:
                            break
                    except Exception:
                        pass
                if phone_input:
                    break
                time.sleep(0.5)

            if not phone_input:
                return {
                    "success": False,
                    "status": "input_not_found",
                    "error": "Could not locate phone number input field on WhatsApp Web."
                }

            # 6. Type phone number into input
            try:
                phone_input.click()
                phone_input.send_keys(Keys.CONTROL + "a")
                phone_input.send_keys(Keys.BACKSPACE)
                time.sleep(0.2)
                # Send cleaned phone number
                phone_input.send_keys(clean_phone)
                time.sleep(0.5)
            except Exception as e:
                return {
                    "success": False,
                    "status": "input_error",
                    "error": f"Failed entering phone number: {e}"
                }

            # 7. Click Next button
            next_clicked = False
            next_selectors = [
                (By.XPATH, "//button[contains(translate(., 'NEXT', 'next'), 'next')]"),
                (By.XPATH, "//div[@role='button'][contains(translate(., 'NEXT', 'next'), 'next')]"),
                (By.XPATH, "//button[contains(., 'Next') or contains(., 'Continue') or contains(., 'Confirm')]"),
                (By.XPATH, "//div[@role='button'][contains(., 'Next') or contains(., 'Continue')]"),
            ]
            for by_type, query in next_selectors:
                try:
                    elems = driver.find_elements(by_type, query)
                    for elem in elems:
                        if elem.is_displayed():
                            elem.click()
                            next_clicked = True
                            logger.info("Clicked 'Next' button on phone pairing screen.")
                            break
                    if next_clicked:
                        break
                except Exception:
                    pass

            if not next_clicked:
                # Try submitting via ENTER on input
                try:
                    phone_input.send_keys(Keys.RETURN)
                    next_clicked = True
                except Exception:
                    pass

            # 8. Wait for and extract 8-character pairing code
            code = None
            start_code = time.time()
            while time.time() - start_code < 12:
                # Check for container with link code data
                try:
                    code_elems = driver.find_elements(By.XPATH, "//*[@data-link-code or contains(@aria-details, 'link') or contains(@class, 'link-code')]")
                    for ce in code_elems:
                        val = ce.get_attribute("data-link-code") or ce.text or ""
                        match = re.search(r"\b([A-Z0-9]{4})-?([A-Z0-9]{4})\b", val.replace(" ", "").upper())
                        if match:
                            code = f"{match.group(1)}-{match.group(2)}"
                            break
                except Exception:
                    pass

                if not code:
                    # Scan text blocks on page for 8-char pattern
                    try:
                        body_text = driver.find_element(By.TAG_NAME, "body").text
                        match = re.search(r"\b([A-Z0-9]{4})-?([A-Z0-9]{4})\b", body_text.replace(" ", ""))
                        if match:
                            code = f"{match.group(1)}-{match.group(2)}"
                    except Exception:
                        pass

                if not code:
                    # Scan spans that hold individual code characters (WhatsApp often renders 8 individual spans)
                    try:
                        char_spans = driver.find_elements(By.XPATH, "//div[@aria-atomic='true']//span | //div[contains(@class, 'code')]//span")
                        chars = [s.text.strip().upper() for s in char_spans if len(s.text.strip()) == 1 and s.text.strip().isalnum()]
                        if len(chars) >= 8:
                            raw_code = "".join(chars[:8])
                            code = f"{raw_code[:4]}-{raw_code[4:]}"
                    except Exception:
                        pass

                if code:
                    break
                time.sleep(0.8)

            if not code:
                return {
                    "success": False,
                    "status": "code_timeout",
                    "error": "Phone number submitted, but WhatsApp pairing code could not be retrieved in time. Please try again."
                }

            # 9. Store pairing state
            expires_at = time.time() + 120.0
            self._current_pairing = {
                "phone": clean_phone,
                "code": code,
                "created_at": time.time(),
                "expires_at": expires_at,
                "status": "waiting_for_user",
                "instructions": "Open WhatsApp on your phone > Settings > Linked Devices > Link a Device > Link with phone number instead, then enter this code."
            }

            logger.info(f"Phone pairing code generated: {code} for phone {clean_phone[:4]}***")
            return {
                "success": True,
                "status": "code_generated",
                "code": code,
                "phone": clean_phone,
                "seconds_remaining": 120,
                "instructions": self._current_pairing["instructions"]
            }

    def get_pairing_status(self) -> Dict[str, Any]:
        """Polls current status of phone pairing operation."""
        with self._lock:
            driver = connection_monitor.get_driver()

            # 1. Check if authenticated
            if self.is_driver_logged_in(driver):
                self._current_pairing = None
                return {
                    "status": "authenticated",
                    "is_logged_in": True,
                    "message": "WhatsApp is successfully connected!"
                }

            if not self._current_pairing:
                return {
                    "status": "idle",
                    "is_logged_in": False,
                    "message": "No phone pairing in progress."
                }

            now = time.time()
            expires_at = self._current_pairing.get("expires_at", now)
            if now > expires_at:
                expired_phone = self._current_pairing.get("phone", "")
                self._current_pairing = None
                return {
                    "status": "expired",
                    "is_logged_in": False,
                    "phone": expired_phone,
                    "message": "Pairing code has expired. Please request a new code."
                }

            remaining = max(0, int(expires_at - now))
            return {
                "status": "waiting_for_user",
                "is_logged_in": False,
                "code": self._current_pairing.get("code"),
                "phone": self._current_pairing.get("phone"),
                "seconds_remaining": remaining,
                "instructions": self._current_pairing.get("instructions")
            }

    def cancel_pairing(self) -> Dict[str, Any]:
        """Cancels an active pairing session and refreshes WhatsApp Web."""
        with self._lock:
            self._current_pairing = None
            driver = connection_monitor.get_driver()
            if driver is not None:
                try:
                    driver.get("https://web.whatsapp.com")
                except Exception:
                    pass
            return {"success": True, "message": "Pairing session cancelled."}


# Singleton instance
whatsapp_pairing = WhatsAppPairingManager()
