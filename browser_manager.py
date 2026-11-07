"""
Browser and Profile Manager for WhatsApp Automation
Detects installed Chromium browsers (Chrome, Edge, Brave) and their user profiles on Windows.
Allows persistent WhatsApp Web sessions without re-scanning QR codes.
"""

import os
import json
import winreg
import time
import psutil
import ctypes
from ctypes import wintypes
from typing import List, Dict, Optional, Tuple, Any
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from backend.paths import get_session_dir


class ProfileLockedError(RuntimeError):
    """Raised when an active browser process is verified to be using the target profile."""
    def __init__(self, message: str, condition: str = "ACTIVE_VISIBLE_PROCESS", pids: list = None, is_relay_owned: bool = False, conflict_type: str = "personal_browser"):
        super().__init__(message)
        self.condition = condition
        self.pids = pids or []
        self.is_relay_owned = is_relay_owned
        self.conflict_type = conflict_type


class StaleLockArtifactError(RuntimeError):
    """Raised when a lock file exists on disk, but NO matching browser process was found."""
    def __init__(self, message: str, lock_path: str = ""):
        super().__init__(message)
        self.lock_path = lock_path


class BrowserExecutableNotFoundError(FileNotFoundError):
    """Raised when the configured browser executable does not exist on disk."""
    pass


class BrowserLaunchFailedError(RuntimeError):
    """Raised when browser launch fails before a process or window appears."""
    def __init__(self, message: str, safe_reason: str = "", technical_detail: str = ""):
        super().__init__(message)
        self.safe_reason = safe_reason
        self.technical_detail = technical_detail


class UnsupportedProfileAutomationError(RuntimeError):
    """Raised when browser security restrictions (such as Chrome 136+) prohibit automating the default user-data directory."""
    def __init__(self, message: str, safe_reason: str = "", technical_detail: str = ""):
        super().__init__(message)
        self.safe_reason = safe_reason
        self.technical_detail = technical_detail


def get_file_version_string(filename: str) -> Optional[str]:
    """Retrieves file product version string on Windows using Win32 API without spawning processes."""
    if not filename or not os.path.isfile(filename):
        return None
    try:
        size = ctypes.windll.version.GetFileVersionInfoSizeW(filename, None)
        if not size:
            return None
        res = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(filename, 0, size, res):
            return None
        handle = ctypes.c_void_p()
        length = ctypes.c_uint()
        if not ctypes.windll.version.VerQueryValueW(res, r'\\VarFileInfo\\Translation', ctypes.byref(handle), ctypes.byref(length)):
            return None
        trans = ctypes.cast(handle, ctypes.POINTER(ctypes.c_uint16))
        lang, codepage = trans[0], trans[1]
        sub_block = f'\\\\StringFileInfo\\\\{lang:04x}{codepage:04x}\\\\ProductVersion'
        if ctypes.windll.version.VerQueryValueW(res, sub_block, ctypes.byref(handle), ctypes.byref(length)):
            return ctypes.wstring_at(handle)
    except Exception:
        pass
    return None


def is_profile_automation_supported(browser_key: str, profile_dir: str, is_dedicated: bool, exe_path: Optional[str] = None) -> Tuple[bool, str, str]:
    """
    Evaluates whether a given browser profile can be automated via WebDriver / DevTools.
    Chrome 136+ (and Chromium derivatives) strictly disallows remote debugging endpoints
    (--remote-debugging-port) when pointing to the browser's default User Data directory.
    
    Returns:
        (is_supported: bool, reason: str, detected_version: str)
    """
    if is_dedicated or profile_dir == "__dedicated__":
        return True, "", ""
    
    if browser_key not in ("chrome", "brave", "edge"):
        return True, "", ""
    
    # Check browser version
    v_str = get_file_version_string(exe_path) if exe_path else None
    major_v = 0
    if v_str:
        try:
            major_v = int(v_str.split(".")[0])
        except Exception:
            major_v = 0
    
    # Modern Chromium restriction: version 136+ restricts remote debugging on default User Data dir
    if major_v >= 136:
        reason = (
            f"{browser_key.title()} {v_str or '136+'} restricts remote debugging against the browser's default user-data directory. "
            "Automated WebDriver control requires an isolated user-data directory. Use the persistent Relay session instead."
        )
        return False, reason, v_str or ""
        
    return True, "", v_str or ""


def has_visible_window(pid: int) -> bool:
    """Checks whether a process currently owns at least one visible top-level window."""
    try:
        user32 = ctypes.windll.user32
        found = []
        def enum_proc(hwnd, lParam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    p_id = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p_id))
                    if p_id.value == pid:
                        found.append(hwnd)
            return True
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(EnumWindowsProc(enum_proc), 0)
        return len(found) > 0
    except Exception:
        return False



class BrowserManager:
    BROWSERS = {
        "chrome": {
            "name": "Google Chrome",
            "exe_names": ["chrome.exe"],
            "reg_path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
            "default_paths": [
                os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
            ],
            "user_data_path": os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data"),
            "driver_type": "chrome"
        },
        "edge": {
            "name": "Microsoft Edge",
            "exe_names": ["msedge.exe"],
            "reg_path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
            "default_paths": [
                os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
            ],
            "user_data_path": os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "User Data"),
            "driver_type": "edge"
        },
        "brave": {
            "name": "Brave Browser",
            "exe_names": ["brave.exe"],
            "reg_path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\brave.exe",
            "default_paths": [
                os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            ],
            "user_data_path": os.path.join(os.environ.get("LOCALAPPDATA", ""), "BraveSoftware", "Brave-Browser", "User Data"),
            "driver_type": "brave"
        },
        "firefox": {
            "name": "Mozilla Firefox",
            "exe_names": ["firefox.exe"],
            "reg_path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe",
            "default_paths": [
                os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "Mozilla Firefox", "firefox.exe"),
                os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), "Mozilla Firefox", "firefox.exe"),
            ],
            "user_data_path": os.path.join(os.environ.get("APPDATA", ""), "Mozilla", "Firefox"),
            "driver_type": "firefox"
        }
    }

    @classmethod
    def get_installed_browsers(cls) -> Dict[str, dict]:
        """Detects which supported browsers are installed on the local Windows system."""
        installed = {}
        for key, info in cls.BROWSERS.items():
            exe_path = cls._find_executable(info["reg_path"], info["default_paths"])
            if exe_path:
                info_copy = info.copy()
                info_copy["exe_path"] = exe_path
                installed[key] = info_copy
        return installed

    @staticmethod
    def _find_executable(reg_path: str, default_paths: List[str]) -> Optional[str]:
        # 1. Registry
        for hkey in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hkey, reg_path) as k:
                    val, _ = winreg.QueryValueEx(k, "")
                    if val and os.path.isfile(val):
                        return val
            except OSError:
                pass
        # 2. Default installation paths
        for p in default_paths:
            if p and os.path.isfile(p):
                return p
        return None

    @classmethod
    def is_profile_automation_supported(cls, browser_key: str, profile_dir: str, is_dedicated: bool = False, exe_path: Optional[str] = None) -> Tuple[bool, str, str]:
        """Evaluates whether a profile can be automated under modern Chromium restrictions."""
        if not exe_path and browser_key in cls.BROWSERS:
            b_info = cls.BROWSERS[browser_key]
            exe_path = cls._find_executable(b_info["reg_path"], b_info["default_paths"])
        return is_profile_automation_supported(browser_key, profile_dir, is_dedicated, exe_path)

    @staticmethod
    def shorten_path(path: str) -> str:
        """Returns shortened local/relative representation of file paths for privacy."""
        if not path:
            return ""
        user_home = os.path.expanduser("~")
        if path.startswith(user_home):
            return "~" + path[len(user_home):].replace("\\", "/")
        return path.replace("\\", "/")

    @classmethod
    def diagnose_profile(cls, browser_key: str, profile_dir: str = "Default", is_dedicated: bool = False) -> Dict[str, Any]:
        """
        Rigorously diagnoses browser profile state by distinguishing:
        1. ACTIVE_VISIBLE_PROCESS: Process with visible window actively using that exact profile.
        2. ACTIVE_BACKGROUND_PROCESS: Background process using that exact profile (no window).
        3. STALE_LOCK_ARTIFACT: Lock file exists, but NO matching process is running.
        4. PROFILE_PATH_INVALID: User data or profile directory not found on disk.
        5. MISSING_EXECUTABLE: Browser binary not found at registry or default paths.
        6. AVAILABLE: Browser executable exists and profile is free to launch.
        """
        browser_info = cls.BROWSERS.get(browser_key)
        if not browser_info:
            return {
                "condition": "UNSUPPORTED_BROWSER",
                "availability": "profile_unavailable",
                "is_locked": False,
                "is_stale_lock": False,
                "user_message": f"Unsupported browser '{browser_key}'.",
                "safe_error_reason": f"Browser key '{browser_key}' is not in supported catalog.",
                "matching_pids": [],
                "browser_running_pids": [],
                "relay_pids": [],
                "personal_pids": [],
                "conflict_type": "none",
                "is_relay_owned": False,
                "can_auto_resolve": True,
                "has_visible_window": False,
                "browser_has_visible_window": False,
                "raw_profile_path": "",
                "short_profile_path": "",
                "browser_exe_exists": False,
                "browser_exe_path": ""
            }

        b_name = browser_info["name"]
        exe_path = cls._find_executable(browser_info["reg_path"], browser_info["default_paths"])
        exe_exists = bool(exe_path and os.path.isfile(exe_path))

        if is_dedicated or profile_dir == "__dedicated__":
            user_data_path = get_session_dir()
            raw_profile_path = user_data_path
            is_dedicated = True
        else:
            user_data_path = browser_info.get("user_data_path", "")
            raw_profile_path = os.path.join(user_data_path, profile_dir) if browser_key != "firefox" else profile_dir

        short_path = cls.shorten_path(raw_profile_path)

        if not exe_exists:
            return {
                "condition": "MISSING_EXECUTABLE",
                "availability": "profile_unavailable",
                "is_locked": False,
                "is_stale_lock": False,
                "user_message": f"Couldn't find {b_name} executable.",
                "safe_error_reason": f"Executable for {b_name} not found at default paths or registry.",
                "matching_pids": [],
                "browser_running_pids": [],
                "relay_pids": [],
                "personal_pids": [],
                "conflict_type": "none",
                "is_relay_owned": False,
                "can_auto_resolve": True,
                "has_visible_window": False,
                "browser_has_visible_window": False,
                "raw_profile_path": raw_profile_path,
                "short_profile_path": short_path,
                "browser_exe_exists": False,
                "browser_exe_path": exe_path or ""
            }

        if not is_dedicated and not os.path.isdir(user_data_path):
            return {
                "condition": "PROFILE_PATH_INVALID",
                "availability": "profile_unavailable",
                "is_locked": False,
                "is_stale_lock": False,
                "is_automation_supported": False,
                "user_message": f"{b_name} user data directory does not exist.",
                "safe_error_reason": f"Path '{short_path}' is not a directory.",
                "matching_pids": [],
                "browser_running_pids": [],
                "relay_pids": [],
                "personal_pids": [],
                "conflict_type": "none",
                "is_relay_owned": False,
                "can_auto_resolve": True,
                "has_visible_window": False,
                "browser_has_visible_window": False,
                "raw_profile_path": raw_profile_path,
                "short_profile_path": short_path,
                "browser_exe_exists": True,
                "browser_exe_path": exe_path
            }

        # Check Chromium 136+ restrictions for non-dedicated profiles
        is_supported, unsupp_reason, browser_ver = is_profile_automation_supported(
            browser_key,
            profile_dir=profile_dir,
            is_dedicated=is_dedicated,
            exe_path=exe_path
        )

        # Inspect running processes
        matching_pids = []
        browser_running_pids = []
        is_visible = False
        browser_is_visible = False
        norm_ud = os.path.normcase(os.path.normpath(user_data_path)) if user_data_path else ""
        norm_profile_dir = (profile_dir or "").strip('"\'').lower()

        exe_names = [n.lower() for n in browser_info.get("exe_names", [])]

        try:
            for p in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
                try:
                    pname = (p.info['name'] or '').lower()
                    if not any(target in pname for target in exe_names):
                        continue

                    cmd = p.info['cmdline'] or []
                    pid = p.info['pid']

                    if browser_key == "firefox":
                        browser_running_pids.append(pid)
                        matching_pids.append(pid)
                        if has_visible_window(pid):
                            is_visible = True
                            browser_is_visible = True
                        continue

                    cmd_ud = None
                    cmd_profile = None
                    for arg in cmd:
                        if arg.startswith('--user-data-dir='):
                            val = arg.split('=', 1)[1].strip('"\'')
                            cmd_ud = os.path.normcase(os.path.normpath(val))
                        elif arg.startswith('--profile-directory='):
                            cmd_profile = arg.split('=', 1)[1].strip('"\'')

                    is_this_user_data = False
                    if cmd_ud:
                        if cmd_ud == norm_ud:
                            is_this_user_data = True
                    else:
                        default_norm = os.path.normcase(os.path.normpath(browser_info.get("user_data_path", "")))
                        if not is_dedicated and norm_ud == default_norm:
                            is_this_user_data = True

                    if not is_this_user_data:
                        continue

                    # This process belongs to this browser's User Data directory
                    browser_running_pids.append(pid)
                    has_win = has_visible_window(pid)
                    if has_win:
                        browser_is_visible = True

                    # Now check if it belongs to THIS EXACT profile
                    if is_dedicated or profile_dir == "__dedicated__":
                        matching_pids.append(pid)
                        if has_win:
                            is_visible = True
                    else:
                        is_exact_match = False
                        if cmd_profile:
                            if cmd_profile.strip('"\'').lower() == norm_profile_dir:
                                is_exact_match = True
                        else:
                            # If no --profile-directory= was specified on Windows, Chrome defaults to "Default"
                            if norm_profile_dir in ("default", ""):
                                is_exact_match = True

                        if is_exact_match:
                            matching_pids.append(pid)
                            if has_win:
                                is_visible = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass

        # Check lockfile on disk
        if is_dedicated:
            lock_path = os.path.join(user_data_path, "lockfile")
        elif browser_key == "firefox":
            lock_path = os.path.join(raw_profile_path, "parent.lock")
        else:
            lock_path = os.path.join(user_data_path, "lockfile")

        lock_exists = os.path.exists(lock_path)
        is_file_locked = False
        if lock_exists:
            try:
                with open(lock_path, "r+"):
                    pass
            except (PermissionError, OSError):
                is_file_locked = True

        # Classify matching PIDs into Relay-owned vs Personal
        relay_pids = []
        personal_pids = []
        try:
            from backend.session_lifecycle import session_lifecycle
            for pid in matching_pids:
                if session_lifecycle.is_relay_owned_pid(pid):
                    relay_pids.append(pid)
                else:
                    personal_pids.append(pid)
        except Exception:
            personal_pids = list(matching_pids)

        if not matching_pids:
            conflict_type = "none"
        elif personal_pids:
            conflict_type = "personal_browser"
        else:
            conflict_type = "relay_owned"

        # Synthesize condition and honest availability status
        if matching_pids:
            if conflict_type == "relay_owned":
                cond = "ACTIVE_IN_RELAY"
                availability = "active_in_relay"
                msg = f"A previous Relay-owned {b_name} session is running for this profile."
                reason = f"Relay session process {matching_pids[0]} ({b_name}) is active."
                is_locked = False
                is_stale = False
            elif is_visible:
                cond = "ACTIVE_VISIBLE_PROCESS"
                availability = "in_use"
                msg = f"Selected profile is currently open in a {b_name} window."
                reason = f"Process {matching_pids[0]} ({b_name}) has an active visible window using profile '{profile_dir}'."
                is_locked = True
                is_stale = False
            else:
                cond = "ACTIVE_BACKGROUND_PROCESS"
                availability = "in_use"
                msg = f"A background {b_name} process is using this profile (no window visible)."
                reason = f"Background process {matching_pids[0]} ({b_name}) is running using profile '{profile_dir}'."
                is_locked = True
                is_stale = False
        elif browser_running_pids:
            cond = "BROWSER_RUNNING_OTHER_PROFILE"
            availability = "browser_running"
            msg = f"{b_name} is running with another profile. Profile '{profile_dir}' is not active."
            reason = f"{b_name} processes detected, but none are using profile '{profile_dir}'."
            is_locked = False
            is_stale = False
        elif lock_exists and is_file_locked:
            cond = "STALE_LOCK_ARTIFACT"
            availability = "stale_lock"
            msg = f"Stale lock file found, but no running {b_name} process was detected."
            reason = "A lock file artifact exists from a previous run, but no matching browser process is active."
            is_locked = False
            is_stale = True
        elif not is_supported:
            cond = "UNSUPPORTED_DEFAULT_PROFILE"
            availability = "unsupported_profile"
            msg = "Selected Chrome profile cannot be automated with the current configuration."
            reason = unsupp_reason
            is_locked = False
            is_stale = False
        else:
            cond = "AVAILABLE"
            availability = "available"
            msg = "Profile is available."
            reason = ""
            is_locked = False
            is_stale = False

        return {
            "condition": cond,
            "availability": availability,
            "is_locked": is_locked,
            "is_stale_lock": is_stale,
            "is_automation_supported": is_supported,
            "action_recommendation": "use_dedicated" if not is_supported else ("restart_session" if conflict_type == "relay_owned" else ""),
            "action_label": "Use persistent Relay session" if not is_supported else "",
            "browser_version": browser_ver,
            "user_message": msg,
            "safe_error_reason": reason or (unsupp_reason if not is_supported else ""),
            "matching_pids": matching_pids,
            "browser_running_pids": browser_running_pids,
            "relay_pids": relay_pids,
            "personal_pids": personal_pids,
            "conflict_type": conflict_type,
            "is_relay_owned": len(relay_pids) > 0 and len(personal_pids) == 0,
            "can_auto_resolve": conflict_type in ("none", "relay_owned"),
            "has_visible_window": is_visible,
            "browser_has_visible_window": browser_is_visible,
            "raw_profile_path": raw_profile_path,
            "short_profile_path": short_path,
            "browser_exe_exists": exe_exists,
            "browser_exe_path": exe_path or "",
            "lock_path": lock_path
        }

    @classmethod
    def check_profile_availability(cls, browser_key: str, profile_path: str, is_dedicated: bool = False, profile_dir: str = "Default") -> str:
        """
        Non-destructively checks profile availability returning honest states:
        'available', 'browser_running', 'in_use', 'active_in_relay', 'stale_lock', 'profile_unavailable', or 'could_not_verify'.
        """
        try:
            diag = cls.diagnose_profile(browser_key, profile_dir=profile_dir, is_dedicated=is_dedicated)
            return diag.get("availability", "available")
        except Exception:
            return "could_not_verify"

    @classmethod
    def get_profiles(cls, browser_key: str) -> List[Dict[str, str]]:
        """
        Discovers available profiles for the given browser.
        Also includes a Dedicated Automation Profile to avoid lock conflicts with active personal windows.
        """
        profiles = []
        # Option 0: Dedicated Profile for WhatsApp Automation
        dedicated_dir = get_session_dir()
        os.makedirs(dedicated_dir, exist_ok=True)
        dedicated_avail = cls.check_profile_availability(browser_key, dedicated_dir, is_dedicated=True, profile_dir="__dedicated__")

        profiles.append({
            "dir": "__dedicated__",
            "name": "Relay Automation Session",
            "display_name": "Relay Automation (Persistent & Supported)",
            "path": dedicated_dir,
            "short_path": "whatsapp_browser_session",
            "availability": "available",
            "is_dedicated": True,
            "is_automation_supported": True
        })

        if browser_key not in cls.BROWSERS:
            return profiles

        user_data = cls.BROWSERS[browser_key]["user_data_path"]
        if not os.path.isdir(user_data):
            return profiles

        # Firefox Profile Handling via profiles.ini
        if browser_key == "firefox":
            ini_file = os.path.join(user_data, "profiles.ini")
            if os.path.isfile(ini_file):
                try:
                    import configparser
                    cp = configparser.ConfigParser()
                    cp.read(ini_file, encoding="utf-8")
                    for s in cp.sections():
                        if s.lower().startswith("profile"):
                            pname = cp[s].get("name", s)
                            ppath = cp[s].get("path", "")
                            is_rel = cp[s].get("isrelative", "1") == "1"
                            full_path = os.path.join(user_data, ppath) if is_rel else ppath
                            if os.path.isdir(full_path):
                                avail = cls.check_profile_availability("firefox", full_path, profile_dir=ppath)
                                profiles.append({
                                    "dir": ppath,
                                    "name": f"{pname} ({os.path.basename(ppath)})",
                                    "display_name": pname,
                                    "path": full_path,
                                    "short_path": cls.shorten_path(full_path),
                                    "availability": avail,
                                    "is_dedicated": False
                                })
                except Exception as e:
                    print(f"[WARNING] Could not parse Firefox profiles.ini: {e}")
            return profiles

        local_state_file = os.path.join(user_data, "Local State")
        seen_dirs = set()

        if os.path.isfile(local_state_file):
            try:
                with open(local_state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                info_cache = data.get("profile", {}).get("info_cache", {})
                for dir_name, pinfo in info_cache.items():
                    dir_path = os.path.join(user_data, dir_name)
                    if os.path.isdir(dir_path):
                        display_name = pinfo.get("name") or dir_name
                        is_supp, unsupp_r, _ = is_profile_automation_supported(
                            browser_key,
                            profile_dir=dir_name,
                            is_dedicated=False,
                            exe_path=cls.BROWSERS.get(browser_key, {}).get("exe_path")
                        )
                        avail = "unsupported_profile" if not is_supp else cls.check_profile_availability(browser_key, user_data, is_dedicated=False, profile_dir=dir_name)
                        profiles.append({
                            "dir": dir_name,
                            "name": f"{display_name} ({dir_name})",
                            "display_name": display_name,
                            "path": user_data,
                            "short_path": cls.shorten_path(dir_path),
                            "availability": avail,
                            "is_dedicated": False,
                            "is_automation_supported": is_supp,
                            "unsupported_reason": unsupp_r if not is_supp else ""
                        })
                        seen_dirs.add(dir_name)
            except Exception as e:
                print(f"[WARNING] Could not parse Local State for {browser_key}: {e}")

        # Scan for existing folders like Default if not in info_cache
        try:
            for entry in os.listdir(user_data):
                if entry in seen_dirs:
                    continue
                if entry == "Default" or entry.startswith("Profile "):
                    epath = os.path.join(user_data, entry)
                    if os.path.isdir(epath):
                        is_supp, unsupp_r, _ = is_profile_automation_supported(
                            browser_key,
                            profile_dir=entry,
                            is_dedicated=False,
                            exe_path=cls.BROWSERS.get(browser_key, {}).get("exe_path")
                        )
                        avail = "unsupported_profile" if not is_supp else cls.check_profile_availability(browser_key, user_data, is_dedicated=False, profile_dir=entry)
                        profiles.append({
                            "dir": entry,
                            "name": entry,
                            "display_name": entry,
                            "path": user_data,
                            "short_path": cls.shorten_path(epath),
                            "availability": avail,
                            "is_dedicated": False,
                            "is_automation_supported": is_supp,
                            "unsupported_reason": unsupp_r if not is_supp else ""
                        })
                        seen_dirs.add(entry)
        except OSError:
            pass

        return profiles

    @classmethod
    def _find_cached_service(cls, driver_type: str):
        """Locates cached driver binary to avoid selenium-manager network stalls."""
        try:
            import glob
            import shutil
            if driver_type in ("chrome", "brave"):
                from selenium.webdriver.chrome.service import Service as ChromeService
                cache_pattern = os.path.expanduser("~/.cache/selenium/chromedriver/win64/*/chromedriver.exe")
                matches = glob.glob(cache_pattern)
                if matches and os.path.isfile(matches[0]):
                    return ChromeService(executable_path=matches[0])
                which_path = shutil.which("chromedriver")
                if which_path and os.path.isfile(which_path):
                    return ChromeService(executable_path=which_path)
            elif driver_type == "edge":
                from selenium.webdriver.edge.service import Service as EdgeService
                cache_pattern = os.path.expanduser("~/.cache/selenium/msedgedriver/win64/*/msedgedriver.exe")
                matches = glob.glob(cache_pattern)
                if matches and os.path.isfile(matches[0]):
                    return EdgeService(executable_path=matches[0])
                which_path = shutil.which("msedgedriver")
                if which_path and os.path.isfile(which_path):
                    return EdgeService(executable_path=which_path)
        except Exception:
            pass
        return None

    @classmethod
    def launch_driver(cls, browser_key: str, profile: dict, headless: bool = False, ignore_stale_lock: bool = False):
        """
        Initializes and returns a Selenium WebDriver instance with persistent session support.
        Strictly verifies that:
        1. Browser binary exists before attempting launch.
        2. Profile is not locked by an active process.
        3. Stale lock artifacts are reported cleanly unless ignore_stale_lock is specified.
        4. Driver process and window actually initialize before returning.
        """
        browser_info = cls.BROWSERS.get(browser_key)
        if not browser_info:
            raise ValueError(f"Unsupported browser: {browser_key}")

        driver_type = browser_info["driver_type"]
        p_dir = profile.get("dir", "__dedicated__")
        is_dedicated = profile.get("is_dedicated", False)

        # 1. Perform rigorous pre-flight diagnosis
        diag = cls.diagnose_profile(browser_key, profile_dir=p_dir, is_dedicated=is_dedicated)

        if diag.get("condition") == "UNSUPPORTED_DEFAULT_PROFILE" or not diag.get("is_automation_supported", True):
            raise UnsupportedProfileAutomationError(
                diag["user_message"],
                safe_reason=diag.get("safe_error_reason", "Selected Chrome profile cannot be automated with the current configuration."),
                technical_detail="Chromium 136+ security restrictions prevent remote debugging against default user-data directory."
            )

        if not diag["browser_exe_exists"]:
            raise BrowserExecutableNotFoundError(
                f"Browser executable not found for '{browser_key}'. Expected path: '{diag['browser_exe_path'] or 'unknown'}'."
            )

        if diag["is_locked"]:
            raise ProfileLockedError(
                diag["user_message"],
                condition=diag["condition"],
                pids=diag.get("matching_pids", []),
                is_relay_owned=diag.get("is_relay_owned", False),
                conflict_type=diag.get("conflict_type", "personal_browser")
            )

        if diag["is_stale_lock"] and not ignore_stale_lock:
            raise StaleLockArtifactError(
                diag["user_message"],
                lock_path=diag.get("lock_path", "")
            )

        session_id = None
        try:
            from backend.session_lifecycle import session_lifecycle
            session_id = session_lifecycle.generate_session_id()
        except Exception:
            pass

        try:
            if driver_type in ("chrome", "brave"):
                options = ChromeOptions()
                if session_id:
                    options.add_argument(f"--relay-session-id={session_id}")
                if driver_type == "brave":
                    options.binary_location = browser_info["exe_path"]

                if profile.get("is_dedicated"):
                    options.add_argument(f"--user-data-dir={profile['path']}")
                else:
                    options.add_argument(f"--user-data-dir={profile['path']}")
                    options.add_argument(f"--profile-directory={profile['dir']}")

                # Anti-detection & performance flags
                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_argument("--disable-infobars")
                options.add_argument("--start-maximized")
                options.add_argument("--window-size=1920,1080")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option("useAutomationExtension", False)

                if headless:
                    options.add_argument("--headless=new")

                service = cls._find_cached_service(driver_type)
                if service:
                    driver = webdriver.Chrome(service=service, options=options)
                else:
                    driver = webdriver.Chrome(options=options)

            elif driver_type == "edge":
                options = EdgeOptions()
                if session_id:
                    options.add_argument(f"--relay-session-id={session_id}")
                if profile.get("is_dedicated"):
                    options.add_argument(f"--user-data-dir={profile['path']}")
                else:
                    options.add_argument(f"--user-data-dir={profile['path']}")
                    options.add_argument(f"--profile-directory={profile['dir']}")

                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_argument("--disable-infobars")
                options.add_argument("--start-maximized")
                options.add_argument("--window-size=1920,1080")
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option("useAutomationExtension", False)

                if headless:
                    options.add_argument("--headless=new")

                service = cls._find_cached_service("edge")
                if service:
                    driver = webdriver.Edge(service=service, options=options)
                else:
                    driver = webdriver.Edge(options=options)

            elif driver_type == "firefox":
                from selenium.webdriver.firefox.options import Options as FirefoxOptions
                options = FirefoxOptions()
                if browser_info.get("exe_path"):
                    options.binary_location = browser_info["exe_path"]

                if profile.get("is_dedicated"):
                    os.makedirs(profile["path"], exist_ok=True)
                    options.add_argument("-profile")
                    options.add_argument(profile["path"])
                elif os.path.isdir(profile.get("path", "")):
                    options.add_argument("-profile")
                    options.add_argument(profile["path"])

                options.add_argument("--width=1920")
                options.add_argument("--height=1080")
                if headless:
                    options.add_argument("-headless")

                driver = webdriver.Firefox(options=options)

            else:
                raise ValueError(f"Unknown driver type: {driver_type}")

            try:
                driver.set_window_size(1920, 1080)
            except Exception:
                pass

            # Verify window / process associated with that launch
            window_verified = False
            for _ in range(10):
                try:
                    if len(driver.window_handles) > 0:
                        window_verified = True
                        break
                except Exception:
                    pass
                time.sleep(0.3)

            if not window_verified:
                try:
                    driver.quit()
                except Exception:
                    pass
                raise BrowserLaunchFailedError(
                    "Couldn't start the selected browser profile.",
                    safe_reason="Browser process launched but no interactive window appeared within timeout.",
                    technical_detail="Window handles check returned empty after 3 seconds."
                )

            # Record session in session lifecycle manager
            try:
                from backend.session_lifecycle import session_lifecycle
                session_lifecycle.record_session(
                    driver=driver,
                    browser_key=browser_key,
                    profile_dir=p_dir,
                    profile_path=profile.get("path", ""),
                    session_id=session_id
                )
            except Exception:
                pass

            return driver

        except (ProfileLockedError, StaleLockArtifactError, BrowserExecutableNotFoundError, BrowserLaunchFailedError, UnsupportedProfileAutomationError):
            raise
        except Exception as e:
            # Re-verify if an actual process suddenly appeared
            post_diag = cls.diagnose_profile(browser_key, profile_dir=p_dir, is_dedicated=is_dedicated)
            if post_diag["is_locked"]:
                raise ProfileLockedError(
                    post_diag["user_message"],
                    condition=post_diag["condition"],
                    pids=post_diag.get("matching_pids", [])
                )

            err_str = str(e)
            safe_reason = "Browser process failed to start or initialize window."
            if "devtoolsactiveport" in err_str.lower():
                safe_reason = (
                    "Browser process exited before remote debugging port opened. "
                    "Modern Chromium security restricts remote debugging on default user profiles. "
                    "We recommend using the Dedicated WhatsApp Session."
                )
            elif "cannot find" in err_str.lower() or "not found" in err_str.lower():
                safe_reason = "Browser binary or driver component not found."
            elif "version" in err_str.lower() or "driver" in err_str.lower():
                safe_reason = f"Driver compatibility error: {err_str[:120]}"

            raise BrowserLaunchFailedError(
                "Couldn't start the selected browser profile.",
                safe_reason=safe_reason,
                technical_detail=err_str
            )

    def __init__(self):
        self.driver = None

    def close_browser(self):
        """Terminates active driver session cleanly."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def start_browser(self, browser_key: Optional[str] = None, profile_dir: Optional[str] = None, headless: bool = False):
        """
        Instance helper method called by adapters to start driver with configured or specified profile.
        """
        from config_manager import ConfigManager
        cfg = ConfigManager().get_config()
        b_key = browser_key or getattr(cfg, "browser", "chrome") or "chrome"
        p_dir = profile_dir or getattr(cfg, "profile_dir", "__dedicated__") or "__dedicated__"

        profiles = self.get_profiles(b_key)
        matched = next((p for p in profiles if p["dir"] == p_dir), None)
        if not matched and profiles:
            matched = profiles[0]

        if not matched:
            raise RuntimeError(f"No valid profiles found for browser '{b_key}'")

        self.driver = self.launch_driver(b_key, matched, headless=headless)
        return self.driver

    @classmethod
    def check_profile_session(cls, browser_key: str, profile_dir: str) -> Dict[str, Any]:
        """
        Probes a browser profile in a controlled session to check WhatsApp Web sign-in state.
        Returns one of: 'Signed in', 'Needs QR sign-in', 'Browser unavailable', 'Could not verify'.
        Closes driver cleanly after check.
        """
        import time
        from selenium.webdriver.common.by import By
        from whatsapp_engine import WhatsAppEngine

        profiles = cls.get_profiles(browser_key)
        target_profile = next((p for p in profiles if p["dir"] == profile_dir), None)
        if not target_profile:
            return {
                "status": "Could not verify",
                "detail": f"Profile '{profile_dir}' not found on {browser_key}",
                "logged_in": False
            }

        # Check automation support before launching driver
        is_supp, unsupp_r, _ = is_profile_automation_supported(
            browser_key,
            profile_dir=profile_dir,
            is_dedicated=target_profile.get("is_dedicated", False),
            exe_path=cls.BROWSERS.get(browser_key, {}).get("exe_path")
        )
        if not is_supp:
            return {
                "status": "Cannot be automated",
                "is_locked": False,
                "lock_state": "unsupported_profile",
                "is_automation_supported": False,
                "detail": unsupp_r or "Selected Chrome profile cannot be automated due to Chrome 136+ security restrictions.",
                "logged_in": False
            }

        # Check availability before launching driver
        if target_profile.get("availability") == "in_use" and not target_profile.get("is_dedicated"):
            b_info = cls.BROWSERS.get(browser_key, {})
            b_name = b_info.get("name", browser_key.title())
            return {
                "status": "Profile in use",
                "is_locked": True,
                "lock_state": "locked",
                "detail": f"The selected browser profile is currently open in {b_name}. Close {b_name} completely to use this profile for automated messaging, or use a dedicated Relay session instead.",
                "logged_in": False
            }

        driver = None
        try:
            driver = cls.launch_driver(browser_key, target_profile, headless=True)
            driver.set_page_load_timeout(25)
            driver.get("https://web.whatsapp.com")

            start = time.time()
            while time.time() - start < 15:
                # 1. Check for logged in chat list
                for by_type, query in WhatsAppEngine.CHAT_LIST_SELECTORS:
                    try:
                        elems = driver.find_elements(by_type, query)
                        if any(e.is_displayed() for e in elems):
                            return {
                                "status": "Signed in",
                                "detail": "Active WhatsApp Web session detected with chat list present",
                                "logged_in": True
                            }
                    except Exception:
                        pass

                # 2. Check for QR code element
                try:
                    qr = driver.find_elements(By.CSS_SELECTOR, "canvas[aria-label*='Scan'], canvas, div[data-ref]")
                    if any(q.is_displayed() for q in qr):
                        return {
                            "status": "Needs QR sign-in",
                            "detail": "WhatsApp Web opened and requires scanning QR code to link device",
                            "logged_in": False
                        }
                except Exception:
                    pass

                time.sleep(1)

            return {
                "status": "Could not verify",
                "detail": "Session verification timed out before confirmation",
                "logged_in": False
            }

        except (ProfileLockedError, StaleLockArtifactError, BrowserExecutableNotFoundError, BrowserLaunchFailedError, UnsupportedProfileAutomationError) as be:
            if isinstance(be, UnsupportedProfileAutomationError):
                return {
                    "status": "Cannot be automated",
                    "is_locked": False,
                    "lock_state": "unsupported_profile",
                    "is_automation_supported": False,
                    "detail": be.safe_reason or str(be),
                    "logged_in": False
                }
            elif isinstance(be, ProfileLockedError):
                return {
                    "status": "Profile in use",
                    "is_locked": True,
                    "lock_state": "locked",
                    "detail": str(be),
                    "logged_in": False
                }
            elif isinstance(be, StaleLockArtifactError):
                return {
                    "status": "Stale lock detected",
                    "is_locked": False,
                    "is_stale_lock": True,
                    "lock_state": "stale_lock",
                    "detail": str(be),
                    "logged_in": False
                }
            elif isinstance(be, BrowserExecutableNotFoundError):
                return {
                    "status": "Browser unavailable",
                    "is_locked": False,
                    "lock_state": "available",
                    "detail": str(be),
                    "logged_in": False
                }
            else:  # BrowserLaunchFailedError
                return {
                    "status": "Browser unavailable",
                    "is_locked": False,
                    "lock_state": "available",
                    "detail": be.safe_reason or str(be),
                    "logged_in": False
                }
        except RuntimeError as re:
            re_str = str(re)
            is_locked = "open in another window" in re_str.lower() or "user data directory is already in use" in re_str.lower()
            return {
                "status": "Profile in use" if is_locked else "Browser unavailable",
                "is_locked": is_locked,
                "lock_state": "locked" if is_locked else "available",
                "detail": re_str,
                "logged_in": False
            }
        except Exception as e:
            err = str(e)
            if "executable" in err.lower() or "binary" in err.lower():
                return {
                    "status": "Browser unavailable",
                    "detail": "Browser executable or automation driver is unavailable",
                    "logged_in": False
                }
            return {
                "status": "Could not verify",
                "detail": f"Probe error: {err[:120]}",
                "logged_in": False
            }
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    @classmethod
    def resolve_conflict(
        cls,
        browser_key: str,
        profile_dir: str = "Default",
        is_dedicated: bool = False,
        force_personal: bool = False
    ) -> Dict[str, Any]:
        """
        Executes automatic conflict resolution via SessionLifecycleManager.
        Auto-restarts Relay-owned sessions, handles stale locks, and guards personal windows.
        """
        from backend.session_lifecycle import session_lifecycle
        return session_lifecycle.resolve_conflict(
            browser_key=browser_key,
            profile_dir=profile_dir,
            is_dedicated=is_dedicated,
            force_personal=force_personal
        )


