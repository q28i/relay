"""
Intelligent Real-Time Connection Monitor and State Machine for WhatsApp Web.
Continuously observes browser session lifecycle, detects QR code presence,
monitors authentication transitions (syncing, connected), detects profile locks
and browser closure, and safely notifies background job workers without blocking.

Supported States:
- starting_browser
- opening_whatsapp
- waiting_for_qr
- syncing_account
- connected
- profile_locked
- browser_closed
- connection_lost
- timed_out
- unknown_error
"""

import os
import time
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
from selenium.webdriver.common.by import By

from browser_manager import (
    BrowserManager,
    ProfileLockedError,
    StaleLockArtifactError,
    BrowserExecutableNotFoundError,
    BrowserLaunchFailedError,
    UnsupportedProfileAutomationError
)
from config_manager import ConfigManager
from logger import get_logger

logger = get_logger("ConnectionMonitor")


class FailureCategory:
    TEMPORARY_DISCONNECT = "temporary_disconnect"
    BROWSER_STARTING = "browser_starting"
    HEALTHY_SESSION = "healthy_session"
    AUTHENTICATION_REQUIRED = "authentication_required"
    UNSUPPORTED_PROFILE = "unsupported_profile"
    MISSING_EXECUTABLE = "missing_executable"
    PERMANENT_LAUNCH_FAILURE = "permanent_launch_failure"


class ConnectionState:
    CHECKING_BROWSER = "checking_browser"
    RESOLVING_CONFLICT = "resolving_conflict"
    STARTING_BROWSER = "starting_browser"
    OPENING_WHATSAPP = "opening_whatsapp"
    WAITING_FOR_QR = "waiting_for_qr"
    SYNCING_ACCOUNT = "syncing_account"
    CONNECTED = "connected"
    PROFILE_LOCKED = "profile_locked"
    STALE_LOCK = "stale_lock"
    LAUNCH_FAILED = "launch_failed"
    UNSUPPORTED_PROFILE = "unsupported_profile"
    BROWSER_CLOSED = "browser_closed"
    CONNECTION_LOST = "connection_lost"
    TIMED_OUT = "timed_out"
    UNKNOWN_ERROR = "unknown_error"

    LABELS = {
        CHECKING_BROWSER: "Checking browser",
        RESOLVING_CONFLICT: "Resolving conflict",
        STARTING_BROWSER: "Starting browser",
        OPENING_WHATSAPP: "Opening WhatsApp Web",
        WAITING_FOR_QR: "Waiting for QR scan",
        SYNCING_ACCOUNT: "Syncing account",
        CONNECTED: "Connected",
        PROFILE_LOCKED: "Profile locked",
        STALE_LOCK: "Stale lock detected",
        LAUNCH_FAILED: "Launch failed",
        UNSUPPORTED_PROFILE: "Cannot be automated",
        BROWSER_CLOSED: "Browser closed",
        CONNECTION_LOST: "Connection lost",
        TIMED_OUT: "Timed out",
        UNKNOWN_ERROR: "Unknown error"
    }


class ConnectionMonitor:
    """
    Singleton connection manager and background observer.
    Maintains continuous visibility into browser and WhatsApp Web state.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._driver = None
        self._state = ConnectionState.BROWSER_CLOSED
        self._browser_key = "chrome"
        self._profile_dir = "__dedicated__"
        self._profile_name = "Dedicated WhatsApp Session"
        self._is_dedicated = True
        self._last_checked_at: Optional[str] = None
        self._current_activity = "Browser not started"
        self._error_detail = ""
        self._diagnostic_info: Dict[str, Any] = {}
        self._raw_profile_path = ""
        self._timeout_deadline = 0.0
        self._timeout_duration = 180.0  # 3 minutes for QR scan
        self._monitoring_active = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._listeners: List[Callable[[str, Dict[str, Any]], None]] = []
        self._timeline: List[Dict[str, Any]] = self._init_timeline()
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 3
        self._is_reconnecting = False
        self._failure_category: Optional[str] = None
        self._active_session_name = "Relay Automation"

        # Load initial saved configuration
        self._load_saved_profile_settings()

    def _load_saved_profile_settings(self):
        try:
            from backend.database import db
            pref = db.get_browser_profile_preference()
            cfg = ConfigManager().get_config()
            self._browser_key = getattr(cfg, "browser", "chrome") or "chrome"
            self._profile_dir = getattr(cfg, "profile_dir", "__dedicated__") or "__dedicated__"
            self._profile_name = getattr(cfg, "profile_name", "Dedicated WhatsApp Session") or "Dedicated WhatsApp Session"

            if pref and pref.get("remember_profile", 1):
                pref_mode = pref.get("selected_automation_mode") or pref.get("connection_mode") or "dedicated"
                if pref_mode == "existing_profile":
                    pers = pref.get("preferred_personal_profile") or {}
                    if pers.get("is_supported", False):
                        self._browser_key = pers.get("browser", "chrome")
                        self._profile_dir = pers.get("profile_dir", "Profile 10")
                        self._profile_name = pers.get("profile_name", "whatsapp auto")
                    else:
                        self._browser_key = "chrome"
                        self._profile_dir = "__dedicated__"
                        self._profile_name = "Relay Automation Session"
                elif pref_mode == "dedicated":
                    self._browser_key = "chrome"
                    self._profile_dir = "__dedicated__"
                    self._profile_name = "Relay Automation Session"

            self._is_dedicated = (self._profile_dir == "__dedicated__")
        except Exception:
            pass

    def _init_timeline(self) -> List[Dict[str, Any]]:
        return [
            {"id": "browser_launched", "label": "Browser launched", "status": "pending", "timestamp": None},
            {"id": "whatsapp_opened", "label": "WhatsApp Web opened", "status": "pending", "timestamp": None},
            {"id": "qr_detected", "label": "QR detected", "status": "pending", "timestamp": None},
            {"id": "login_confirmed", "label": "Login confirmed", "status": "pending", "timestamp": None},
            {"id": "connection_ready", "label": "Connection ready", "status": "pending", "timestamp": None}
        ]

    def _update_timeline_step(self, step_id: str, status: str):
        now_str = datetime.now().isoformat()
        for item in self._timeline:
            if item["id"] == step_id:
                item["status"] = status
                if status == "completed" and not item["timestamp"]:
                    item["timestamp"] = now_str
                break

    def update_profile_selection(
        self,
        browser_key: str,
        profile_dir: str,
        profile_name: str,
        is_dedicated: bool = False
    ):
        """Updates the target profile configuration and diagnoses compatibility immediately."""
        with self._lock:
            self._browser_key = browser_key
            self._profile_dir = profile_dir
            self._profile_name = profile_name
            self._is_dedicated = is_dedicated

            diag = BrowserManager.diagnose_profile(
                browser_key,
                profile_dir=profile_dir,
                is_dedicated=is_dedicated
            )
            self._diagnostic_info = diag
            self._raw_profile_path = diag.get("raw_profile_path", "")
            self._last_checked_at = datetime.now().isoformat()

            if diag.get("condition") == "UNSUPPORTED_DEFAULT_PROFILE" or not diag.get("is_automation_supported", True):
                self._state = ConnectionState.UNSUPPORTED_PROFILE
                self._failure_category = FailureCategory.UNSUPPORTED_PROFILE
                self._current_activity = "Selected Chrome profile cannot be automated with the current configuration."
                self._error_detail = diag.get("safe_error_reason", "Chrome 136+ security restrictions prevent remote debugging against Chrome's default user-data directory.")
                self._update_timeline_step("browser_launched", "failed")
            else:
                self._state = ConnectionState.BROWSER_CLOSED
                self._failure_category = FailureCategory.HEALTHY_SESSION
                self._current_activity = f"Selected {profile_name}. Click Start Session to connect."
                self._error_detail = ""

    def register_listener(self, callback: Callable[[str, Dict[str, Any]], None]):
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def unregister_listener(self, callback: Callable[[str, Dict[str, Any]], None]):
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _notify_listeners(self, state: str):
        snapshot = self.get_live_status()
        with self._lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(state, snapshot)
            except Exception as e:
                logger.debug(f"Error in connection listener: {e}")

    def is_connected(self) -> bool:
        with self._lock:
            return self._state == ConnectionState.CONNECTED and self._driver is not None

    def get_driver(self):
        with self._lock:
            return self._driver

    def set_driver_external(self, driver, browser_key: str = "chrome", profile_dir: str = "__dedicated__", profile_name: str = "Dedicated WhatsApp Session"):
        """Allows test harnesses or external callers to attach a mock or controlled driver."""
        with self._lock:
            self._driver = driver
            self._browser_key = browser_key
            self._profile_dir = profile_dir
            self._profile_name = profile_name
            self._is_dedicated = (profile_dir == "__dedicated__")
            self._monitoring_active = True
            self._state = ConnectionState.STARTING_BROWSER
            self._current_activity = "Attached driver. Observing connection..."
            self._update_timeline_step("browser_launched", "completed")
            self._start_observation_loop()

    def start_monitoring(
        self,
        browser_key: Optional[str] = None,
        profile_dir: Optional[str] = None,
        profile_name: Optional[str] = None,
        headless: bool = False,
        ignore_stale_lock: bool = False,
        force_personal: bool = False,
        force_restart: bool = False
    ) -> Dict[str, Any]:
        """
        Launches or attaches to the browser session and starts continuous non-blocking observation.
        Features automatic conflict resolution for previous Relay sessions, safe user prompting
        for personal browser instances, and reuse of existing healthy sessions.
        """
        from backend.session_lifecycle import session_lifecycle

        with self._lock:
            # Check if already connected with a live healthy driver
            if not force_restart and self._driver is not None and self._state == ConnectionState.CONNECTED:
                if session_lifecycle.is_session_healthy(self._driver):
                    logger.info("Reusing existing healthy Relay browser session without restarting.")
                    self._last_checked_at = datetime.now().isoformat()
                    return self.get_live_status()

            # Close any previous broken session
            if self._driver is not None:
                try:
                    self._driver.quit()
                except Exception:
                    pass
                self._driver = None

            self._timeline = self._init_timeline()
            self._load_saved_profile_settings()

            if browser_key:
                self._browser_key = browser_key
            if profile_dir:
                self._profile_dir = profile_dir
                self._is_dedicated = (profile_dir == "__dedicated__")
            if profile_name:
                self._profile_name = profile_name

            b_info = BrowserManager.BROWSERS.get(self._browser_key, {})
            b_name = b_info.get("name", self._browser_key.title())

            # Perform comprehensive pre-launch diagnosis
            diag = BrowserManager.diagnose_profile(
                self._browser_key,
                profile_dir=self._profile_dir,
                is_dedicated=self._is_dedicated
            )
            self._diagnostic_info = diag
            self._raw_profile_path = diag.get("raw_profile_path", "")
            self._last_checked_at = datetime.now().isoformat()

            # 0. Check if profile automation is prohibited by modern Chromium security restrictions
            if diag.get("condition") == "UNSUPPORTED_DEFAULT_PROFILE" or not diag.get("is_automation_supported", True):
                self._state = ConnectionState.UNSUPPORTED_PROFILE
                self._failure_category = FailureCategory.UNSUPPORTED_PROFILE
                self._current_activity = "Selected Chrome profile cannot be automated with the current configuration."
                self._error_detail = diag.get("safe_error_reason", "Chrome 136+ security restrictions prevent remote debugging against Chrome's default user-data directory.")
                self._update_timeline_step("browser_launched", "failed")
                self._monitoring_active = False
                self._notify_listeners(self._state)
                return self.get_live_status()

            # 1. Check if browser binary is missing
            if not diag.get("browser_exe_exists", True) or diag.get("condition") == "MISSING_EXECUTABLE":
                self._state = ConnectionState.LAUNCH_FAILED
                self._failure_category = FailureCategory.MISSING_EXECUTABLE
                self._current_activity = "Couldn't start the selected browser profile."
                self._error_detail = diag.get("safe_error_reason", f"Executable for {b_name} not found on disk.")
                self._update_timeline_step("browser_launched", "failed")
                self._monitoring_active = False
                self._notify_listeners(self._state)
                return self.get_live_status()

            # 2. Check for running browser process conflicts and resolve automatically
            if diag.get("is_locked"):
                conflict_type = diag.get("conflict_type", "personal_browser")
                if conflict_type == "relay_owned":
                    logger.info(f"Relay-owned conflict detected for {b_name} profile {self._profile_dir}. Resolving automatically...")
                    self._state = ConnectionState.RESOLVING_CONFLICT
                    self._current_activity = "Previous Relay session detected. Resolving conflict..."
                    self._notify_listeners(self._state)
                    session_lifecycle.resolve_conflict(
                        self._browser_key,
                        profile_dir=self._profile_dir,
                        is_dedicated=self._is_dedicated,
                        force_personal=False
                    )
                    time.sleep(0.5)
                    diag = BrowserManager.diagnose_profile(
                        self._browser_key,
                        profile_dir=self._profile_dir,
                        is_dedicated=self._is_dedicated
                    )
                    self._diagnostic_info = diag
                elif conflict_type == "personal_browser" and force_personal:
                    logger.info(f"User confirmed closing personal {b_name} window. Closing gracefully...")
                    self._state = ConnectionState.RESOLVING_CONFLICT
                    self._current_activity = "Closing confirmed personal browser window..."
                    self._notify_listeners(self._state)
                    session_lifecycle.resolve_conflict(
                        self._browser_key,
                        profile_dir=self._profile_dir,
                        is_dedicated=self._is_dedicated,
                        force_personal=True
                    )
                    time.sleep(0.5)
                    diag = BrowserManager.diagnose_profile(
                        self._browser_key,
                        profile_dir=self._profile_dir,
                        is_dedicated=self._is_dedicated
                    )
                    self._diagnostic_info = diag

            # If still locked after resolution attempt
            if diag.get("is_locked"):
                self._state = ConnectionState.PROFILE_LOCKED
                self._current_activity = diag.get("user_message", f"Selected profile is currently open in {b_name}.")
                if diag.get("conflict_type") == "personal_browser":
                    self._error_detail = f"Close {b_name} completely to use this profile for automated messaging, or click 'Restart browser' to close the open window, or use a dedicated Relay session."
                elif diag.get("has_visible_window"):
                    self._error_detail = f"Close {b_name} completely to use this profile for automated messaging, or use a dedicated Relay session instead."
                else:
                    self._error_detail = f"A background {b_name} process is running. Close background processes or use a dedicated Relay session instead."
                self._update_timeline_step("browser_launched", "pending")
                self._notify_listeners(self._state)
                return self.get_live_status()

            # 3. Check for stale lock artifact (no process detected)
            if diag.get("is_stale_lock") and not ignore_stale_lock:
                self._state = ConnectionState.STALE_LOCK
                self._current_activity = diag.get("user_message", f"Stale lock file found, but no running {b_name} process was detected.")
                self._error_detail = "A lock file artifact exists from a previous run, but no matching browser process is active. You can try launching anyway, choose another profile, or use a dedicated session."
                self._update_timeline_step("browser_launched", "pending")
                self._notify_listeners(self._state)
                return self.get_live_status()

            # 4. Ready to launch browser
            self._state = ConnectionState.STARTING_BROWSER
            self._current_activity = "Launching browser process..."
            self._error_detail = ""
            self._update_timeline_step("browser_launched", "current")
            self._timeout_deadline = time.time() + self._timeout_duration
            self._monitoring_active = True
            self._timeout_deadline = time.time() + self._timeout_duration
            self._monitoring_active = True

            try:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                target_p = {
                    "dir": self._profile_dir,
                    "name": self._profile_name,
                    "is_dedicated": self._is_dedicated,
                    "path": os.path.join(base_dir, "whatsapp_browser_session") if self._is_dedicated else b_info.get("user_data_path", "")
                }
                if self._is_dedicated:
                    os.makedirs(target_p["path"], exist_ok=True)

                driver = BrowserManager.launch_driver(
                    self._browser_key,
                    target_p,
                    headless=headless,
                    ignore_stale_lock=ignore_stale_lock
                )
                self._driver = driver
                self._update_timeline_step("browser_launched", "completed")

                # Navigate to WhatsApp Web
                self._state = ConnectionState.OPENING_WHATSAPP
                self._current_activity = "Opening https://web.whatsapp.com..."
                self._last_checked_at = datetime.now().isoformat()
                self._update_timeline_step("whatsapp_opened", "current")

                driver.set_page_load_timeout(35)
                driver.get("https://web.whatsapp.com")
                self._update_timeline_step("whatsapp_opened", "completed")

            except ProfileLockedError as ple:
                self._state = ConnectionState.PROFILE_LOCKED
                self._current_activity = str(ple)
                self._error_detail = f"Close {b_name} completely to use this profile for automated messaging, or use a dedicated Relay session instead."
                self._update_timeline_step("browser_launched", "pending")
                self._last_checked_at = datetime.now().isoformat()
                self._notify_listeners(self._state)
                return self.get_live_status()

            except StaleLockArtifactError as sle:
                self._state = ConnectionState.STALE_LOCK
                self._current_activity = str(sle)
                self._error_detail = "A lock file artifact exists from a previous run. You can choose 'Try launch anyway'."
                self._update_timeline_step("browser_launched", "pending")
                self._last_checked_at = datetime.now().isoformat()
                self._notify_listeners(self._state)
                return self.get_live_status()

            except UnsupportedProfileAutomationError as upe:
                self._state = ConnectionState.UNSUPPORTED_PROFILE
                self._failure_category = FailureCategory.UNSUPPORTED_PROFILE
                self._current_activity = "Selected Chrome profile cannot be automated with the current configuration."
                self._error_detail = upe.safe_reason or str(upe)
                self._diagnostic_info["safe_error_reason"] = upe.safe_reason or str(upe)
                self._diagnostic_info["technical_detail"] = upe.technical_detail
                self._update_timeline_step("browser_launched", "failed")
                self._last_checked_at = datetime.now().isoformat()
                self._monitoring_active = False
                self._notify_listeners(self._state)
                return self.get_live_status()

            except BrowserExecutableNotFoundError as bne:
                self._state = ConnectionState.LAUNCH_FAILED
                self._failure_category = FailureCategory.MISSING_EXECUTABLE
                self._current_activity = "Couldn't start the selected browser profile."
                self._error_detail = str(bne)
                self._diagnostic_info["safe_error_reason"] = str(bne)
                self._update_timeline_step("browser_launched", "failed")
                self._last_checked_at = datetime.now().isoformat()
                self._monitoring_active = False
                self._notify_listeners(self._state)
                return self.get_live_status()

            except BrowserLaunchFailedError as blf:
                self._state = ConnectionState.LAUNCH_FAILED
                self._failure_category = FailureCategory.PERMANENT_LAUNCH_FAILURE
                self._current_activity = "Couldn't start the selected browser profile."
                self._error_detail = blf.safe_reason or str(blf)
                self._diagnostic_info["safe_error_reason"] = blf.safe_reason or str(blf)
                self._diagnostic_info["technical_detail"] = blf.technical_detail
                self._update_timeline_step("browser_launched", "failed")
                self._last_checked_at = datetime.now().isoformat()
                self._monitoring_active = False
                self._notify_listeners(self._state)
                return self.get_live_status()

            except Exception as e:
                self._state = ConnectionState.LAUNCH_FAILED
                self._current_activity = "Couldn't start the selected browser profile."
                self._error_detail = f"Launch error: {str(e)}"
                self._diagnostic_info["safe_error_reason"] = f"Unexpected launch failure: {str(e)}"
                self._update_timeline_step("browser_launched", "failed")
                self._last_checked_at = datetime.now().isoformat()
                self._notify_listeners(self._state)
                return self.get_live_status()

            # Start observation thread
            self._start_observation_loop()
            return self.get_live_status()

            # Start observation thread
            self._start_observation_loop()
            return self.get_live_status()

    def _start_observation_loop(self):
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        self._monitoring_active = True
        self._monitor_thread = threading.Thread(
            target=self._observation_worker,
            daemon=True,
            name="ConnectionMonitor-Observer"
        )
        self._monitor_thread.start()

    def _observation_worker(self):
        """Continuous background observation loop checking active driver states."""
        logger.info("Started background WhatsApp connection observation worker.")

        while self._monitoring_active:
            try:
                time.sleep(1.8)
                with self._lock:
                    if not self._monitoring_active or not self._driver:
                        break
                    driver = self._driver

                # Check 1: Window closed or process disconnected?
                window_lost = False
                try:
                    handles = driver.window_handles
                    if len(handles) == 0:
                        window_lost = True
                except Exception:
                    window_lost = True

                if window_lost:
                    if self._monitoring_active and self._reconnect_attempts < self._max_reconnect_attempts and not self._is_reconnecting:
                        self._reconnect_attempts += 1
                        self._is_reconnecting = True
                        backoff_sec = min(10.0, 2.0 * self._reconnect_attempts)
                        logger.warning(f"Connection lost. Initiating auto-reconnect attempt {self._reconnect_attempts}/{self._max_reconnect_attempts} in {backoff_sec:.1f}s...")
                        self._transition_to(
                            ConnectionState.CONNECTION_LOST,
                            f"Connection lost. Auto-reconnecting ({self._reconnect_attempts}/{self._max_reconnect_attempts})...",
                            error_detail=f"Auto-reconnect attempt {self._reconnect_attempts} of {self._max_reconnect_attempts}"
                        )
                        time.sleep(backoff_sec)
                        try:
                            self.start_monitoring(headless=False, force_restart=True)
                            self._is_reconnecting = False
                            continue
                        except Exception as rx:
                            logger.error(f"Auto-reconnect attempt {self._reconnect_attempts} failed: {rx}")
                            self._is_reconnecting = False
                            continue
                    else:
                        self._reconnect_attempts = 0
                        self._transition_to(
                            ConnectionState.BROWSER_CLOSED,
                            "Browser window was closed or disconnected."
                        )
                        break

                # Check 2: Timeout check
                with self._lock:
                    deadline = self._timeout_deadline
                    cur_st = self._state

                if deadline > 0 and time.time() > deadline and cur_st in (ConnectionState.WAITING_FOR_QR, ConnectionState.OPENING_WHATSAPP, ConnectionState.STARTING_BROWSER):
                    self._transition_to(
                        ConnectionState.TIMED_OUT,
                        "Connection verification timed out. Restart connection to try again."
                    )
                    break

                # Check 3: Current URL check
                try:
                    cur_url = driver.current_url or ""
                    if "web.whatsapp.com" not in cur_url and cur_st != ConnectionState.STARTING_BROWSER:
                        try:
                            driver.get("https://web.whatsapp.com")
                        except Exception:
                            pass
                except Exception:
                    pass

                # Check 4: Probe DOM non-destructively
                is_logged_in = False
                is_qr_present = False
                is_syncing = False

                # 4A. Check QR Code Presence first (prevents false positive authentication)
                qr_selectors = [
                    (By.CSS_SELECTOR, "canvas[aria-label*='Scan']"),
                    (By.CSS_SELECTOR, "canvas"),
                    (By.CSS_SELECTOR, "div[data-ref]")
                ]
                for by_type, query in qr_selectors:
                    try:
                        elems = driver.find_elements(by_type, query)
                        if any(e.is_displayed() for e in elems):
                            is_qr_present = True
                            break
                    except Exception:
                        pass

                # 4B. If QR code is not displayed, check Chat List and Active Chat Panes
                if not is_qr_present:
                    from whatsapp_engine import WhatsAppEngine
                    for by_type, query in WhatsAppEngine.CHAT_LIST_SELECTORS:
                        try:
                            elems = driver.find_elements(by_type, query)
                            if any(e.is_displayed() for e in elems):
                                is_logged_in = True
                                break
                        except Exception:
                            pass

                    if not is_logged_in:
                        # Specific WhatsApp conversation view elements.
                        # Generic 'header' and 'footer' tags alone MUST NOT establish authentication.
                        specific_chat_selectors = [
                            (By.ID, "main"),
                            (By.CSS_SELECTOR, "div#main"),
                            (By.CSS_SELECTOR, "div[data-testid='conversation-panel-wrapper']"),
                            (By.CSS_SELECTOR, "div[contenteditable='true'][data-tab='10']"),
                        ]
                        for by_type, query in specific_chat_selectors:
                            try:
                                elems = driver.find_elements(by_type, query)
                                if any(e.is_displayed() for e in elems):
                                    is_logged_in = True
                                    break
                            except Exception:
                                pass

                if is_logged_in:
                    self._reconnect_attempts = 0
                    self._is_reconnecting = False
                    self._update_timeline_step("login_confirmed", "completed")
                    self._update_timeline_step("connection_ready", "completed")
                    try:
                        from backend.database import db
                        db.update_browser_last_connected(
                            browser=self._browser_key,
                            profile_dir=self._profile_dir,
                            profile_name=self._profile_name,
                            mode="dedicated" if self._is_dedicated else "existing_profile",
                            was_authenticated=True
                        )
                    except Exception:
                        pass
                    if cur_st != ConnectionState.CONNECTED:
                        self._transition_to(
                            ConnectionState.CONNECTED,
                            "WhatsApp Web session active and ready for messaging."
                        )
                    else:
                        with self._lock:
                            self._last_checked_at = datetime.now().isoformat()
                            self._current_activity = "Session verified active. Continuous monitoring running."
                    # Once connected, keep observing at a gentler cadence
                    time.sleep(2.0)
                    continue

                # 4B. Check Account Syncing / Loading
                sync_selectors = [
                    (By.CSS_SELECTOR, "div[data-animate-progress]"),
                    (By.CSS_SELECTOR, "progress"),
                    (By.XPATH, "//div[contains(text(), 'Downloading messages')]"),
                    (By.XPATH, "//div[contains(text(), 'Starting chat')]"),
                    (By.XPATH, "//div[contains(text(), 'Loading your chats')]")
                ]
                for by_type, query in sync_selectors:
                    try:
                        elems = driver.find_elements(by_type, query)
                        if any(e.is_displayed() for e in elems):
                            is_syncing = True
                            break
                    except Exception:
                        pass

                if is_syncing:
                    self._update_timeline_step("login_confirmed", "completed")
                    self._transition_to(
                        ConnectionState.SYNCING_ACCOUNT,
                        "Syncing messages and account data with WhatsApp..."
                    )
                    continue

                # 4C. Check QR Code Presence
                qr_selectors = [
                    (By.CSS_SELECTOR, "canvas[aria-label*='Scan']"),
                    (By.CSS_SELECTOR, "canvas"),
                    (By.CSS_SELECTOR, "div[data-ref]")
                ]
                for by_type, query in qr_selectors:
                    try:
                        elems = driver.find_elements(by_type, query)
                        if any(e.is_displayed() for e in elems):
                            is_qr_present = True
                            break
                    except Exception:
                        pass

                if is_qr_present:
                    self._update_timeline_step("qr_detected", "completed")
                    remaining = max(0, int(deadline - time.time())) if deadline > 0 else 0
                    activity_msg = f"Waiting for QR scan — checking again in 2 seconds (Timeout: {remaining}s)"
                    if cur_st != ConnectionState.WAITING_FOR_QR:
                        self._transition_to(ConnectionState.WAITING_FOR_QR, activity_msg)
                    else:
                        with self._lock:
                            self._last_checked_at = datetime.now().isoformat()
                            self._current_activity = activity_msg
                    continue

                # In transit or loading initial page
                with self._lock:
                    self._last_checked_at = datetime.now().isoformat()
                    if self._state == ConnectionState.OPENING_WHATSAPP:
                        self._current_activity = "Loading WhatsApp Web interface..."

            except Exception as e:
                logger.debug(f"Observer tick error: {e}")
                time.sleep(1.0)

        logger.info("Connection observation loop ended.")

    def _transition_to(self, new_state: str, activity_message: str, error_detail: str = ""):
        with self._lock:
            old_state = self._state
            self._state = new_state
            self._current_activity = activity_message
            if error_detail:
                self._error_detail = error_detail
            self._last_checked_at = datetime.now().isoformat()

            # Update persisted config connection_status
            try:
                cm = ConfigManager()
                cfg = cm.get_config()
                cfg.connection_status = ConnectionState.LABELS.get(new_state, new_state)
                cm.save_config(cfg)
            except Exception:
                pass

        logger.info(f"Connection state transition: {old_state} -> {new_state} ({activity_message})")
        self._notify_listeners(new_state)

    def stop_monitoring(self):
        """Stops the observer loop and closes the driver cleanly."""
        with self._lock:
            self._monitoring_active = False
            self._reconnect_attempts = 0
            self._is_reconnecting = False
            driver = self._driver
            self._driver = None
            self._state = ConnectionState.BROWSER_CLOSED
            self._current_activity = "Connection stopped by operator."
            self._last_checked_at = datetime.now().isoformat()

        if driver:
            try:
                driver.quit()
            except Exception:
                pass

        self._notify_listeners(ConnectionState.BROWSER_CLOSED)

    def perform_action(self, action: str) -> Dict[str, Any]:
        """
        Executes recoverable control actions according to the current state:
        - open_whatsapp: focuses or navigates to WhatsApp Web
        - open_session: opens or brings session window to focus
        - cancel: cancels waiting/starting and cleanly closes browser
        - change_profile: returns instructions to open picker
        - refresh_status: forces an immediate observation probe
        - try_again: re-checks profile lock or restarts
        - use_dedicated: switches to dedicated session
        - restart_connection: stops broken session and relaunches fresh
        """
        act = action.lower().strip()
        logger.info(f"Executing connection control action: {act} (current state: {self._state})")

        if act in ("open_whatsapp", "open_session"):
            if self._driver is None or self._state in (ConnectionState.BROWSER_CLOSED, ConnectionState.CONNECTION_LOST, ConnectionState.TIMED_OUT):
                return self.start_monitoring(headless=False)
            try:
                self._driver.get("https://web.whatsapp.com")
                return {"success": True, "message": "WhatsApp Web navigation requested.", "connection": self.get_live_status()}
            except Exception as e:
                return self.start_monitoring(headless=False)

        elif act == "cancel":
            self.stop_monitoring()
            return {"success": True, "message": "Connection attempt cancelled.", "connection": self.get_live_status()}

        elif act == "refresh_status":
            with self._lock:
                self._last_checked_at = datetime.now().isoformat()
            if self._driver is None:
                # Trigger a quick probe check
                probe = BrowserManager.check_profile_session(self._browser_key, self._profile_dir)
                status_raw = probe.get("status", "Could not verify")
                if probe.get("is_locked"):
                    self._state = ConnectionState.PROFILE_LOCKED
                elif probe.get("logged_in"):
                    self._state = ConnectionState.CONNECTED
                elif status_raw == "Needs QR sign-in":
                    self._state = ConnectionState.WAITING_FOR_QR
                else:
                    self._state = ConnectionState.BROWSER_CLOSED
                self._current_activity = probe.get("detail", "Status refreshed.")
            return {"success": True, "message": "Status refreshed.", "connection": self.get_live_status()}

        elif act in ("start_session", "start"):
            return self.start_monitoring(headless=False)

        elif act in ("confirm_personal_restart", "confirm_restart"):
            return self.start_monitoring(headless=False, force_personal=True)

        elif act == "try_again":
            return self.start_monitoring(headless=False)

        elif act == "try_launch_anyway":
            return self.start_monitoring(headless=False, ignore_stale_lock=True)

        elif act == "view_details":
            status = self.get_live_status()
            return {
                "success": True,
                "message": "Diagnostic details retrieved.",
                "details": status.get("diagnostic_details", {}),
                "connection": status
            }

        elif act in ("use_dedicated", "use_persistent_relay"):
            self._active_session_name = "Relay Automation"
            try:
                cm = ConfigManager()
                cfg = cm.get_config()
                cfg.browser = "chrome"
                cfg.profile_dir = "__dedicated__"
                cfg.profile_name = "Relay Automation Session"
                cm.save_config(cfg)
                from backend.database import db
                db.save_browser_profile_preference(
                    browser_id="chrome",
                    profile_display_name="Relay Automation Session",
                    canonical_profile_dir="__dedicated__",
                    connection_mode="dedicated"
                )
            except Exception as e:
                logger.warning(f"Failed to persist dedicated preference in action: {e}")
            return self.start_monitoring(browser_key="chrome", profile_dir="__dedicated__", profile_name="Relay Automation", headless=False, force_restart=True)

        elif act == "disconnect":
            self.stop_monitoring()
            return {"success": True, "message": "Messaging session disconnected.", "connection": self.get_live_status()}

        elif act == "test_connection":
            from backend.routers.browser import test_browser_connection
            res = test_browser_connection(self._browser_key, self._profile_dir)
            return {"success": res.get("success", False), "result": res, "connection": self.get_live_status()}

        elif act == "restart_connection":
            self.stop_monitoring()
            time.sleep(0.5)
            return self.start_monitoring(headless=False)

        elif act == "simulate_waiting_qr":
            with self._lock:
                self._state = ConnectionState.WAITING_FOR_QR
                self._current_activity = "Waiting for QR scan — checking again in 2s"
                now_str = datetime.now().isoformat()
                self._timeline[0]["status"] = "completed"
                self._timeline[0]["timestamp"] = now_str
                self._timeline[1]["status"] = "completed"
                self._timeline[1]["timestamp"] = now_str
                self._timeline[2]["status"] = "current"
                self._timeline[2]["timestamp"] = now_str
                self._timeline[3]["status"] = "pending"
                self._timeline[4]["status"] = "pending"
                self._last_checked_at = now_str
            self._notify_listeners(ConnectionState.WAITING_FOR_QR)
            return {"success": True, "message": "Simulated waiting_for_qr state.", "connection": self.get_live_status()}

        elif act == "simulate_connected":
            with self._lock:
                self._state = ConnectionState.CONNECTED
                self._current_activity = "WhatsApp Web connected and ready"
                now_str = datetime.now().isoformat()
                for step in self._timeline:
                    step["status"] = "completed"
                    if not step.get("timestamp"):
                        step["timestamp"] = now_str
                self._last_checked_at = now_str
            self._notify_listeners(ConnectionState.CONNECTED)
            return {"success": True, "message": "Simulated connected state.", "connection": self.get_live_status()}

        elif act == "simulate_browser_closed":
            with self._lock:
                self._state = ConnectionState.BROWSER_CLOSED
                self._current_activity = "Browser closed by user"
                self._last_checked_at = datetime.now().isoformat()
            self._notify_listeners(ConnectionState.BROWSER_CLOSED)
            return {"success": True, "message": "Simulated browser_closed state.", "connection": self.get_live_status()}

        elif act == "simulate_profile_locked":
            with self._lock:
                self._state = ConnectionState.PROFILE_LOCKED
                self._current_activity = "Selected profile is currently open in a Google Chrome window."
                self._error_detail = "Close Google Chrome completely to use this profile for automated messaging, or use a dedicated Relay session instead."
                now_str = datetime.now().isoformat()
                self._timeline = self._init_timeline()
                self._last_checked_at = now_str
                self._diagnostic_info = {
                    "condition": "ACTIVE_VISIBLE_PROCESS",
                    "safe_error_reason": "Process 28144 (Google Chrome) has an active visible window using this profile.",
                    "browser_name": "Google Chrome",
                    "short_profile_path": "~/AppData/Local/Google/Chrome/User Data/Work Profile",
                    "matching_pids": [28144],
                    "has_visible_window": True,
                    "browser_exe_exists": True,
                    "technical_detail": "EnumWindows matched visible top-level window for PID 28144"
                }
            self._notify_listeners(ConnectionState.PROFILE_LOCKED)
            return {"success": True, "message": "Simulated profile_locked state.", "connection": self.get_live_status()}

        elif act == "simulate_stale_lock":
            with self._lock:
                self._state = ConnectionState.STALE_LOCK
                self._current_activity = "Stale lock file found, but no running Google Chrome process was detected."
                self._error_detail = "A lock file artifact exists from a previous run, but no matching browser process is active. You can try launching anyway, choose another profile, or use a dedicated session."
                now_str = datetime.now().isoformat()
                self._timeline = self._init_timeline()
                self._last_checked_at = now_str
                self._diagnostic_info = {
                    "condition": "STALE_LOCK_ARTIFACT",
                    "safe_error_reason": "A lock file artifact exists from a previous run, but no matching browser process is active.",
                    "browser_name": "Google Chrome",
                    "short_profile_path": "~/AppData/Local/Google/Chrome/User Data/Default",
                    "matching_pids": [],
                    "has_visible_window": False,
                    "browser_exe_exists": True,
                    "technical_detail": "Lockfile present on disk at User Data/lockfile"
                }
            self._notify_listeners(ConnectionState.STALE_LOCK)
            return {"success": True, "message": "Simulated stale_lock state.", "connection": self.get_live_status()}

        elif act == "simulate_launch_failed":
            with self._lock:
                self._state = ConnectionState.LAUNCH_FAILED
                self._current_activity = "Couldn't start the selected browser profile."
                self._error_detail = "Browser process exited before remote debugging port opened. Modern Chromium security restricts remote debugging on default user profiles."
                now_str = datetime.now().isoformat()
                self._timeline = self._init_timeline()
                self._timeline[0]["status"] = "failed"
                self._timeline[0]["timestamp"] = now_str
                self._last_checked_at = now_str
                self._diagnostic_info = {
                    "condition": "LAUNCH_FAILED",
                    "safe_error_reason": "Browser process exited before remote debugging port opened. Modern Chromium security restricts remote debugging on default user profiles.",
                    "browser_name": "Google Chrome",
                    "short_profile_path": "~/AppData/Local/Google/Chrome/User Data/Default",
                    "matching_pids": [],
                    "has_visible_window": False,
                    "browser_exe_exists": True,
                    "technical_detail": "SessionNotCreatedException: DevToolsActivePort file does not exist"
                }
            self._notify_listeners(ConnectionState.LAUNCH_FAILED)
            return {"success": True, "message": "Simulated launch_failed state.", "connection": self.get_live_status()}

        else:
            return {"success": False, "message": f"Unknown action '{act}'", "connection": self.get_live_status()}

    def get_live_status(self) -> Dict[str, Any]:
        """Returns the full reactive snapshot for the unified connection card."""
        with self._lock:
            state = self._state
            state_label = ConnectionState.LABELS.get(state, state.title())
            activity = self._current_activity
            last_checked = self._last_checked_at or datetime.now().isoformat()
            error_detail = self._error_detail
            timeline = [dict(t) for t in self._timeline]
            b_key = self._browser_key
            p_dir = self._profile_dir
            p_name = self._profile_name
            is_dedicated = self._is_dedicated
            has_driver = self._driver is not None

            # Dynamic actions by state
            actions = []
            if state == ConnectionState.UNSUPPORTED_PROFILE:
                actions = [
                    {"id": "use_dedicated", "label": "Use persistent Relay session", "primary": True},
                    {"id": "view_details", "label": "View details", "variant": "secondary"},
                    {"id": "change_profile", "label": "Change profile", "variant": "secondary"}
                ]
            elif state == ConnectionState.WAITING_FOR_QR:
                actions = [
                    {"id": "open_whatsapp", "label": "Open WhatsApp Web", "primary": True},
                    {"id": "cancel", "label": "Cancel", "variant": "secondary"},
                    {"id": "change_profile", "label": "Change profile", "variant": "secondary"}
                ]
            elif state == ConnectionState.CONNECTED:
                actions = [
                    {"id": "open_session", "label": "Open session", "primary": True},
                    {"id": "test_connection", "label": "Test connection", "variant": "secondary"},
                    {"id": "disconnect", "label": "Disconnect", "variant": "secondary"}
                ]
            elif state == ConnectionState.PROFILE_LOCKED:
                is_personal = self._diagnostic_info.get("conflict_type") == "personal_browser"
                actions = [
                    {"id": "use_dedicated", "label": "Use persistent Relay session", "primary": True},
                    {"id": "confirm_personal_restart", "label": "Restart browser (close open window)", "variant": "secondary"} if is_personal else {"id": "try_again", "label": "Restart session", "variant": "secondary"},
                    {"id": "change_profile", "label": "Change profile", "variant": "secondary"},
                    {"id": "view_details", "label": "View details", "variant": "secondary"}
                ]
            elif state == ConnectionState.STALE_LOCK:
                actions = [
                    {"id": "try_launch_anyway", "label": "Try launch anyway", "primary": True},
                    {"id": "use_dedicated", "label": "Use persistent Relay session", "variant": "secondary"},
                    {"id": "change_profile", "label": "Change profile", "variant": "secondary"},
                    {"id": "view_details", "label": "View details", "variant": "secondary"}
                ]
            elif state == ConnectionState.LAUNCH_FAILED:
                actions = [
                    {"id": "use_dedicated", "label": "Use persistent Relay session", "primary": True},
                    {"id": "view_details", "label": "View details", "variant": "secondary"},
                    {"id": "change_profile", "label": "Change profile", "variant": "secondary"}
                ]
            elif state in (ConnectionState.BROWSER_CLOSED, ConnectionState.CONNECTION_LOST, ConnectionState.TIMED_OUT, ConnectionState.UNKNOWN_ERROR):
                if self._diagnostic_info.get("condition") == "UNSUPPORTED_DEFAULT_PROFILE" or not self._diagnostic_info.get("is_automation_supported", True):
                    actions = [
                        {"id": "use_dedicated", "label": "Use persistent Relay session", "primary": True},
                        {"id": "view_details", "label": "View details", "variant": "secondary"},
                        {"id": "change_profile", "label": "Change profile", "variant": "secondary"}
                    ]
                else:
                    actions = [
                        {"id": "start_session", "label": "Start Session", "primary": True},
                        {"id": "test_connection", "label": "Test Connection", "variant": "secondary"},
                        {"id": "change_profile", "label": "Change profile", "variant": "secondary"}
                    ]
            else:  # STARTING_BROWSER, OPENING_WHATSAPP, SYNCING_ACCOUNT
                actions = [
                    {"id": "cancel", "label": "Cancel", "variant": "secondary"}
                ]

            b_info = BrowserManager.BROWSERS.get(b_key, {})
            b_name = b_info.get("name", b_key.title())

            # Prepare safe diagnostic details (no exposing sensitive raw paths)
            diag_det = {
                "condition": self._diagnostic_info.get("condition", "AVAILABLE" if state == ConnectionState.CONNECTED else "UNKNOWN"),
                "safe_error_reason": self._diagnostic_info.get("safe_error_reason", error_detail or "No errors reported."),
                "browser_name": b_name,
                "profile_path": self._diagnostic_info.get("short_profile_path", BrowserManager.shorten_path(p_dir)),
                "matching_pids": self._diagnostic_info.get("matching_pids", []),
                "relay_pids": self._diagnostic_info.get("relay_pids", []),
                "personal_pids": self._diagnostic_info.get("personal_pids", []),
                "conflict_type": self._diagnostic_info.get("conflict_type", "none"),
                "prompt_required": self._diagnostic_info.get("conflict_type") == "personal_browser" and state == ConnectionState.PROFILE_LOCKED,
                "has_visible_window": self._diagnostic_info.get("has_visible_window", False),
                "browser_exe_exists": self._diagnostic_info.get("browser_exe_exists", True),
                "technical_detail": self._diagnostic_info.get("technical_detail", "")
            }

            HEALTH_STATE_MAP = {
                ConnectionState.BROWSER_CLOSED: "not_started",
                ConnectionState.CHECKING_BROWSER: "starting",
                ConnectionState.RESOLVING_CONFLICT: "starting",
                ConnectionState.STARTING_BROWSER: "starting",
                ConnectionState.OPENING_WHATSAPP: "browser_ready",
                ConnectionState.WAITING_FOR_QR: "waiting_qr",
                ConnectionState.SYNCING_ACCOUNT: "authenticating",
                ConnectionState.CONNECTED: "connected",
                ConnectionState.PROFILE_LOCKED: "profile_locked",
                ConnectionState.STALE_LOCK: "profile_locked",
                ConnectionState.LAUNCH_FAILED: "failed",
                ConnectionState.UNSUPPORTED_PROFILE: "unsupported",
                ConnectionState.CONNECTION_LOST: "disconnected",
                ConnectionState.TIMED_OUT: "disconnected",
                ConnectionState.UNKNOWN_ERROR: "failed",
            }
            health_state = HEALTH_STATE_MAP.get(state, "not_started")

            from backend.database import db
            pref = None
            try:
                pref = db.get_browser_profile_preference()
            except Exception:
                pass

            pers_pref = pref.get("preferred_personal_profile") if pref else None
            if pers_pref:
                pers_b = pers_pref.get("browser", "chrome")
                pers_p = pers_pref.get("profile_dir", "Profile 10")
                pers_name = pers_pref.get("profile_name", "whatsapp auto")
                pers_supp = pers_pref.get("is_supported", False)
                pers_reason = pers_pref.get("unsupported_reason", "")
                preferred_profile = {
                    "browser": pers_b,
                    "browser_name": BrowserManager.BROWSERS.get(pers_b, {}).get("name", pers_b.title()),
                    "profile_dir": pers_p,
                    "profile_name": pers_name,
                    "is_supported": pers_supp,
                    "unsupported_reason": pers_reason
                }
            else:
                pref_b_key = pref.get("browser_id", b_key) if pref else b_key
                pref_p_dir = pref.get("canonical_profile_dir", p_dir) if pref else p_dir
                pref_p_name = pref.get("profile_display_name", p_name) if pref else p_name
                pref_b_name = BrowserManager.BROWSERS.get(pref_b_key, {}).get("name", pref_b_key.title())
                is_supp, unsupp_r, _ = BrowserManager.is_profile_automation_supported(
                    pref_b_key,
                    profile_dir=pref_p_dir,
                    is_dedicated=(pref_p_dir == "__dedicated__"),
                    exe_path=BrowserManager.BROWSERS.get(pref_b_key, {}).get("exe_path")
                )
                preferred_profile = {
                    "browser": pref_b_key,
                    "browser_name": pref_b_name,
                    "profile_dir": pref_p_dir,
                    "profile_name": pref_p_name,
                    "is_supported": is_supp,
                    "unsupported_reason": unsupp_r if not is_supp else ""
                }

            remember_profile = bool(pref.get("remember_profile", 1) if pref else True)
            auto_connect = bool(pref.get("auto_connect", 0) if pref else False)

            saved_cfg = {
                "browser": b_key,
                "browser_name": b_name,
                "profile_dir": p_dir,
                "profile_name": p_name,
                "mode": "dedicated" if is_dedicated else "existing_profile",
                "is_dedicated": is_dedicated,
                "remember_profile": remember_profile,
                "auto_connect": auto_connect,
                "last_selected_at": pref.get("last_selected_at") if pref else None,
                "last_connected_at": pref.get("last_connected_at") if pref else None
            }
            active_sess = {
                "is_active": state == ConnectionState.CONNECTED or (has_driver and state not in (ConnectionState.BROWSER_CLOSED, ConnectionState.LAUNCH_FAILED, ConnectionState.UNSUPPORTED_PROFILE)),
                "has_driver": has_driver,
                "name": self._active_session_name,
                "browser": b_key,
                "profile_dir": p_dir,
                "is_dedicated": is_dedicated,
                "is_connected": state == ConnectionState.CONNECTED
            }
            conn_hlth = {
                "state": state,
                "health_state": health_state,
                "status": state_label,
                "is_locked": state == ConnectionState.PROFILE_LOCKED,
                "lock_state": "locked" if state == ConnectionState.PROFILE_LOCKED else ("stale_lock" if state == ConnectionState.STALE_LOCK else "available"),
                "can_send": state == ConnectionState.CONNECTED
            }

            return {
                # Structured separation
                "preferred_profile": preferred_profile,
                "saved_config": saved_cfg,
                "active_session": active_sess,
                "connection_health": conn_hlth,
                "pending_transition": None,
                "failure_category": self._failure_category,
                # Live connection status
                "state": state,
                "health_state": health_state,
                "state_label": state_label,
                "mode": "dedicated" if is_dedicated else "existing_profile",
                "mode_label": "Dedicated Relay Session" if is_dedicated else "Existing Browser Profile",
                "browser": b_key,
                "browser_name": b_name,
                "profile_dir": p_dir,
                "profile_name": p_name,
                "is_dedicated": is_dedicated,
                "is_connected": state == ConnectionState.CONNECTED,
                "has_active_driver": has_driver,
                "last_checked_at": last_checked,
                "current_activity": activity,
                "error_detail": error_detail,
                "timeline": timeline,
                "actions": actions,
                "can_send": state == ConnectionState.CONNECTED,
                "remember_profile": remember_profile,
                "auto_connect": auto_connect,
                "prompt_required": self._diagnostic_info.get("conflict_type") == "personal_browser" and state == ConnectionState.PROFILE_LOCKED,
                "conflict_type": self._diagnostic_info.get("conflict_type", "none"),
                "diagnostic_details": diag_det
            }


# Global singleton monitor
connection_monitor = ConnectionMonitor()
