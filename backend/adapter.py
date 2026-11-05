"""
Messaging Provider Abstraction and Adapters.
Isolates browser automation behind a clean provider interface, enabling
both real WhatsApp Web automation and lightweight mock simulations for tests.
"""

import os
import time
import random
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable

from logger import get_logger, mask_phone
from config_manager import AppConfig

logger = get_logger("MessagingAdapter")


class MessagingProvider(ABC):
    """Abstract interface defining required messaging automation capabilities."""

    @abstractmethod
    def initialize_browser(self, headless: bool = False) -> bool:
        """Starts or attaches to the browser session."""
        pass

    @abstractmethod
    def check_session_status(self) -> Dict[str, Any]:
        """Returns browser session readiness, QR login state, and active URL."""
        pass

    @abstractmethod
    def send_message(self, phone: str, message: str, attachment_path: Optional[str] = None, message_format: str = "image_with_caption", **kwargs) -> Dict[str, Any]:
        """Dispatches a single message."""
        pass

    @abstractmethod
    def send_batch(
        self,
        contacts: List[Dict[str, Any]],
        min_delay: float = 8.0,
        max_delay: float = 15.0,
        batch_size: int = 20,
        batch_cooldown_secs: float = 60.0,
        max_daily_limit: int = 100,
        global_attachment: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, Dict[str, Any], Dict[str, Any]], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> List[Dict[str, Any]]:
        """Dispatches a batch of messages with anti-ban pacing."""
        pass

    @abstractmethod
    def pause(self):
        """Temporarily pauses message dispatching."""
        pass

    @abstractmethod
    def resume(self):
        """Resumes paused dispatching."""
        pass

    @abstractmethod
    def stop(self):
        """Stops active dispatching immediately."""
        pass

    @abstractmethod
    def close(self):
        """Terminates the browser session."""
        pass


class WhatsAppWebAdapter(MessagingProvider):
    """Real Selenium-based WhatsApp Web automation adapter."""

    def __init__(self):
        self._engine = None
        self._browser_mgr = None

    def _ensure_engine(self, headless: bool = False):
        from backend.connection_monitor import connection_monitor
        from whatsapp_engine import WhatsAppEngine

        # 1. Prefer driver managed by connection_monitor if alive
        mon_driver = connection_monitor.get_driver()
        if mon_driver is not None:
            try:
                if len(mon_driver.window_handles) > 0:
                    if self._engine is None or getattr(self._engine, "driver", None) != mon_driver:
                        self._engine = WhatsAppEngine(mon_driver)
                    return
            except Exception:
                pass

        if self._engine is None:
            from browser_manager import BrowserManager
            self._browser_mgr = BrowserManager()
            driver = self._browser_mgr.start_browser(headless=headless)
            self._engine = WhatsAppEngine(driver)

    def initialize_browser(self, headless: bool = False) -> bool:
        try:
            self._ensure_engine(headless=headless)
            return True
        except Exception as e:
            logger.error(f"Failed to initialize WhatsApp browser: {e}")
            return False

    def check_session_status(self) -> Dict[str, Any]:
        if not self._engine or not self._engine.driver:
            return {"active": False, "logged_in": False, "status_text": "Browser not initialized"}
        try:
            current_url = self._engine.driver.current_url
            logged_in = self._engine.is_logged_in()
            return {
                "active": True,
                "logged_in": logged_in,
                "status_text": "Logged in & Ready" if logged_in else "Waiting for WhatsApp QR scan",
                "current_url": current_url
            }
        except Exception as e:
            return {"active": False, "logged_in": False, "status_text": f"Error: {e}"}

    def send_message(self, phone: str, message: str, attachment_path: Optional[str] = None, message_format: str = "image_with_caption", stage: str = "all", **kwargs) -> Dict[str, Any]:
        self._ensure_engine()
        return self._engine.send_message(
            phone=phone,
            message=message,
            attachment_path=attachment_path,
            message_format=message_format,
            stage=stage,
            **kwargs
        )

    def send_batch(
        self,
        contacts: List[Dict[str, Any]],
        min_delay: float = 8.0,
        max_delay: float = 15.0,
        batch_size: int = 20,
        batch_cooldown_secs: float = 60.0,
        max_daily_limit: int = 100,
        global_attachment: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, Dict[str, Any], Dict[str, Any]], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> List[Dict[str, Any]]:
        self._ensure_engine()
        return self._engine.send_batch(
            contacts=contacts,
            min_delay=min_delay,
            max_delay=max_delay,
            batch_size=batch_size,
            batch_cooldown_secs=batch_cooldown_secs,
            max_daily_limit=max_daily_limit,
            global_attachment=global_attachment,
            progress_callback=progress_callback,
            log_callback=log_callback
        )

    def pause(self):
        if self._engine:
            self._engine.pause()

    def resume(self):
        if self._engine:
            self._engine.resume()

    def stop(self):
        if self._engine:
            self._engine.stop()

    def close(self):
        from backend.connection_monitor import connection_monitor
        connection_monitor.stop_monitoring()
        if self._engine and hasattr(self._engine, "driver") and self._engine.driver:
            try:
                self._engine.driver.quit()
            except Exception:
                pass
        if self._browser_mgr:
            try:
                self._browser_mgr.close_browser()
            except Exception:
                pass
        self._engine = None
        self._browser_mgr = None


class MockMessagingProvider(MessagingProvider):
    """
    Lightweight simulated provider for automated tests, demonstrations,
    and fast verification without requiring Google Chrome.
    """

    def __init__(self, simulation_delay: float = 0.01, failure_rate: float = 0.0):
        self.simulation_delay = simulation_delay
        self.failure_rate = failure_rate
        self._is_paused = False
        self._is_stopped = False
        self._is_active = True

    def initialize_browser(self, headless: bool = False) -> bool:
        self._is_active = True
        return True

    def check_session_status(self) -> Dict[str, Any]:
        return {
            "active": self._is_active,
            "logged_in": True,
            "status_text": "Mock Provider (Simulated WhatsApp Web Connected)",
            "current_url": "https://web.whatsapp.com/mock"
        }

    def send_message(self, phone: str, message: str, attachment_path: Optional[str] = None, message_format: str = "image_with_caption", stage: str = "all", **kwargs) -> Dict[str, Any]:
        stage_cb = kwargs.get("stage_callback")
        if stage_cb:
            stage_cb("Simulating dispatch...")

        if self.simulation_delay > 0:
            time.sleep(self.simulation_delay)

        if stage == "text_only":
            if random.random() < self.failure_rate:
                return {
                    "status": "PARTIAL",
                    "media_status": "SENT",
                    "text_status": "FAILED",
                    "overall_status": "PARTIALLY_SENT",
                    "last_successful_stage": "media",
                    "recovery_eligibility": "retry_text_only",
                    "media_sent": True,
                    "text_sent": False,
                    "caption_sent": False,
                    "message_format": message_format,
                    "error": "Simulated follow-up text transmission timeout"
                }
            return {
                "status": "SENT",
                "media_status": "SENT",
                "text_status": "SENT",
                "overall_status": "SENT",
                "last_successful_stage": "text",
                "recovery_eligibility": "none",
                "media_sent": True,
                "text_sent": True,
                "caption_sent": False,
                "message_format": message_format,
                "error": None
            }

        if attachment_path:
            if not os.path.isfile(attachment_path):
                return {
                    "status": "FAILED",
                    "media_status": "FAILED",
                    "text_status": "NOT_ATTEMPTED",
                    "overall_status": "FAILED",
                    "last_successful_stage": "none",
                    "recovery_eligibility": "retry_all",
                    "media_sent": False,
                    "caption_sent": False,
                    "text_sent": False,
                    "error": f"Media file not found: {attachment_path}. No text was sent."
                }
            try:
                if os.path.getsize(attachment_path) == 0:
                    return {
                        "status": "FAILED",
                        "media_status": "FAILED",
                        "text_status": "NOT_ATTEMPTED",
                        "overall_status": "FAILED",
                        "last_successful_stage": "none",
                        "recovery_eligibility": "retry_all",
                        "media_sent": False,
                        "caption_sent": False,
                        "text_sent": False,
                        "error": f"Media failed: file is 0 bytes: {attachment_path}. No text was sent."
                    }
            except Exception:
                pass

        if random.random() < self.failure_rate:
            return {
                "status": "FAILED",
                "media_status": "FAILED" if attachment_path else "SKIPPED",
                "text_status": "FAILED",
                "overall_status": "FAILED",
                "last_successful_stage": "none",
                "recovery_eligibility": "retry_all",
                "media_sent": False,
                "caption_sent": False,
                "text_sent": False,
                "error": "Simulated transmission timeout"
            }

        has_media = bool(attachment_path)
        has_text = bool(message and message.strip())
        is_split = (message_format == "image_then_text")

        return {
            "status": "SENT",
            "media_status": "SENT" if has_media else "SKIPPED",
            "text_status": "SENT" if has_text else "SKIPPED",
            "overall_status": "SENT",
            "last_successful_stage": "text" if (is_split and has_text) else ("caption" if (has_media and has_text) else ("media" if has_media else "text")),
            "recovery_eligibility": "none",
            "media_sent": has_media,
            "caption_sent": bool(has_media and has_text and not is_split),
            "text_sent": bool(has_text and (not has_media or is_split)),
            "message_format": message_format,
            "error": None
        }

    def send_batch(
        self,
        contacts: List[Dict[str, Any]],
        min_delay: float = 8.0,
        max_delay: float = 15.0,
        batch_size: int = 20,
        batch_cooldown_secs: float = 60.0,
        max_daily_limit: int = 100,
        global_attachment: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, Dict[str, Any], Dict[str, Any]], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> List[Dict[str, Any]]:
        self._is_paused = False
        self._is_stopped = False
        results = []
        total = min(len(contacts), max_daily_limit)

        def log(msg: str):
            if log_callback:
                log_callback(msg)

        log(f"[MOCK] Starting simulated dispatch for {total} recipients...")

        for idx, contact in enumerate(contacts[:total], 1):
            if self._is_stopped:
                log("[MOCK] Simulation cancelled by user.")
                break

            while self._is_paused:
                time.sleep(0.05)
                if self._is_stopped:
                    break
            if self._is_stopped:
                break

            phone = contact.get("phone", "")
            name = contact.get("name", "Customer")
            msg = contact.get("message", "")
            attach = contact.get("attachment") or global_attachment

            masked = mask_phone(phone)
            log(f"[{idx}/{total}] [MOCK] Sending to {name} (+{masked})...")

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
                log(f"  -> [OK - MOCK SENT]")
            else:
                log(f"  -> [MOCK FAILED: {error}]")

            if progress_callback:
                progress_callback(idx, total, contact, record)

            # Minimal simulated delay between messages for test velocity
            if self.simulation_delay > 0:
                time.sleep(self.simulation_delay)

        log(f"[MOCK] Batch complete: {len(results)}/{total} executed.")
        return results

    def pause(self):
        self._is_paused = True

    def resume(self):
        self._is_paused = False

    def stop(self):
        self._is_stopped = True

    def close(self):
        self._is_active = False


# Aliases for backward compatibility and test conventions
BrowserEngineAdapter = WhatsAppWebAdapter
MockWhatsAppEngine = MockMessagingProvider

