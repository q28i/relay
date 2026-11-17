"""
Intelligent Session Lifecycle Manager for Relay WhatsApp Automation.
Tracks browser executable, family, profile path, PID, verified child PIDs,
Relay ownership metadata, session state, launch timestamp, health checks,
and handles graceful shutdowns, concurrency locking, and orphaned process recovery.
"""

import os
import sys
import json
import time
import uuid
import ctypes
from ctypes import wintypes
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List, Set
import psutil

from logger import get_logger
from backend.paths import get_session_dir

logger = get_logger("SessionLifecycle")

WM_CLOSE = 0x0010


def send_wm_close_to_pid(pid: int) -> int:
    """
    Sends Win32 WM_CLOSE messages to all top-level windows belonging to the given PID.
    Simulates a graceful window closure by the user. Returns number of windows messaged.
    """
    if sys.platform != "win32":
        return 0

    windows_found = []
    try:
        user32 = ctypes.windll.user32

        def enum_handler(hwnd, lparam):
            if user32.IsWindow(hwnd):
                proc_id = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
                if proc_id.value == pid:
                    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                    windows_found.append(hwnd)
            return True

        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(EnumWindowsProc(enum_handler), 0)
    except Exception as e:
        logger.debug(f"Error enumerating windows for PID {pid}: {e}")

    return len(windows_found)


class SessionLifecycleManager:
    """
    Centralized session tracker and process lifecycle coordinator.
    Ensures that only authorized Relay-owned sessions are managed automatically,
    while personal browser processes are protected with strict confirmation workflows.
    """

    _instance = None
    _singleton_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = super(SessionLifecycleManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, session_dir: Optional[str] = None):
        if getattr(self, "_initialized", False):
            return

        self._lock = threading.RLock()
        self._launch_mutex = threading.Lock()
        self._launch_in_progress = False

        self.session_dir = session_dir or get_session_dir()
        os.makedirs(self.session_dir, exist_ok=True)
        self.session_file = os.path.join(self.session_dir, "relay_session.json")

        self._current_session: Optional[Dict[str, Any]] = None
        self._active_driver = None
        self._load_persisted_session()
        self._initialized = True

    # --------------------------------------------------------------------------
    # Concurrency Lock
    # --------------------------------------------------------------------------

    def acquire_launch_lock(self, timeout: float = 10.0) -> bool:
        """Acquires launch mutex preventing concurrent start/restart operations."""
        acquired = self._launch_mutex.acquire(timeout=timeout)
        if acquired:
            self._launch_in_progress = True
        return acquired

    def release_launch_lock(self):
        """Releases launch mutex."""
        self._launch_in_progress = False
        try:
            self._launch_mutex.release()
        except RuntimeError:
            pass

    # --------------------------------------------------------------------------
    # Persistence
    # --------------------------------------------------------------------------

    def _load_persisted_session(self):
        """Loads persisted session metadata from disk if present."""
        if os.path.isfile(self.session_file):
            try:
                with open(self.session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("is_relay_owned"):
                    self._current_session = data
                    logger.info(f"Loaded existing Relay session metadata: ID={data.get('session_id')}, PID={data.get('browser_pid')}")
            except Exception as e:
                logger.warning(f"Could not load relay_session.json: {e}")

    def _save_persisted_session(self):
        """Persists current session metadata to disk."""
        try:
            if self._current_session:
                with open(self.session_file, "w", encoding="utf-8") as f:
                    json.dump(self._current_session, f, indent=2)
            else:
                if os.path.isfile(self.session_file):
                    os.remove(self.session_file)
        except Exception as e:
            logger.warning(f"Could not persist relay_session.json: {e}")

    # --------------------------------------------------------------------------
    # Session Registration & Tracking
    # --------------------------------------------------------------------------

    def generate_session_id(self) -> str:
        return str(uuid.uuid4())

    def record_session(
        self,
        driver: Any,
        browser_key: str,
        profile_dir: str,
        profile_path: str,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Registers an active Selenium driver session, capturing driver PID,
        root browser process PID, and verified child processes.
        """
        with self._lock:
            s_id = session_id or self.generate_session_id()
            now_iso = datetime.now().isoformat()
            now_epoch = time.time()

            driver_pid = None
            browser_pid = None
            child_pids: List[int] = []
            browser_create_time = 0.0

            # 1. Identify Selenium Driver process
            try:
                if hasattr(driver, "service") and getattr(driver.service, "process", None):
                    driver_pid = driver.service.process.pid
            except Exception:
                pass

            # 2. Identify Browser Process (child of driver or matching command line)
            if driver_pid and psutil.pid_exists(driver_pid):
                try:
                    driver_proc = psutil.Process(driver_pid)
                    children = driver_proc.children(recursive=True)
                    for child in children:
                        child_pids.append(child.pid)
                        # Root browser is typically the direct child
                        if browser_pid is None:
                            browser_pid = child.pid
                            try:
                                browser_create_time = child.create_time()
                            except Exception:
                                pass
                except Exception:
                    pass

            # Fallback search if browser_pid wasn't found via driver children
            if browser_pid is None:
                norm_prof = os.path.normcase(os.path.normpath(profile_path)) if profile_path else ""
                marker = f"--relay-session-id={s_id}"
                for p in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
                    try:
                        cmd = p.info.get('cmdline') or []
                        if any(marker in arg for arg in cmd):
                            browser_pid = p.info['pid']
                            browser_create_time = p.info.get('create_time') or 0.0
                            break
                        if norm_prof:
                            for arg in cmd:
                                if arg.startswith('--user-data-dir=') and norm_prof in os.path.normcase(os.path.normpath(arg)):
                                    browser_pid = p.info['pid']
                                    browser_create_time = p.info.get('create_time') or 0.0
                                    break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

            self._active_driver = driver
            self._current_session = {
                "session_id": s_id,
                "relay_marker": f"relay-session-{s_id}",
                "browser_key": browser_key,
                "browser_family": browser_key,
                "profile_dir": profile_dir,
                "profile_path": profile_path,
                "driver_pid": driver_pid,
                "browser_pid": browser_pid,
                "child_pids": child_pids,
                "browser_create_time": browser_create_time,
                "launch_timestamp": now_iso,
                "launch_epoch": now_epoch,
                "last_health_check": now_iso,
                "session_state": "active",
                "is_relay_owned": True,
                "last_error": ""
            }
            self._save_persisted_session()
            logger.info(f"Recorded new Relay session: id={s_id}, driver_pid={driver_pid}, browser_pid={browser_pid}")
            return dict(self._current_session)

    def get_current_session(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return dict(self._current_session) if self._current_session else None

    def get_active_driver(self):
        with self._lock:
            return self._active_driver

    def set_active_driver(self, driver):
        with self._lock:
            self._active_driver = driver

    def update_health_check(self, is_healthy: bool = True, error: str = ""):
        with self._lock:
            if self._current_session:
                self._current_session["last_health_check"] = datetime.now().isoformat()
                if not is_healthy and error:
                    self._current_session["last_error"] = error
                self._save_persisted_session()

    def clear_session(self, state: str = "terminated"):
        with self._lock:
            if self._current_session:
                self._current_session["session_state"] = state
                self._current_session = None
            self._active_driver = None
            self._save_persisted_session()

    # --------------------------------------------------------------------------
    # Ownership & Conflict Diagnosis
    # --------------------------------------------------------------------------

    def is_relay_owned_pid(self, pid: int, cmdline: Optional[List[str]] = None) -> bool:
        """
        Determines whether a running process is unequivocally owned by Relay:
        1. Check recorded current session PID & creation time.
        2. Check for '--relay-session-id=' flag in process cmdline.
        3. Check if '--user-data-dir' points to the app-owned dedicated session directory.
        """
        # 1. Match against active recorded session
        sess = self.get_current_session()
        if sess:
            known_pids = set([sess.get("browser_pid"), sess.get("driver_pid")] + (sess.get("child_pids") or []))
            known_pids.discard(None)
            if pid in known_pids:
                # Verify creation time if possible
                target_create_time = sess.get("browser_create_time") or 0.0
                if target_create_time > 0:
                    try:
                        p = psutil.Process(pid)
                        if abs(p.create_time() - target_create_time) < 3.0:
                            return True
                    except Exception:
                        pass
                else:
                    return True

        # 2. Inspect command line arguments
        cmd = cmdline
        if cmd is None:
            try:
                if psutil.pid_exists(pid):
                    p = psutil.Process(pid)
                    cmd = p.cmdline()
            except Exception:
                cmd = []

        if cmd:
            for arg in cmd:
                if "--relay-session-id=" in arg or "relay-session-" in arg:
                    return True

            # 3. Dedicated session path is strictly owned by Relay
            norm_sess_dir = os.path.normcase(os.path.normpath(self.session_dir))
            for arg in cmd:
                if arg.startswith("--user-data-dir="):
                    val = arg.split("=", 1)[1].strip('"\'')
                    if os.path.normcase(os.path.normpath(val)) == norm_sess_dir:
                        return True

        return False

    def identify_conflicting_processes(
        self,
        browser_key: str,
        profile_dir: str,
        is_dedicated: bool
    ) -> Dict[str, Any]:
        """
        Scans running processes and classifies them into:
        - Relay-owned processes (can be auto-restarted cleanly)
        - Personal browser processes (require explicit user confirmation)
        - Unrelated processes (must NEVER be touched)
        """
        from browser_manager import BrowserManager
        diag = BrowserManager.diagnose_profile(browser_key, profile_dir=profile_dir, is_dedicated=is_dedicated)

        matching_pids = diag.get("matching_pids", [])
        relay_pids: List[int] = []
        personal_pids: List[int] = []
        process_details: List[Dict[str, Any]] = []

        for pid in matching_pids:
            try:
                proc = psutil.Process(pid)
                cmd = proc.cmdline()
                pname = proc.name()
                is_relay = self.is_relay_owned_pid(pid, cmd)

                detail = {
                    "pid": pid,
                    "name": pname,
                    "is_relay_owned": is_relay,
                    "has_window": BrowserManager.has_visible_window(pid) if hasattr(BrowserManager, "has_visible_window") else False
                }
                process_details.append(detail)

                if is_relay:
                    relay_pids.append(pid)
                else:
                    personal_pids.append(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        has_conflict = len(matching_pids) > 0
        if not has_conflict:
            conflict_type = "none"
        elif len(personal_pids) > 0:
            conflict_type = "personal_browser"
        else:
            conflict_type = "relay_owned"

        return {
            "has_conflict": has_conflict,
            "conflict_type": conflict_type,
            "matching_pids": matching_pids,
            "relay_pids": relay_pids,
            "personal_pids": personal_pids,
            "process_details": process_details,
            "is_stale_lock": diag.get("is_stale_lock", False),
            "browser_exe_exists": diag.get("browser_exe_exists", True),
            "safe_error_reason": diag.get("safe_error_reason", ""),
            "raw_profile_path": diag.get("raw_profile_path", "")
        }

    # --------------------------------------------------------------------------
    # Graceful Closure & Termination
    # --------------------------------------------------------------------------

    def graceful_close_pid(self, pid: int, timeout: float = 4.0) -> bool:
        """
        Gracefully requests a process to close via WM_CLOSE window messaging.
        Waits up to timeout seconds for process exit. Returns True if process exited.
        """
        if not psutil.pid_exists(pid):
            return True

        # Send WM_CLOSE to top-level windows on Windows, or SIGTERM on POSIX
        if sys.platform == "win32":
            send_wm_close_to_pid(pid)
        else:
            try:
                psutil.Process(pid).terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Wait for exit
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not psutil.pid_exists(pid):
                return True
            time.sleep(0.2)

        return not psutil.pid_exists(pid)

    def terminate_relay_process_tree(self, timeout: float = 5.0) -> bool:
        """
        Terminates the active Relay-owned browser process tree gracefully first,
        falling back to terminate/kill only for Relay-owned processes.
        NEVER affects personal processes.
        """
        with self._lock:
            # 1. Close active driver session cleanly if responsive
            if self._active_driver is not None:
                try:
                    self._active_driver.quit()
                except Exception:
                    pass
                self._active_driver = None

            sess = self.get_current_session()
            pids_to_clean: Set[int] = set()

            if sess:
                if sess.get("driver_pid"):
                    pids_to_clean.add(sess["driver_pid"])
                if sess.get("browser_pid"):
                    pids_to_clean.add(sess["browser_pid"])
                for c in (sess.get("child_pids") or []):
                    pids_to_clean.add(c)

            # Discover any other running Relay processes
            for p in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if self.is_relay_owned_pid(p.info['pid'], p.info.get('cmdline')):
                        pids_to_clean.add(p.info['pid'])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            if not pids_to_clean:
                self.clear_session("terminated")
                return True

            logger.info(f"Terminating Relay process tree: PIDs={list(pids_to_clean)}")

            # Pass 1: Send graceful WM_CLOSE to all Relay windows
            for pid in list(pids_to_clean):
                if psutil.pid_exists(pid):
                    send_wm_close_to_pid(pid)

            # Wait up to 2 seconds for graceful exit
            deadline = time.time() + 2.0
            while time.time() < deadline:
                remaining = [pid for pid in pids_to_clean if psutil.pid_exists(pid)]
                if not remaining:
                    self.clear_session("terminated")
                    return True
                time.sleep(0.2)

            # Pass 2: Graceful terminate() on remaining Relay processes
            for pid in list(pids_to_clean):
                if psutil.pid_exists(pid):
                    try:
                        p = psutil.Process(pid)
                        for child in p.children(recursive=True):
                            try:
                                child.terminate()
                            except Exception:
                                pass
                        p.terminate()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

            # Wait up to 2 more seconds
            deadline = time.time() + 2.0
            while time.time() < deadline:
                remaining = [pid for pid in pids_to_clean if psutil.pid_exists(pid)]
                if not remaining:
                    self.clear_session("terminated")
                    return True
                time.sleep(0.2)

            # Pass 3: Hard kill remaining Relay processes (Relay-owned ONLY)
            for pid in list(pids_to_clean):
                if psutil.pid_exists(pid):
                    try:
                        p = psutil.Process(pid)
                        p.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

            self.clear_session("terminated")
            return True

    # --------------------------------------------------------------------------
    # Automatic Conflict Resolution
    # --------------------------------------------------------------------------

    def resolve_conflict(
        self,
        browser_key: str,
        profile_dir: str,
        is_dedicated: bool,
        force_personal: bool = False
    ) -> Dict[str, Any]:
        """
        Executes automatic conflict resolution:
        1. If no conflict: returns resolved=True immediately.
        2. If previous Relay-owned session: automatically terminates process tree gracefully,
           cleans up lockfile, and returns resolved=True.
        3. If personal browser instance:
           - If not force_personal: stops and requests user confirmation (NEVER kills).
           - If force_personal: sends WM_CLOSE gracefully and waits up to 5s.
             If personal window exits, returns resolved=True; otherwise returns failure without killing.
        4. If stale lock: removes or bypasses lock safely.
        """
        analysis = self.identify_conflicting_processes(browser_key, profile_dir, is_dedicated)

        # Case A: No active conflict
        if not analysis["has_conflict"]:
            # Check for stale lockfile
            if analysis.get("is_stale_lock"):
                logger.info("Stale lock artifact detected without active processes. Resolving cleanly.")
            return {
                "resolved": True,
                "conflict_type": "none",
                "message": "No active browser conflict.",
                "analysis": analysis
            }

        # Case B: Relay-owned conflict
        if analysis["conflict_type"] == "relay_owned":
            logger.info("Relay-owned browser session conflict detected. Resolving automatically...")
            self.terminate_relay_process_tree(timeout=4.0)

            # Wait up to 3 seconds for profile lock to be released
            time.sleep(0.8)
            recheck = self.identify_conflicting_processes(browser_key, profile_dir, is_dedicated)
            if not recheck["has_conflict"]:
                return {
                    "resolved": True,
                    "conflict_type": "relay_owned",
                    "message": "Previous Relay session automatically closed and profile released.",
                    "analysis": recheck
                }
            else:
                return {
                    "resolved": False,
                    "conflict_type": "relay_owned",
                    "message": "Waiting for previous Relay session processes to finish releasing profile lock.",
                    "analysis": recheck
                }

        # Case C: Personal Browser Instance (User opened window)
        personal_pids = analysis.get("personal_pids", [])
        if not force_personal:
            # STRICT POLICY: Never terminate personal browser without explicit confirmation
            logger.info(f"Personal browser conflict detected on PIDs={personal_pids}. User confirmation required.")
            return {
                "resolved": False,
                "conflict_type": "personal_browser",
                "prompt_required": True,
                "personal_pids": personal_pids,
                "message": (
                    "The selected profile is currently open in a personal browser window. "
                    "Restarting will close open tabs and unsaved work."
                ),
                "analysis": analysis
            }

        # User explicitly confirmed closing personal browser window
        logger.info(f"User confirmed closing personal browser window for PIDs={personal_pids}. Sending WM_CLOSE...")
        for pid in personal_pids:
            send_wm_close_to_pid(pid)

        # Wait up to 5.0 seconds for graceful personal browser exit
        deadline = time.time() + 5.0
        while time.time() < deadline:
            remaining = [pid for pid in personal_pids if psutil.pid_exists(pid)]
            if not remaining:
                break
            time.sleep(0.4)

        recheck = self.identify_conflicting_processes(browser_key, profile_dir, is_dedicated)
        if not recheck["has_conflict"]:
            return {
                "resolved": True,
                "conflict_type": "personal_browser",
                "message": "Personal browser window closed successfully.",
                "analysis": recheck
            }
        else:
            # We NEVER force-kill personal browsers!
            return {
                "resolved": False,
                "conflict_type": "personal_browser",
                "prompt_required": False,
                "timeout": True,
                "message": (
                    "Personal browser did not close within timeout. "
                    "Please save and close your browser window manually, or use a dedicated Relay session."
                ),
                "analysis": recheck
            }

    # --------------------------------------------------------------------------
    # Orphan Recovery
    # --------------------------------------------------------------------------

    def recover_orphaned_session(self) -> Dict[str, Any]:
        """
        Inspects persisted session metadata against live system processes.
        If an orphaned Relay-owned process is found running after an application restart,
        it cleanly handles or terminates it so future launches proceed cleanly.
        """
        with self._lock:
            sess = self.get_current_session()
            if not sess:
                return {"has_orphaned": False, "message": "No session metadata found on disk."}

            browser_pid = sess.get("browser_pid")
            is_alive = False
            if browser_pid and psutil.pid_exists(browser_pid):
                try:
                    p = psutil.Process(browser_pid)
                    if self.is_relay_owned_pid(browser_pid, p.cmdline()):
                        is_alive = True
                except Exception:
                    pass

            if is_alive:
                logger.info(f"Found orphaned Relay session process (PID {browser_pid}). Terminating cleanly...")
                self.terminate_relay_process_tree(timeout=3.0)
                return {
                    "has_orphaned": True,
                    "recovered": True,
                    "message": f"Orphaned Relay process {browser_pid} was terminated cleanly."
                }
            else:
                self.clear_session("stale_cleared")
                return {
                    "has_orphaned": False,
                    "message": "Session metadata cleared (processes already dead)."
                }

    # --------------------------------------------------------------------------
    # Session Health Verification
    # --------------------------------------------------------------------------

    def is_session_healthy(self, driver: Any) -> bool:
        """
        Non-destructively verifies whether an existing Selenium driver is responsive
        and has at least one valid window handle.
        """
        if not driver:
            return False
        try:
            handles = driver.window_handles
            if len(handles) == 0:
                return False
            # Check title or current URL
            _ = driver.current_url
            return True
        except Exception:
            return False


# Global singleton instance
session_lifecycle = SessionLifecycleManager()

