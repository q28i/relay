"""
Relay Auto-Updater & GitHub Release Integration Engine.

Capabilities:
- Communicates directly with GitHub Releases API (list /repos/q28i/relay/releases and /latest).
- Semantic version comparison (SemVer 2.0.0 with channel and prerelease tag support).
- Channel filtering: 'stable', 'beta', and 'dev' with targeted developer rollouts.
- SHA-256 integrity verification against release checksums (SHA256SUMS.txt).
- Safe chunked downloading to %LOCALAPPDATA%\\Relay\\updates\\.
- Active campaign protection (verifies both in-memory job worker AND SQLite persistent queue).
- Clean Inno Setup silent/passive execution and graceful process handover.
"""

import os
import sys
import re
import time
import json
import hashlib
import platform
import subprocess
import threading
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Tuple, List

from backend.paths import get_user_data_dir, is_frozen
from logger import get_logger

logger = get_logger("RelayUpdater")

CURRENT_VERSION = "2.0.0"
DEFAULT_GITHUB_REPO = "q28i/relay"

PRERELEASE_RANKS = {"dev": 1, "alpha": 2, "beta": 3, "rc": 4, "": 10}


def parse_semver(version_str: str) -> Tuple[int, ...]:
    """
    Parses version string (e.g. 'v2.0.0', '2.1.3') into comparable 3-element integer tuple.
    Preserves exact backward compatibility with existing tests and scripts.
    """
    clean = version_str.strip().lstrip("vV")
    parts = []
    for chunk in clean.split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
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


class SemVer:
    """
    Full SemVer 2.0.0 representation supporting prerelease channels and comparison.
    Ranks: dev (1) < alpha (2) < beta (3) < rc (4) < stable (10).
    """

    def __init__(
        self,
        major: int,
        minor: int,
        patch: int,
        prerelease_type: str = "",
        prerelease_num: int = 0,
        raw: str = ""
    ):
        self.major = major
        self.minor = minor
        self.patch = patch
        self.prerelease_type = (prerelease_type or "").lower().strip()
        self.prerelease_num = prerelease_num
        self.raw = raw

    @classmethod
    def parse(cls, v: str) -> "SemVer":
        if not v or not isinstance(v, str):
            return cls(0, 0, 0, "", 0, "")
        raw = v.strip().lstrip("vV")
        # Matches patterns like: 2.1.0, 2.1.0-beta.1, 2.1.0-rc2, 2.1.0-dev.20261108
        m = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-([a-zA-Z]+)(?:\.?(\d+))?)?", raw)
        if not m:
            return cls(0, 0, 0, "", 0, raw)
        maj = int(m.group(1) or 0)
        min_ = int(m.group(2) or 0)
        patch = int(m.group(3) or 0)
        pr_type = (m.group(4) or "").lower()
        pr_num = int(m.group(5) or 0)
        return cls(maj, min_, patch, pr_type, pr_num, raw)

    @property
    def is_stable(self) -> bool:
        return self.prerelease_type == ""

    def get_channel(self) -> str:
        if self.prerelease_type in ("dev", "alpha"):
            return "dev"
        if self.prerelease_type in ("beta", "rc"):
            return "beta"
        return "stable"

    def _sort_key(self) -> Tuple[int, int, int, int, int]:
        rank = PRERELEASE_RANKS.get(self.prerelease_type, 0)
        return (self.major, self.minor, self.patch, rank, self.prerelease_num)

    def __lt__(self, other: "SemVer") -> bool:
        return self._sort_key() < other._sort_key()

    def __eq__(self, other: "SemVer") -> bool:
        return self._sort_key() == other._sort_key()

    def __gt__(self, other: "SemVer") -> bool:
        return self._sort_key() > other._sort_key()

    def __ge__(self, other: "SemVer") -> bool:
        return self._sort_key() >= other._sort_key()

    def __le__(self, other: "SemVer") -> bool:
        return self._sort_key() <= other._sort_key()

    def __str__(self) -> str:
        if self.raw:
            return self.raw
        pr = f"-{self.prerelease_type}.{self.prerelease_num}" if self.prerelease_type else ""
        return f"{self.major}.{self.minor}.{self.patch}{pr}"


class RelayUpdaterService:
    """Manages update checks, channel filtering, downloads, SHA-256 verification, and execution."""

    def __init__(self, repo: str = DEFAULT_GITHUB_REPO):
        self.repo = repo
        self._lock = threading.Lock()
        self._is_checking = False
        self._is_downloading = False
        self._download_progress: int = 0
        self._download_error: Optional[str] = None
        self._latest_release_info: Optional[Dict[str, Any]] = None
        self._downloaded_installer: Optional[str] = None
        self._downloaded_sha256: Optional[str] = None

    def get_updates_dir(self) -> str:
        updates_dir = os.path.join(get_user_data_dir(), "updates")
        os.makedirs(updates_dir, exist_ok=True)
        return updates_dir

    def get_status(self) -> Dict[str, Any]:
        """Returns the current state of the updater service."""
        from backend.device_identity import device_identity_manager
        identity = device_identity_manager.get_device_identity()
        with self._lock:
            return {
                "current_version": CURRENT_VERSION,
                "current_semver": str(SemVer.parse(CURRENT_VERSION)),
                "channel": identity.get("update_channel", "stable"),
                "device_role": identity.get("device_role", "standard"),
                "installation_id": identity.get("installation_id"),
                "is_frozen": is_frozen(),
                "is_checking": self._is_checking,
                "is_downloading": self._is_downloading,
                "download_progress": self._download_progress,
                "download_error": self._download_error,
                "downloaded_installer": self._downloaded_installer,
                "downloaded_sha256": self._downloaded_sha256,
                "latest_release": self._latest_release_info,
                "repo": self.repo,
            }

    def _get_auth_headers(self) -> Dict[str, str]:
        headers = {
            "User-Agent": f"Relay-Desktop-Updater/{CURRENT_VERSION} ({platform.system()})",
            "Accept": "application/vnd.github.v3+json",
        }
        gh_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not gh_token:
            try:
                import shutil
                if shutil.which("gh"):
                    res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=2)
                    if res.returncode == 0 and res.stdout.strip():
                        gh_token = res.stdout.strip()
            except Exception:
                pass
        if gh_token:
            headers["Authorization"] = f"Bearer {gh_token}"
        return headers

    def check_for_updates(self, channel: Optional[str] = None, timeout: float = 10.0) -> Dict[str, Any]:
        """
        Queries GitHub API for published releases, filters according to channel,
        and determines whether an eligible upgrade is available.
        """
        from backend.device_identity import device_identity_manager
        identity = device_identity_manager.get_device_identity()
        target_channel = (channel or identity.get("update_channel", "stable")).strip().lower()
        installation_id = identity.get("installation_id", "")

        with self._lock:
            self._is_checking = True
            self._download_error = None

        headers = self._get_auth_headers()
        releases: List[Dict[str, Any]] = []

        # 1. First attempt to fetch the list of releases to support channel filtering
        list_url = f"https://api.github.com/repos/{self.repo}/releases?per_page=15"
        try:
            req = urllib.request.Request(list_url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    raw_data = json.loads(response.read().decode("utf-8"))
                    releases = [raw_data] if isinstance(raw_data, dict) else raw_data
        except Exception as e:
            logger.debug(f"Failed to query releases list from {list_url}: {e}. Falling back to /releases/latest.")

        # 2. Fallback to /releases/latest if list failed or was empty
        if not releases:
            try:
                latest_url = f"https://api.github.com/repos/{self.repo}/releases/latest"
                req = urllib.request.Request(latest_url, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    if response.status == 200:
                        raw_data = json.loads(response.read().decode("utf-8"))
                        releases = [raw_data] if isinstance(raw_data, dict) else raw_data
            except Exception as e:
                msg = str(e)
                logger.warning(f"Failed to check updates from GitHub: {msg}")
                with self._lock:
                    self._is_checking = False
                    self._download_error = msg
                return {
                    "has_update": False,
                    "error": msg,
                    "current_version": CURRENT_VERSION,
                    "channel": target_channel,
                }

        # Filter releases by target channel
        eligible_releases = []
        curr_semver = SemVer.parse(CURRENT_VERSION)

        for rel in releases:
            if rel.get("draft", False):
                continue

            tag = rel.get("tag_name", "")
            parsed = SemVer.parse(tag)
            rel_channel = parsed.get_channel()

            # Channel gating
            if target_channel == "stable":
                if not (parsed.is_stable and not rel.get("prerelease", False)):
                    continue
            elif target_channel == "beta":
                if rel_channel not in ("stable", "beta"):
                    continue
            elif target_channel == "dev":
                # Dev channel receives all releases (stable, beta, dev)
                pass

            # Targeted rollout check: if release body or asset includes target_devices
            body = rel.get("body", "")
            target_match = re.search(r"<!--\s*target_devices:\s*(\[.*?\])\s*-->", body)
            if target_match:
                try:
                    targets = json.loads(target_match.group(1))
                    if isinstance(targets, list) and installation_id not in targets:
                        logger.info(f"Skipping targeted release {tag} (not targeted for this installation ID)")
                        continue
                except Exception:
                    pass

            # Ensure it has an installer executable (.exe)
            has_exe = any(
                asset.get("name", "").lower().endswith(".exe")
                for asset in rel.get("assets", [])
            )
            if has_exe:
                eligible_releases.append((parsed, rel))

        if not eligible_releases:
            summary = {
                "has_update": False,
                "current_version": CURRENT_VERSION,
                "channel": target_channel,
                "message": f"No eligible releases found for channel '{target_channel}'.",
            }
            with self._lock:
                self._latest_release_info = summary
                self._is_checking = False
            return summary

        # Sort eligible releases by semver descending
        eligible_releases.sort(key=lambda item: item[0], reverse=True)
        best_semver, best_release = eligible_releases[0]

        has_update = best_semver > curr_semver
        is_downgrade = best_semver < curr_semver

        # Find installer and checksum assets
        installer_asset = None
        checksums_asset = None
        for asset in best_release.get("assets", []):
            name = asset.get("name", "").lower()
            if name.endswith(".exe"):
                installer_asset = asset
            elif "sha256" in name or name.endswith(".txt"):
                checksums_asset = asset

        release_summary = {
            "tag_name": best_release.get("tag_name"),
            "name": best_release.get("name", best_release.get("tag_name")),
            "published_at": best_release.get("published_at"),
            "release_notes": best_release.get("body", ""),
            "has_update": has_update,
            "is_downgrade": is_downgrade,
            "channel": target_channel,
            "release_channel": best_semver.get_channel(),
            "installer_name": installer_asset.get("name") if installer_asset else None,
            "installer_url": installer_asset.get("browser_download_url") if installer_asset else None,
            "installer_size": installer_asset.get("size") if installer_asset else 0,
            "checksums_url": checksums_asset.get("browser_download_url") if checksums_asset else None,
            "html_url": best_release.get("html_url", f"https://github.com/{self.repo}/releases"),
            "current_version": CURRENT_VERSION,
        }

        with self._lock:
            self._latest_release_info = release_summary
            self._is_checking = False

        return release_summary

    def download_installer(self, download_url: Optional[str] = None) -> Tuple[bool, str]:
        """
        Downloads the latest installer executable to %LOCALAPPDATA%\\Relay\\updates\\.
        Streams with chunking, computes SHA-256, and verifies against checksums if available.
        """
        with self._lock:
            if self._is_downloading:
                return False, "Download already in progress."
            self._is_downloading = True
            self._download_progress = 0
            self._download_error = None
            self._downloaded_sha256 = None

        target_url = download_url
        checksums_url = None
        if self._latest_release_info:
            if not target_url:
                target_url = self._latest_release_info.get("installer_url")
            checksums_url = self._latest_release_info.get("checksums_url")

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
            headers = self._get_auth_headers()
            req = urllib.request.Request(target_url, headers=headers)

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

            calculated_sha256 = hasher.hexdigest().lower()

            # Verify checksum against SHA256SUMS.txt if available
            if checksums_url:
                try:
                    c_req = urllib.request.Request(checksums_url, headers=headers)
                    with urllib.request.urlopen(c_req, timeout=10) as c_resp:
                        c_text = c_resp.read().decode("utf-8")
                        # Format in SHA256SUMS.txt: <hash>  <filename>
                        expected_hash = None
                        for line in c_text.splitlines():
                            parts = line.strip().split()
                            if len(parts) >= 2:
                                h, fn = parts[0].lower(), parts[1].lower()
                                if fn.endswith(".exe") or "relay" in fn:
                                    expected_hash = h
                                    break
                        if expected_hash and expected_hash != calculated_sha256:
                            raise ValueError(
                                f"SHA-256 verification failed! Expected {expected_hash}, calculated {calculated_sha256}"
                            )
                        logger.info("SHA-256 verified successfully against release checksums manifest.")
                except Exception as ce:
                    if "SHA-256 verification failed" in str(ce):
                        raise
                    logger.warning(f"Could not verify SHA256SUMS.txt: {ce}")

            if os.path.exists(final_path):
                os.remove(final_path)
            os.rename(temp_path, final_path)

            logger.info(f"Downloaded installer to {final_path} (SHA-256: {calculated_sha256})")

            with self._lock:
                self._downloaded_installer = final_path
                self._downloaded_sha256 = calculated_sha256
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
        # Safety Check 1: In-memory active campaign worker
        from backend.job_queue import job_worker
        if job_worker.get_active_job():
            return (
                False,
                "Cannot install update while an active WhatsApp campaign is dispatching. Please pause or wait for completion."
            )

        # Safety Check 2: Durable SQLite database jobs (prevents upgrading with pending or paused campaigns)
        try:
            from backend.database import db
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, name, status FROM campaign_jobs WHERE status IN ('RUNNING', 'PAUSED', 'RECONCILIATION_REQUIRED', 'QUEUED')"
                )
                active_db_jobs = cursor.fetchall()
                if active_db_jobs:
                    job_desc = f"ID: {active_db_jobs[0][0]}, Status: {active_db_jobs[0][2]}"
                    return (
                        False,
                        f"Cannot install update: found {len(active_db_jobs)} active, paused, or queued campaign(s) in database ({job_desc}). Please complete or cancel before updating."
                    )
        except Exception as e:
            logger.warning(f"Could not inspect campaign jobs in database: {e}")

        with self._lock:
            installer_path = self._downloaded_installer

        if not installer_path or not os.path.isfile(installer_path):
            return False, "No verified installer found. Please download update first."

        cmd = [installer_path]
        if silent:
            cmd.extend(["/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"])

        logger.info(f"Spawning update installer: {' '.join(cmd)}")

        try:
            subprocess.Popen(
                cmd,
                creationflags=subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0,
                close_fds=True
            )

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
