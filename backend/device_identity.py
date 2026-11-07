"""
Relay Device Identity & Local Hardware Diagnostics Manager.

Provides:
- Persistent Installation ID: UUIDv4 format (relay-xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx)
- Survives restarts and application updates, stored in %LOCALAPPDATA%\\Relay\\device_identity.json
- Atomic file writes (temp file + fsync + os.replace) preventing corruption
- Not derived from hardware serials, MAC, CPU IDs, or motherboard UUIDs
- Local device info gathering: OS, CPU, RAM, disk, locale, timezone, app mode, browsers
- Privacy redaction for diagnostics export
- Developer device registration & enrollment
- Channel preferences (stable, beta, dev)
"""

import os
import sys
import re
import json
import time
import uuid
import socket
import locale
import shutil
import getpass
import platform
import subprocess
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

from backend.paths import (
    get_user_data_dir,
    get_bundle_dir,
    get_logs_dir,
    get_session_dir,
    is_frozen,
)
from logger import get_logger

logger = get_logger("DeviceIdentity")

CURRENT_VERSION = "2.0.0"
IDENTITY_SCHEMA_VERSION = 1
UUIDV4_RELAY_PATTERN = r"^relay-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
VALID_CHANNELS = ("stable", "beta", "dev")
VALID_ROLES = ("standard", "developer")

_STARTUP_TIMESTAMP = datetime.now(timezone.utc).isoformat()


def generate_installation_id() -> str:
    """Generates a random UUIDv4 formatted Relay installation ID."""
    return f"relay-{uuid.uuid4()}"


def is_valid_installation_id(val: str) -> bool:
    """Verifies format compliance with relay-UUIDv4."""
    if not isinstance(val, str):
        return False
    return bool(re.match(UUIDV4_RELAY_PATTERN, val, re.IGNORECASE))


class DeviceIdentityManager:
    """Manages persistent device identity, developer enrollment, and hardware diagnostics."""

    def __init__(self):
        self._lock = threading.RLock()
        self._cached_identity: Optional[Dict[str, Any]] = None

    def get_identity_path(self) -> str:
        """Returns the absolute path to device_identity.json in persistent user data."""
        return os.path.join(get_user_data_dir(), "device_identity.json")

    def _read_identity_from_disk(self) -> Optional[Dict[str, Any]]:
        path = self.get_identity_path()
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and is_valid_installation_id(data.get("installation_id")):
                return data
            logger.warning("device_identity.json had invalid format; will regenerate.")
            return None
        except Exception as e:
            logger.warning(f"Failed to read device_identity.json: {e}; will regenerate.")
            return None

    def _write_identity_to_disk(self, data: Dict[str, Any]) -> None:
        """Writes identity JSON atomically via a temp file in the same directory."""
        path = self.get_identity_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except (AttributeError, OSError):
                    pass
            os.replace(tmp_path, path)
        except Exception as e:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            logger.error(f"Failed to write device_identity.json atomically: {e}")
            raise

    def get_device_identity(self) -> Dict[str, Any]:
        """
        Retrieves or generates the persistent device identity.
        Survives application restarts and updates.
        """
        with self._lock:
            if self._cached_identity is not None:
                return dict(self._cached_identity)

            disk_data = self._read_identity_from_disk()
            now_iso = datetime.now(timezone.utc).isoformat()

            if disk_data is not None:
                # Update last_startup_at
                disk_data["last_startup_at"] = now_iso
                # Ensure all schema fields exist
                disk_data.setdefault("schema_version", IDENTITY_SCHEMA_VERSION)
                disk_data.setdefault("device_label", socket.gethostname() or "Relay Workstation")
                disk_data.setdefault("device_role", "standard")
                disk_data.setdefault("update_channel", "stable")
                disk_data.setdefault("created_at", now_iso)
                disk_data.setdefault("developer_enrolled_at", None)
                disk_data.setdefault("developer_token", None)
                disk_data.setdefault("update_feed_override", None)
                disk_data.setdefault("verbose_updater_logging", False)
                self._write_identity_to_disk(disk_data)
                self._cached_identity = disk_data
                return dict(self._cached_identity)

            # Generate new identity
            new_id = generate_installation_id()
            default_label = socket.gethostname() or "Relay Workstation"
            identity = {
                "schema_version": IDENTITY_SCHEMA_VERSION,
                "installation_id": new_id,
                "device_label": default_label,
                "device_role": "standard",
                "update_channel": "stable",
                "created_at": now_iso,
                "last_startup_at": now_iso,
                "developer_enrolled_at": None,
                "developer_token": None,
                "update_feed_override": None,
                "verbose_updater_logging": False,
            }
            self._write_identity_to_disk(identity)
            self._cached_identity = identity
            logger.info(f"Initialized new Relay Installation ID: {new_id} ({default_label})")
            return dict(self._cached_identity)

    def set_device_label(self, new_label: str) -> Dict[str, Any]:
        """Updates the friendly local device label."""
        cleaned = (new_label or "").strip()
        if not cleaned:
            raise ValueError("Device label cannot be empty.")
        with self._lock:
            current = self.get_device_identity()
            current["device_label"] = cleaned[:64]
            self._write_identity_to_disk(current)
            self._cached_identity = current
            logger.info(f"Updated device label to: '{current['device_label']}'")
            return dict(self._cached_identity)

    def set_update_channel(self, channel: str) -> Dict[str, Any]:
        """Updates update channel preference (stable, beta, dev)."""
        clean_ch = (channel or "").strip().lower()
        if clean_ch not in VALID_CHANNELS:
            raise ValueError(f"Invalid update channel '{channel}'. Allowed: {VALID_CHANNELS}")
        with self._lock:
            current = self.get_device_identity()
            current["update_channel"] = clean_ch
            self._write_identity_to_disk(current)
            self._cached_identity = current
            logger.info(f"Updated update channel to: '{clean_ch}'")
            return dict(self._cached_identity)

    def register_as_developer(
        self,
        label: Optional[str] = None,
        token: Optional[str] = None,
        channel: str = "dev"
    ) -> Dict[str, Any]:
        """
        Enrolls the local device as a developer workstation.
        Persists developer status across restarts and upgrades.
        """
        clean_ch = (channel or "dev").strip().lower()
        if clean_ch not in VALID_CHANNELS:
            clean_ch = "dev"

        with self._lock:
            current = self.get_device_identity()
            current["device_role"] = "developer"
            current["update_channel"] = clean_ch
            if label and label.strip():
                current["device_label"] = label.strip()[:64]
            current["developer_enrolled_at"] = datetime.now(timezone.utc).isoformat()
            if token and token.strip():
                current["developer_token"] = token.strip()
            self._write_identity_to_disk(current)
            self._cached_identity = current
            logger.info(f"Device enrolled as DEVELOPER: {current['installation_id']} ({current['device_label']})")
            return dict(self._cached_identity)

    def unregister_developer(self) -> Dict[str, Any]:
        """Reverts device back to Standard role and resets channel to stable."""
        with self._lock:
            current = self.get_device_identity()
            current["device_role"] = "standard"
            current["update_channel"] = "stable"
            current["developer_enrolled_at"] = None
            current["developer_token"] = None
            self._write_identity_to_disk(current)
            self._cached_identity = current
            logger.info(f"Device reverted to STANDARD role: {current['installation_id']}")
            return dict(self._cached_identity)

    def reset_device_identity(self) -> Dict[str, Any]:
        """
        Regenerates a new unique Installation ID and resets settings.
        Requires explicit confirmation from caller.
        """
        with self._lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            new_id = generate_installation_id()
            default_label = socket.gethostname() or "Relay Workstation"
            identity = {
                "schema_version": IDENTITY_SCHEMA_VERSION,
                "installation_id": new_id,
                "device_label": default_label,
                "device_role": "standard",
                "update_channel": "stable",
                "created_at": now_iso,
                "last_startup_at": now_iso,
                "developer_enrolled_at": None,
                "developer_token": None,
                "update_feed_override": None,
                "verbose_updater_logging": False,
            }
            self._write_identity_to_disk(identity)
            self._cached_identity = identity
            logger.info(f"Reset device identity. New Installation ID: {new_id}")
            return dict(self._cached_identity)

    # -------------------------------------------------------------------------
    # Diagnostics & System Metrics Gathering
    # -------------------------------------------------------------------------

    def get_system_info(self) -> Dict[str, Any]:
        """Collects local OS and hardware specifications safely."""
        # RAM via Windows API (ctypes) or fallback
        total_ram_gb = 0.0
        avail_ram_gb = 0.0
        if sys.platform == "win32":
            try:
                import ctypes

                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                    total_ram_gb = round(stat.ullTotalPhys / (1024**3), 2)
                    avail_ram_gb = round(stat.ullAvailPhys / (1024**3), 2)
            except Exception as e:
                logger.debug(f"Failed to query RAM via ctypes: {e}")

        # Disk space on persistent data drive
        free_disk_gb = 0.0
        total_disk_gb = 0.0
        try:
            usage = shutil.disk_usage(get_user_data_dir())
            total_disk_gb = round(usage.total / (1024**3), 2)
            free_disk_gb = round(usage.free / (1024**3), 2)
        except Exception:
            pass

        # Locale and Timezone
        loc = "unknown"
        try:
            loc = "-".join(filter(None, locale.getdefaultlocale()))
        except Exception:
            pass

        tz = "UTC"
        try:
            tz = f"{time.tzname[0]} ({time.strftime('%z')})"
        except Exception:
            pass

        return {
            "os_name": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "os_build": platform.win32_ver()[1] if sys.platform == "win32" else "",
            "cpu_arch": platform.machine(),
            "cpu_model": platform.processor(),
            "cpu_logical_cores": os.cpu_count() or 1,
            "total_ram_gb": total_ram_gb,
            "available_ram_gb": avail_ram_gb,
            "total_disk_gb": total_disk_gb,
            "free_disk_gb": free_disk_gb,
            "locale": loc,
            "timezone": tz,
        }

    def get_application_info(self) -> Dict[str, Any]:
        """Collects application execution mode, runtime paths, and Git commit."""
        # Git commit
        commit = None
        if not is_frozen():
            try:
                res = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    cwd=get_bundle_dir()
                )
                if res.returncode == 0 and res.stdout.strip():
                    commit = res.stdout.strip()
            except Exception:
                pass
        if not commit:
            commit = "5a4ccfc" if is_frozen() else "development"

        # Elevation
        is_admin = False
        if sys.platform == "win32":
            try:
                import ctypes
                is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
            except Exception:
                pass
        else:
            try:
                is_admin = os.geteuid() == 0
            except AttributeError:
                pass

        return {
            "version": CURRENT_VERSION,
            "git_commit": commit,
            "execution_mode": "Frozen Desktop Package" if is_frozen() else "Development Source",
            "is_frozen": is_frozen(),
            "bundle_dir": get_bundle_dir(),
            "user_data_dir": get_user_data_dir(),
            "logs_dir": get_logs_dir(),
            "pid": os.getpid(),
            "elevation": "Administrator" if is_admin else "Standard User",
            "startup_timestamp": _STARTUP_TIMESTAMP,
            "uptime_seconds": int(time.time() - time.mktime(datetime.fromisoformat(_STARTUP_TIMESTAMP).timetuple())),
        }

    def get_browser_environment(self) -> Dict[str, Any]:
        """Detects installed browsers and active session state."""
        installed = []
        try:
            from browser_manager import BrowserManager
            detected = BrowserManager.get_installed_browsers()
            for key, info in detected.items():
                installed.append({
                    "key": key,
                    "name": info.get("name", key),
                    "exe_path": info.get("exe_path"),
                })
        except Exception as e:
            logger.debug(f"Failed to detect browsers: {e}")

        # Active session status
        is_active = False
        try:
            from backend.session_lifecycle import session_lifecycle
            is_active = session_lifecycle.is_session_active()
        except Exception:
            pass

        return {
            "installed_browsers": installed,
            "session_dir": get_session_dir(),
            "active_session": is_active,
        }

    def get_diagnostics_report(self, redact: bool = False) -> Dict[str, Any]:
        """
        Compiles a comprehensive diagnostic report.
        If redact=True, removes or replaces username, machine hostname, file path user parts,
        and tokens with redacted placeholders. Strictly excludes contacts, messages, and tokens.
        """
        identity = self.get_device_identity()
        system = self.get_system_info()
        app_info = self.get_application_info()
        browser = self.get_browser_environment()

        current_user = getpass.getuser()
        hostname = socket.gethostname()

        def sanitize_path(p: Optional[str]) -> Optional[str]:
            if not p or not isinstance(p, str):
                return p
            if redact and current_user:
                return p.replace(current_user, "[REDACTED_USER]")
            return p

        report_identity = {
            "installation_id": identity["installation_id"],
            "device_label": identity["device_label"],
            "machine_name": "[REDACTED_HOST]" if redact else hostname,
            "local_username": "[REDACTED_USER]" if redact else current_user,
            "device_role": identity["device_role"],
            "update_channel": identity["update_channel"],
            "created_at": identity["created_at"],
            "last_startup_at": identity["last_startup_at"],
            "developer_enrolled_at": identity.get("developer_enrolled_at"),
            "developer_token_present": bool(identity.get("developer_token")),
        }

        report_app = {
            "version": app_info["version"],
            "git_commit": app_info["git_commit"],
            "execution_mode": app_info["execution_mode"],
            "is_frozen": app_info["is_frozen"],
            "bundle_dir": sanitize_path(app_info["bundle_dir"]),
            "user_data_dir": sanitize_path(app_info["user_data_dir"]),
            "logs_dir": sanitize_path(app_info["logs_dir"]),
            "pid": app_info["pid"],
            "elevation": app_info["elevation"],
            "startup_timestamp": app_info["startup_timestamp"],
            "uptime_seconds": app_info["uptime_seconds"],
        }

        report_browsers = {
            "installed_browsers": [
                {
                    "key": b["key"],
                    "name": b["name"],
                    "exe_path": sanitize_path(b.get("exe_path")),
                }
                for b in browser["installed_browsers"]
            ],
            "session_dir": sanitize_path(browser["session_dir"]),
            "active_session": browser["active_session"],
        }

        return {
            "report_timestamp": datetime.now(timezone.utc).isoformat(),
            "privacy_redacted": redact,
            "identity": report_identity,
            "system": system,
            "application": report_app,
            "browser_environment": report_browsers,
        }

    def export_diagnostics_json(self, redact: bool = False) -> str:
        """Returns JSON-serialized diagnostic report."""
        report = self.get_diagnostics_report(redact=redact)
        return json.dumps(report, indent=2)


# Global singleton instance
device_identity_manager = DeviceIdentityManager()
