"""
Relay Standalone Desktop Launcher.

Features:
- Single-instance enforcement via Windows Named Mutex (Global\\RelayWhatsAppAutomationMutex).
  If already running, brings the existing web dashboard into view and exits immediately.
- Automatic runtime data directory initialization (%LOCALAPPDATA%\\Relay).
- Dynamic port conflict resolution (binds to 8000 or searches 8001-8010).
- Healthcheck polling before launching the default browser.
- Clean process shutdown and runtime state tracking.
"""

import os
import sys
import time
import json
import socket
import urllib.request
import webbrowser
import threading
import signal
import ctypes
from ctypes import wintypes
from typing import Optional, Tuple

from backend.paths import (
    is_frozen,
    get_user_data_dir,
    ensure_data_dirs,
    migrate_legacy_data_if_needed,
)
from logger import get_logger

logger = get_logger("RelayLauncher")

MUTEX_NAME = "Global\\RelayWhatsAppAutomationMutex"
LOCAL_MUTEX_NAME = "Local\\RelayWhatsAppAutomationMutex"
ERROR_ALREADY_EXISTS = 183


class SingleInstanceLock:
    """Windows Named Mutex manager for desktop single-instance enforcement."""

    def __init__(self):
        self.mutex_handle = None
        self.is_primary = False

    def acquire(self) -> bool:
        """
        Attempts to acquire the single-instance mutex.
        Returns True if this is the primary instance; False if another instance exists.
        """
        if sys.platform != "win32":
            return True

        kernel32 = ctypes.windll.kernel32
        # Try Global namespace first, fall back to Local if restricted
        for name in [MUTEX_NAME, LOCAL_MUTEX_NAME]:
            kernel32.SetLastError(0)
            handle = kernel32.CreateMutexW(None, True, name)
            last_err = kernel32.GetLastError()
            if handle:
                if last_err == ERROR_ALREADY_EXISTS:
                    kernel32.CloseHandle(handle)
                    self.mutex_handle = None
                    self.is_primary = False
                    return False
                self.mutex_handle = handle
                self.is_primary = True
                return True

        return True

    def release(self):
        """Releases the mutex handle upon exit."""
        if self.mutex_handle and sys.platform == "win32":
            try:
                ctypes.windll.kernel32.ReleaseMutex(self.mutex_handle)
                ctypes.windll.kernel32.CloseHandle(self.mutex_handle)
            except Exception:
                pass
            self.mutex_handle = None


def get_runtime_state_file() -> str:
    return os.path.join(get_user_data_dir(), "relay_runtime.json")


def save_runtime_state(host: str, port: int):
    path = get_runtime_state_file()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "host": host,
                "port": port,
                "pid": os.getpid(),
                "url": f"http://{host}:{port}",
                "started_at": time.time()
            }, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not write runtime state: {e}")


def load_runtime_state() -> Optional[dict]:
    path = get_runtime_state_file()
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def clear_runtime_state():
    path = get_runtime_state_file()
    if os.path.isfile(path):
        try:
            os.remove(path)
        except Exception:
            pass


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Checks whether the given TCP port is currently occupied."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def check_relay_health(url: str, timeout: float = 1.0) -> bool:
    """Pings /api/health to verify if a responsive Relay instance is listening."""
    health_url = f"{url.rstrip('/')}/api/health"
    try:
        req = urllib.request.Request(health_url, headers={"User-Agent": "Relay-HealthCheck"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("status") == "healthy"
    except Exception:
        pass
    return False


def find_available_port(start_port: int = 8000, max_attempts: int = 10, host: str = "127.0.0.1") -> int:
    """Finds an unused port or verifies if existing port is healthy."""
    for port in range(start_port, start_port + max_attempts):
        if not is_port_in_use(port, host):
            return port
    raise RuntimeError(f"No available TCP port found between {start_port} and {start_port + max_attempts - 1}")


def poll_and_launch_browser(url: str, max_wait_sec: float = 12.0):
    """Waits for Relay server to report healthy before opening the default browser."""
    start_time = time.time()
    while time.sleep(0.3) or (time.time() - start_time) < max_wait_sec:
        if check_relay_health(url, timeout=0.8):
            logger.info(f"Relay backend healthy at {url}. Opening default browser...")
            try:
                webbrowser.open(url)
            except Exception as e:
                logger.warning(f"Failed to open browser automatically: {e}")
            return
    # Fallback open even if health check timed out
    logger.info("Healthcheck deadline passed. Opening browser anyway...")
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    # 1. Single Instance Check
    lock = SingleInstanceLock()
    if not lock.acquire():
        # Another instance is running
        state = load_runtime_state()
        running_url = state.get("url", "http://127.0.0.1:8000") if state else "http://127.0.0.1:8000"
        print(f"[INFO] Relay is already running at {running_url}. Activating existing window...")
        try:
            webbrowser.open(running_url)
        except Exception:
            pass
        sys.exit(0)

    # 2. Storage & Paths Initialization
    ensure_data_dirs()
    migrate_legacy_data_if_needed()

    # 3. Dynamic Port Selection
    host = "127.0.0.1"
    target_port = 8000
    if is_port_in_use(target_port, host):
        # Check if it's already a responsive Relay server
        if check_relay_health(f"http://{host}:{target_port}", timeout=0.6):
            print(f"[INFO] Existing Relay server responded at http://{host}:{target_port}. Opening browser...")
            webbrowser.open(f"http://{host}:{target_port}")
            lock.release()
            sys.exit(0)
        # Otherwise find next free port
        target_port = find_available_port(start_port=8001, host=host)

    url = f"http://{host}:{target_port}"
    save_runtime_state(host, target_port)

    print("=" * 65)
    print("  [RELAY] WhatsApp Bulk Messenger Pro - Desktop Launcher")
    print("=" * 65)
    print(f"  * Mode            : {'Packaged Desktop Executable' if is_frozen() else 'Development'}")
    print(f"  * Data Directory  : {get_user_data_dir()}")
    print(f"  * Server URL      : {url}")
    print(f"  * Single Instance : Active (Mutex Acquired)")
    print("=" * 65)

    # 4. Asynchronously launch browser once healthy
    browser_thread = threading.Thread(target=poll_and_launch_browser, args=(url,), daemon=True)
    browser_thread.start()

    # 5. Clean Exit Handlers
    def cleanup(*args):
        logger.info("Cleaning up Relay runtime state...")
        clear_runtime_state()
        lock.release()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # 6. Start ASGI Server
    import uvicorn
    from backend.app import app

    try:
        uvicorn.run(
            app,
            host=host,
            port=target_port,
            log_level="info",
            access_log=False
        )
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
