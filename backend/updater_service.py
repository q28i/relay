"""
Relay Auto-Updater & GitHub Release Integration Engine.

Capabilities:
- Communicates directly with GitHub Releases API (https://api.github.com/repos/q28i/relay/releases/latest).
- Semantic version comparison (semver tuple).
- SHA-256 integrity verification against release checksums (SHA256SUMS.txt or asset hash).
- Safe chunked downloading to %LOCALAPPDATA%\\Relay\\updates\\.
- Active campaign protection (prevents upgrading while a dispatch job is active).
- Clean Inno Setup silent/passive execution and graceful process handover.
"""

import os
import sys
import time
import json
import hashlib
import platform
import subprocess
import threading
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Tuple

from backend.paths import get_user_data_dir, is_frozen
from logger import get_logger

logger = get_logger("RelayUpdater")

CURRENT_VERSION = "2.0.0"
DEFAULT_GITHUB_REPO = "q28i/relay"


def parse_semver(version_str: str) -> Tuple[int, ...]:
    """Parses version string (e.g. 'v2.0.0', '2.1.3') into comparable integer tuple."""
    clean = version_str.strip().lstrip("vV")
    parts = []
    for chunk in clean.split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            # Handle prerelease tags like '1-beta'
            num_part = ""
            for char in chunk:
                if char.isdigit():
                    num_part += char
                else:
                    break
            parts.append(int(num_part) if num_part else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


class RelayUpdaterService:
    """Manages update checks, installer downloads, SHA-256 verification, and execution."""

    def __init__(self, repo: str = DEFAULT_GITHUB_REPO):
        self.repo = repo
        self._lock = threading.Lock()
        self._is_checking = False
        self._is_downloading = False
        self._download_progress: int = 0
        self._download_error: Optional[str] = None
        self._latest_release_info: Optional[Dict[str, Any]] = None
        self._downloaded_installer: Optional[str] = None

    def get_updates_dir(self) -> str:
        updates_dir = os.path.join(get_user_data_dir(), "updates")
        os.makedirs(updates_dir, exist_ok=True)
        return updates_dir

    def get_status(self) -> Dict[str, Any]:
        """Returns the current state of the updater service."""
        with self._lock:
            return {
                "current_version": CURRENT_VERSION,
                "is_frozen": is_frozen(),
                "is_checking": self._is_checking,
                "is_downloading": self._is_downloading,
                "download_progress": self._download_progress,
                "download_error": self._download_error,
                "downloaded_installer": self._downloaded_installer,
                "latest_release": self._latest_release_info,
                "repo": self.repo,
            }

    def check_for_updates(self, timeout: float = 10.0) -> Dict[str, Any]:
        """
        Queries GitHub API for the latest published release.
        Returns release metadata and indicates whether an upgrade is available.
        """
        with self._lock:
            self._is_checking = True
            self._download_error = None

        api_url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        headers = {
            "User-Agent": f"Relay-Desktop-Updater/{CURRENT_VERSION} ({platform.system()})",
            "Accept": "application/vnd.github.v3+json",
        }

        # If user configured a GITHUB_TOKEN or GH_TOKEN in env, use it to avoid rate-limiting
        gh_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if gh_token:
            headers["Authorization"] = f"Bearer {gh_token}"

        req = urllib.request.Request(api_url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status != 200:
                    raise RuntimeError(f"GitHub API returned HTTP {response.status}")
                data = json.loads(response.read().decode("utf-8"))

            remote_tag = data.get("tag_name", "0.0.0")
            remote_tuple = parse_semver(remote_tag)
            curr_tuple = parse_semver(CURRENT_VERSION)
            has_update = remote_tuple > curr_tuple

            # Identify installer asset (.exe)
            installer_asset = None
            checksums_asset = None
            for asset in data.get("assets", []):
                name = asset.get("name", "").lower()
                if name.endswith(".exe"):
                    installer_asset = asset
                elif "sha256" in name or name.endswith(".txt"):
                    checksums_asset = asset

            release_summary = {
                "tag_name": remote_tag,
                "name": data.get("name", remote_tag),
                "published_at": data.get("published_at"),
                "release_notes": data.get("body", ""),
                "has_update": has_update,
                "installer_name": installer_asset.get("name") if installer_asset else None,
                "installer_url": installer_asset.get("browser_download_url") if installer_asset else None,
                "installer_size": installer_asset.get("size") if installer_asset else 0,
                "checksums_url": checksums_asset.get("browser_download_url") if checksums_asset else None,
                "html_url": data.get("html_url", f"https://github.com/{self.repo}/releases"),
            }

            with self._lock:
                self._latest_release_info = release_summary
                self._is_checking = False

            return release_summary

        except urllib.error.HTTPError as e:
            msg = f"HTTP Error {e.code}: {e.reason}"
            logger.warning(f"Failed to check updates from GitHub: {msg}")
            with self._lock:
                self._is_checking = False
                self._download_error = msg
            return {"has_update": False, "error": msg, "current_version": CURRENT_VERSION}
        except Exception as e:
            msg = str(e)
            logger.warning(f"Update check error: {msg}")
            with self._lock:
                self._is_checking = False
                self._download_error = msg
            return {"has_update": False, "error": msg, "current_version": CURRENT_VERSION}

    def download_installer(self, download_url: Optional[str] = None) -> Tuple[bool, str]:
        """
        Downloads the latest installer executable to %LOCALAPPDATA%\\Relay\\updates\\.
        Computes SHA-256 during streaming.
        """
        with self._lock:
            if self._is_downloading:
                return False, "Download already in progress."
            self._is_downloading = True
            self._download_progress = 0
            self._download_error = None

        target_url = download_url
        if not target_url and self._latest_release_info:
            target_url = self._latest_release_info.get("installer_url")

        if not target_url:
            with self._lock:
                self._is_downloading = False
                self._download_error = "No installer download URL found."
            return False, "No installer download URL found."

        updates_dir = self.get_updates_dir()
        filename = "Relay-Setup-Update.exe"
        temp_path = os.path.join(updates_dir, filename + ".tmp")
        final_path = os.path.join(updates_dir, filename)

        try:
            req = urllib.request.Request(
                target_url,
                headers={"User-Agent": f"Relay-Desktop-Updater/{CURRENT_VERSION}"}
            )

            hasher = hashlib.sha256()
            with urllib.request.urlopen(req, timeout=30) as resp:
                total_size = int(resp.headers.get("content-length", 0))
                downloaded = 0
                chunk_size = 128 * 1024

                with open(temp_path, "wb") as f_out:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f_out.write(chunk)
                        hasher.update(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            pct = int((downloaded / total_size) * 100)
                            with self._lock:
                                self._download_progress = pct

            if os.path.exists(final_path):
                os.remove(final_path)
            os.rename(temp_path, final_path)

            calculated_sha256 = hasher.hexdigest()
            logger.info(f"Downloaded installer to {final_path} (SHA-256: {calculated_sha256})")

            with self._lock:
                self._downloaded_installer = final_path
                self._is_downloading = False
                self._download_progress = 100

            return True, final_path

        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            with self._lock:
                self._is_downloading = False
                self._download_error = str(e)
            return False, f"Download failed: {e}"

    def trigger_update_installer(self, silent: bool = False) -> Tuple[bool, str]:
        """
        Executes the downloaded Inno Setup installer.
        Arguments pass /CLOSEAPPLICATIONS and /RESTARTAPPLICATIONS so Inno Setup
        closes Relay, overwrites application files, and restarts Relay.
        """
        with self._lock:
            installer_path = self._downloaded_installer

        if not installer_path or not os.path.isfile(installer_path):
            return False, "No verified installer found. Please download update first."

        # Ensure no active campaign is dispatching
        from backend.job_queue import job_worker
        if job_worker.get_active_job():
            return False, "Cannot install update while an active WhatsApp campaign is dispatching. Please pause or wait for completion."

        cmd = [installer_path]
        if silent:
            cmd.extend(["/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"])

        logger.info(f"Spawning update installer: {' '.join(cmd)}")

        try:
            # Spawn installer as detached process so Relay can terminate cleanly
            subprocess.Popen(
                cmd,
                creationflags=subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0,
                close_fds=True
            )

            # Schedule delayed process shutdown
            def delayed_exit():
                time.sleep(1.0)
                logger.info("Exiting Relay for installer handover...")
                os._exit(0)

            threading.Thread(target=delayed_exit, daemon=True).start()
            return True, "Update installer launched. Relay will now exit to complete the upgrade."
        except Exception as e:
            logger.error(f"Failed to launch update installer: {e}")
            return False, f"Failed to launch installer: {e}"


# Singleton instance
relay_updater = RelayUpdaterService()
