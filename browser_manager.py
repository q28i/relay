"""
Browser and Profile Manager for WhatsApp Automation
Detects installed Chromium browsers (Chrome, Edge, Brave) and their user profiles on Windows.
Allows persistent WhatsApp Web sessions without re-scanning QR codes.
"""

import os
import json
import winreg
from typing import List, Dict, Optional, Tuple
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions


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
    def get_profiles(cls, browser_key: str) -> List[Dict[str, str]]:
        """
        Discovers available profiles for the given browser.
        Also includes a Dedicated Automation Profile to avoid lock conflicts with active personal windows.
        """
        profiles = []
        # Option 0: Dedicated Profile for WhatsApp Automation
        base_dir = os.path.dirname(os.path.abspath(__file__))
        dedicated_dir = os.path.join(base_dir, "whatsapp_browser_session")
        profiles.append({
            "dir": "__dedicated__",
            "name": "Dedicated WhatsApp Session (Recommended: never conflicts with active windows)",
            "path": dedicated_dir,
            "is_dedicated": True
        })

        if browser_key not in cls.BROWSERS:
            return profiles

        user_data = cls.BROWSERS[browser_key]["user_data_path"]
        if not os.path.isdir(user_data):
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
                        profiles.append({
                            "dir": dir_name,
                            "name": f"{display_name} ({dir_name})",
                            "path": user_data,
                            "is_dedicated": False
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
                        profiles.append({
                            "dir": entry,
                            "name": entry,
                            "path": user_data,
                            "is_dedicated": False
                        })
                        seen_dirs.add(entry)
        except OSError:
            pass

        return profiles

    @classmethod
    def launch_driver(cls, browser_key: str, profile: dict, headless: bool = False):
        """
        Initializes and returns a Selenium WebDriver instance with persistent session support.
        """
        browser_info = cls.BROWSERS.get(browser_key)
        if not browser_info:
            raise ValueError(f"Unsupported browser: {browser_key}")

        driver_type = browser_info["driver_type"]

        if driver_type in ("chrome", "brave"):
            options = ChromeOptions()
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
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)

            if headless:
                options.add_argument("--headless=new")

            driver = webdriver.Chrome(options=options)

        elif driver_type == "edge":
            options = EdgeOptions()
            if profile.get("is_dedicated"):
                options.add_argument(f"--user-data-dir={profile['path']}")
            else:
                options.add_argument(f"--user-data-dir={profile['path']}")
                options.add_argument(f"--profile-directory={profile['dir']}")

            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-infobars")
            options.add_argument("--start-maximized")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)

            if headless:
                options.add_argument("--headless=new")

            driver = webdriver.Edge(options=options)

        else:
            raise ValueError(f"Unknown driver type: {driver_type}")

        return driver

