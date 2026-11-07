"""
Relay Runtime Path Resolution & Storage Isolation Manager.

Maintains strict separation between:
1. Application Code / Executable Bundle (read-only):
   - In dev: Repository root
   - When frozen: sys._MEIPASS / executable directory
2. Persistent User Data (read-write, never wiped on updates):
   - In dev: Repository root (for backwards compatibility with existing tests and scripts)
   - When frozen / packaged: %LOCALAPPDATA%\\Relay
   - Can be overridden anytime via RELAY_USER_DATA_DIR environment variable
"""

import os
import sys
import shutil
import logging
from typing import Optional

logger = logging.getLogger("RelayPaths")


def is_frozen() -> bool:
    """Returns True if the application is running inside a PyInstaller or Nuitka frozen package."""
    return getattr(sys, "frozen", False)


def get_bundle_dir() -> str:
    """
    Returns the root directory of the application bundle.
    In frozen mode: PyInstaller extraction directory (_MEIPASS) or executable folder.
    In development mode: Repository root directory.
    """
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    # In normal Python execution, backend is a subdirectory of the project root
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    return parent_dir


def get_user_data_dir() -> str:
    """
    Returns the persistent user data directory.
    Priority:
    1. RELAY_USER_DATA_DIR environment variable (if explicitly set)
    2. When frozen (packaged desktop app): %LOCALAPPDATA%\\Relay
    3. In development / testing: Repository root directory (preserves 100% test compatibility)
    """
    env_dir = os.environ.get("RELAY_USER_DATA_DIR")
    if env_dir:
        return os.path.abspath(env_dir)

    if is_frozen():
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            local_app_data = os.path.join(os.path.expanduser("~"), "AppData", "Local")
        return os.path.join(local_app_data, "Relay")

    # In development mode, use repository root
    return get_bundle_dir()


def get_db_path() -> str:
    """Returns the absolute path to the SQLite database (whatsapp_web.db)."""
    env_db = os.environ.get("RELAY_DB_PATH")
    if env_db:
        return os.path.abspath(env_db)
    return os.path.join(get_user_data_dir(), "whatsapp_web.db")


def get_media_dir() -> str:
    """Returns the absolute path to user uploaded media files."""
    env_media = os.environ.get("RELAY_MEDIA_DIR")
    if env_media:
        return os.path.abspath(env_media)
    return os.path.join(get_user_data_dir(), "uploads", "media")


def get_session_dir() -> str:
    """Returns the absolute path to the persistent WhatsApp browser session profile."""
    env_session = os.environ.get("RELAY_SESSION_DIR")
    if env_session:
        return os.path.abspath(env_session)
    return os.path.join(get_user_data_dir(), "whatsapp_browser_session")


def get_config_path() -> str:
    """Returns the absolute path to config.json."""
    env_config = os.environ.get("RELAY_CONFIG_PATH")
    if env_config:
        return os.path.abspath(env_config)
    return os.path.join(get_user_data_dir(), "config.json")


def get_static_dir() -> str:
    """Returns the absolute path to frontend static web assets."""
    return os.path.join(get_bundle_dir(), "backend", "static")


def get_logs_dir() -> str:
    """Returns the absolute path to application logs."""
    return os.path.join(get_user_data_dir(), "logs")


def ensure_data_dirs() -> None:
    """Ensures all persistent user directories exist with correct permissions."""
    os.makedirs(get_user_data_dir(), exist_ok=True)
    os.makedirs(get_media_dir(), exist_ok=True)
    os.makedirs(get_session_dir(), exist_ok=True)
    os.makedirs(get_logs_dir(), exist_ok=True)


def migrate_legacy_data_if_needed(legacy_source_dir: Optional[str] = None) -> None:
    """
    One-time safe migration helper:
    If running with an isolated user data directory and no database exists yet,
    checks if a legacy database or browser session exists in a previous installation
    or specified source directory, and copies them safely without overwriting.
    """
    target_data_dir = get_user_data_dir()
    ensure_data_dirs()

    if not legacy_source_dir:
        # Check adjacent or bundle directory
        legacy_source_dir = get_bundle_dir()

    if os.path.abspath(target_data_dir) == os.path.abspath(legacy_source_dir):
        return  # Same directory, no migration needed

    # Migrate database if target doesn't exist
    target_db = os.path.join(target_data_dir, "whatsapp_web.db")
    source_db = os.path.join(legacy_source_dir, "whatsapp_web.db")
    if not os.path.exists(target_db) and os.path.exists(source_db):
        try:
            logger.info("Migrating legacy database from %s to %s", source_db, target_db)
            shutil.copy2(source_db, target_db)
        except Exception as e:
            logger.warning("Failed to migrate database: %s", e)

    # Migrate config if target doesn't exist
    target_cfg = os.path.join(target_data_dir, "config.json")
    source_cfg = os.path.join(legacy_source_dir, "config.json")
    if not os.path.exists(target_cfg) and os.path.exists(source_cfg):
        try:
            logger.info("Migrating legacy config from %s to %s", source_cfg, target_cfg)
            shutil.copy2(source_cfg, target_cfg)
        except Exception as e:
            logger.warning("Failed to migrate config: %s", e)

    # Migrate browser session if source exists
    target_session = os.path.join(target_data_dir, "whatsapp_browser_session")
    source_session = os.path.join(legacy_source_dir, "whatsapp_browser_session")
    if os.path.exists(source_session):
        try:
            logger.info("Migrating legacy session from %s to %s", source_session, target_session)
            shutil.copytree(source_session, target_session, dirs_exist_ok=True)
        except Exception as e:
            logger.warning("Failed to migrate browser session: %s", e)
