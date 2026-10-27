"""
Device ID Manager & Logger for WhatsApp Bulk Messenger Pro
Generates a unique, immutable hardware identifier for Windows devices.
Identifies developer vs client devices, logs audits, and handles licensing.
"""

import os
import json
import uuid
import winreg
import platform
import hashlib
import datetime
from typing import Dict, Tuple

# Whitelisted Developer Hardware IDs (Logs user's machine as DEVELOPER)
DEVELOPER_WHITELIST = {
    "0ef8acc4-40ca-49bd-bfba-76f5da0f6e92",
    "A723A0AA431176BD",
    "DEV-0EF8ACC4-40CA-49BD-BFBA-76F5DA0F6E92",
    "DEV-A723A0AA431176BD"
}

AUDIT_LOG_FILE = "device_audit.log"
CONFIG_FILE = "auth_config.json"


class DeviceManager:
    _cached_info = None

    @classmethod
    def get_device_info(cls) -> Dict[str, str]:
        """Retrieves and caches immutable hardware device information."""
        if cls._cached_info:
            return cls._cached_info

        # 1. Windows MachineGuid
        guid = ""
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
                guid, _ = winreg.QueryValueEx(k, "MachineGuid")
        except Exception:
            guid = str(uuid.uuid4())

        # 2. Hardware MAC node fallback
        node = str(uuid.getnode())

        # 3. Clean SHA-256 short hash
        combined = f"{guid.lower().strip()}-{node}"
        short_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16].upper()

        full_device_id = f"DEV-{guid.upper()}"
        short_device_id = f"DEV-{short_hash}"

        # 4. Check if developer
        is_dev = (
            guid.lower().strip() in [d.lower() for d in DEVELOPER_WHITELIST] or
            short_hash in DEVELOPER_WHITELIST or
            full_device_id in DEVELOPER_WHITELIST or
            short_device_id in DEVELOPER_WHITELIST
        )

        role = "DEVELOPER" if is_dev else "CLIENT"

        info = {
            "device_id": full_device_id,
            "short_id": short_device_id,
            "raw_guid": guid,
            "node": node,
            "role": role,
            "is_developer": is_dev,
            "machine_name": platform.node(),
            "os": f"{platform.system()} {platform.release()} ({platform.architecture()[0]})",
            "python_version": platform.python_version()
        }

        cls._cached_info = info
        return info

    @classmethod
    def is_developer(cls) -> bool:
        """Returns True if the current device is the authorized developer."""
        return cls.get_device_info()["is_developer"]

    @classmethod
    def log_device_startup(cls, app_version: str = "1.2.0"):
        """Logs device startup and audit trace."""
        info = cls.get_device_info()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        log_path = os.path.join(base_dir, AUDIT_LOG_FILE)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = (
            f"[{timestamp}] Device: {info['short_id']} | "
            f"GUID: {info['raw_guid']} | "
            f"Machine: {info['machine_name']} | "
            f"Role: {info['role']} | "
            f"Version: v{app_version} | "
            f"OS: {info['os']}\n"
        )

        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception:
            pass

    @classmethod
    def save_auth_config(cls, extra_dev_ids: list = None):
        """Saves current device state and authorization configuration."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        cfg_path = os.path.join(base_dir, CONFIG_FILE)

        info = cls.get_device_info()
        whitelist = list(DEVELOPER_WHITELIST)
        if extra_dev_ids:
            for d in extra_dev_ids:
                if d not in whitelist:
                    whitelist.append(d)

        data = {
            "current_device": {
                "device_id": info["device_id"],
                "short_id": info["short_id"],
                "role": info["role"],
                "machine_name": info["machine_name"]
            },
            "authorized_developer_devices": whitelist,
            "last_verified": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        try:
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[WARNING] Could not save {CONFIG_FILE}: {e}")


if __name__ == "__main__":
    d = DeviceManager.get_device_info()
    DeviceManager.log_device_startup()
    DeviceManager.save_auth_config()
    print("Device Info:")
    for k, v in d.items():
        print(f"  {k}: {v}")

