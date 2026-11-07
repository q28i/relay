"""
Root proxy for Relay Runtime Path Resolution & Storage Isolation Manager.
Re-exports backend.paths.
"""

from backend.paths import (
    is_frozen,
    get_bundle_dir,
    get_user_data_dir,
    get_db_path,
    get_media_dir,
    get_session_dir,
    get_config_path,
    get_static_dir,
    get_logs_dir,
    ensure_data_dirs,
    migrate_legacy_data_if_needed,
)

__all__ = [
    "is_frozen",
    "get_bundle_dir",
    "get_user_data_dir",
    "get_db_path",
    "get_media_dir",
    "get_session_dir",
    "get_config_path",
    "get_static_dir",
    "get_logs_dir",
    "ensure_data_dirs",
    "migrate_legacy_data_if_needed",
]
