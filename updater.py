"""
WhatsApp Bulk Messenger Pro - Auto-Updater & Developer Release System
Supports automatic update checking and downloading from GitHub or Cloudflare endpoints.
Also includes a 1-click Release Packager for authorized Developers.
"""

import os
import sys
import json
import shutil
import zipfile
import hashlib
import platform
import urllib.request
import urllib.error
import datetime
from typing import Tuple, Dict, Any, Optional

from device_manager import DeviceManager

CURRENT_VERSION = "1.2.0"
CONFIG_FILE = "update_config.json"
VERSION_FILE = "version.json"
BACKUP_DIR = ".update_backup"
DIST_DIR = "dist"

# Files and directories to protect from being overwritten during updates
PROTECTED_PATHS = {
    "whatsapp_browser_session",
    "device_audit.log",
    "auth_config.json",
    "config.json",
    "update_config.json",
    ".update_backup",
    "dist"
}


class Updater:
    @staticmethod
    def get_base_dir() -> str:
        return os.path.dirname(os.path.abspath(__file__))

    @classmethod
    def load_update_config(cls) -> dict:
        base_dir = cls.get_base_dir()
        cfg_path = os.path.join(base_dir, CONFIG_FILE)
        defaults = {
            "provider": "github",
            "github_repo": "ainttyug/whatsapp-bulk-messenger",
            "branch": "main",
            "custom_endpoint": "",
            "auto_check_on_startup": True
        }
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    defaults.update(data)
            except Exception:
                pass
        return defaults

    @classmethod
    def save_update_config(cls, cfg: dict):
        base_dir = cls.get_base_dir()
        cfg_path = os.path.join(base_dir, CONFIG_FILE)
        try:
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)
        except Exception as e:
            print(f"[WARNING] Could not save update config: {e}")

    @classmethod
    def get_current_version(cls) -> str:
        base_dir = cls.get_base_dir()
        v_path = os.path.join(base_dir, VERSION_FILE)
        if os.path.isfile(v_path):
            try:
                with open(v_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("version", CURRENT_VERSION)
            except Exception:
                pass
        return CURRENT_VERSION

    @classmethod
    def get_manifest_url(cls) -> str:
        cfg = cls.load_update_config()
        if cfg.get("custom_endpoint"):
            return cfg["custom_endpoint"].rstrip("/") + "/version.json"
        
        repo = cfg.get("github_repo", "ainttyug/whatsapp-bulk-messenger").strip()
        branch = cfg.get("branch", "main").strip()
        return f"https://raw.githubusercontent.com/{repo}/{branch}/version.json"

    @classmethod
    def parse_semver(cls, version_str: str) -> Tuple[int, ...]:
        clean = version_str.strip().lstrip("vV")
        parts = []
        for p in clean.split("."):
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(0)
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])

    @classmethod
    def check_for_updates(cls, timeout: int = 8) -> Tuple[bool, Dict[str, Any], str]:
        """
        Queries the remote repository/manifest for latest version.
        Returns: (has_update, manifest_dict, status_message)
        """
        url = cls.get_manifest_url()
        current_v = cls.get_current_version()
        curr_tuple = cls.parse_semver(current_v)

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": f"WhatsApp-Bulk-Messenger/{current_v} ({platform.system()})",
                "Cache-Control": "no-cache"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status != 200:
                    return False, {}, f"Server returned HTTP {response.status}"
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return False, {}, f"HTTP Error {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            return False, {}, f"Network connection error: {e.reason}"
        except Exception as e:
            return False, {}, f"Update check failed: {e}"

        remote_v = data.get("version", "0.0.0")
        remote_tuple = cls.parse_semver(remote_v)

        if remote_tuple > curr_tuple:
            return True, data, f"Update available: v{remote_v} (Current: v{current_v})"
        else:
            return False, data, f"You are up to date (v{current_v})"

    @classmethod
    def download_and_apply_update(cls, download_url: str, progress_callback=None) -> Tuple[bool, str]:
        """
        Downloads the update package (.zip) and extracts safe files over current installation.
        Preserves user configuration, WhatsApp sessions, and spreadsheets.
        """
        base_dir = cls.get_base_dir()
        temp_zip = os.path.join(base_dir, "_temp_update.zip")
        backup_path = os.path.join(base_dir, BACKUP_DIR)

        try:
            if progress_callback:
                progress_callback("Connecting to download server...")

            req = urllib.request.Request(
                download_url,
                headers={"User-Agent": "WhatsApp-Bulk-Messenger-Updater"}
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0
                chunk_size = 64 * 1024

                with open(temp_zip, "wb") as f_out:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f_out.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0 and progress_callback:
                            pct = int((downloaded / total_size) * 100)
                            progress_callback(f"Downloading update: {pct}% ({downloaded // 1024} KB)")

            if not zipfile.is_zipfile(temp_zip):
                if os.path.isfile(temp_zip):
                    os.remove(temp_zip)
                return False, "Downloaded file is not a valid zip archive."

            if progress_callback:
                progress_callback("Backing up current installation...")

            # Backup critical python files before overwrite
            os.makedirs(backup_path, exist_ok=True)
            for f_name in os.listdir(base_dir):
                if f_name.endswith(".py") or f_name in ("run.bat", "requirements.txt", "version.json"):
                    src = os.path.join(base_dir, f_name)
                    dst = os.path.join(backup_path, f_name)
                    shutil.copy2(src, dst)

            if progress_callback:
                progress_callback("Applying updates...")

            with zipfile.ZipFile(temp_zip, "r") as zf:
                # Find root directory if GitHub zip contains a nested folder (e.g. repo-main/)
                namelist = zf.namelist()
                prefix = ""
                if "/" in namelist[0]:
                    possible_prefix = namelist[0].split("/")[0] + "/"
                    if all(n.startswith(possible_prefix) for n in namelist if n != possible_prefix):
                        prefix = possible_prefix

                for member in namelist:
                    rel_name = member[len(prefix):] if prefix and member.startswith(prefix) else member
                    rel_name = rel_name.strip("/")
                    if not rel_name:
                        continue

                    # Skip protected user files and directories
                    top_part = rel_name.split("/")[0]
                    if top_part in PROTECTED_PATHS:
                        continue
                    if rel_name.endswith(".xlsx") or rel_name.endswith(".csv"):
                        # Don't overwrite existing user contacts
                        dest_check = os.path.join(base_dir, rel_name)
                        if os.path.exists(dest_check):
                            continue

                    dest_file = os.path.join(base_dir, rel_name)
                    if member.endswith("/"):
                        os.makedirs(dest_file, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                        with zf.open(member) as src_file, open(dest_file, "wb") as dst_file:
                            shutil.copyfileobj(src_file, dst_file)

            if os.path.isfile(temp_zip):
                os.remove(temp_zip)

            if progress_callback:
                progress_callback("Update successfully applied!")

            return True, "Update applied successfully! Please restart the application."

        except Exception as e:
            if os.path.isfile(temp_zip):
                try:
                    os.remove(temp_zip)
                except Exception:
                    pass
            return False, f"Failed to apply update: {e}"

    # =========================================================================
    # DEVELOPER RELEASE PACKAGER
    # =========================================================================
    @classmethod
    def package_release(cls, new_version: str, changelog: list, download_url: str = "") -> Tuple[bool, dict, str]:
        """
        Builds a sanitized production zip package and updates version.json.
        Only authorized developer devices can produce signed release packages.
        """
        if not DeviceManager.is_developer():
            return False, {}, "Unauthorized device! Only whitelisted developer devices can package releases."

        base_dir = cls.get_base_dir()
        dist_dir = os.path.join(base_dir, DIST_DIR)
        os.makedirs(dist_dir, exist_ok=True)

        zip_name = f"whatsapp-bulk-messenger-v{new_version}.zip"
        zip_path = os.path.join(dist_dir, zip_name)

        # Update local version.json first
        cfg = cls.load_update_config()
        repo = cfg.get("github_repo", "ainttyug/whatsapp-bulk-messenger")
        if not download_url:
            download_url = f"https://github.com/{repo}/releases/download/v{new_version}/{zip_name}"

        manifest_data = {
            "version": new_version,
            "release_date": datetime.date.today().isoformat(),
            "min_python_version": "3.8",
            "developer_device": DeviceManager.get_device_info()["short_id"],
            "changelog": changelog if changelog else ["Maintenance and stability improvements."],
            "download_url": download_url,
            "asset_name": zip_name,
            "sha256": ""
        }

        # Essential files to include in release
        files_to_pack = [
            "browser_manager.py",
            "data_loader.py",
            "whatsapp_engine.py",
            "excel_editor.py",
            "device_manager.py",
            "updater.py",
            "gui.py",
            "run.py",
            "run.bat",
            "requirements.txt",
            "DOCUMENTATION.md",
            "README.md",
            "contacts_sample.xlsx",
            "contacts_sample.csv"
        ]

        # Write clean version.json into base dir
        v_path = os.path.join(base_dir, VERSION_FILE)
        with open(v_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=4)

        if "version.json" not in files_to_pack:
            files_to_pack.append("version.json")

        # Create production zip
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname in files_to_pack:
                fpath = os.path.join(base_dir, fname)
                if os.path.isfile(fpath):
                    zf.write(fpath, arcname=fname)

        # Compute SHA256 of package
        hasher = hashlib.sha256()
        with open(zip_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        pkg_sha = hasher.hexdigest()

        # Update manifest with final sha256
        manifest_data["sha256"] = pkg_sha
        with open(v_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=4)

        # Also write version.json into dist folder for easy upload to GitHub/Cloudflare
        dist_manifest = os.path.join(dist_dir, VERSION_FILE)
        with open(dist_manifest, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=4)

        size_kb = os.path.getsize(zip_path) // 1024
        msg = (
            f"Release v{new_version} packaged successfully!\n\n"
            f"Package: {zip_name} ({size_kb} KB)\n"
            f"SHA-256: {pkg_sha[:16]}...\n"
            f"Location: {zip_path}\n"
            f"Manifest: {dist_manifest}\n\n"
            f"To ship update:\n"
            f"1. Push {VERSION_FILE} to your GitHub repo main branch.\n"
            f"2. Create a GitHub Release 'v{new_version}' and attach '{zip_name}'."
        )
        return True, manifest_data, msg


if __name__ == "__main__":
    print("=== WhatsApp Bulk Messenger Pro Updater ===")
    print(f"Current Version : v{Updater.get_current_version()}")
    print(f"Manifest URL    : {Updater.get_manifest_url()}")
    print(f"Is Developer    : {DeviceManager.is_developer()}")

    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        print("Checking for updates...")
        has_up, manifest, msg = Updater.check_for_updates()
        print(f"Result: {msg}")
        if has_up:
            print(f"Changelog: {manifest.get('changelog')}")
            print(f"Download : {manifest.get('download_url')}")
    elif len(sys.argv) > 1 and sys.argv[1] == "--pack":
        ver = sys.argv[2] if len(sys.argv) > 2 else "1.2.1"
        print(f"Packaging release v{ver}...")
        ok, m_data, msg = Updater.package_release(ver, ["Automated production update release."])
        print(msg)

