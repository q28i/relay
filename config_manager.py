"""
Configuration Manager for WhatsApp Bulk Messenger Pro.
Provides centralized, validated, and backward-compatible configuration management.
Supports typed schema, validation bounds, named safety presets, schema versioning,
and profile export/import.
"""

import os
import re
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple

from logger import get_logger

logger = get_logger("ConfigManager")

DEFAULT_CONFIG_FILE = "config.json"
CURRENT_SCHEMA_VERSION = 1

# Built-in Anti-Ban Safety Presets
BUILTIN_PRESETS: Dict[str, Dict[str, Any]] = {
    "safe": {
        "name": "🛡️ Safe Warm-up",
        "description": "Ideal for brand new or cold SIM cards. Extra-slow pacing.",
        "min_delay": 12.0,
        "max_delay": 20.0,
        "batch_size": 15,
        "batch_pause": 90.0,
        "daily_cap": 30
    },
    "balanced": {
        "name": "⚖️ Balanced",
        "description": "Standard recommended setting for everyday established accounts.",
        "min_delay": 8.0,
        "max_delay": 15.0,
        "batch_size": 20,
        "batch_pause": 60.0,
        "daily_cap": 100
    },
    "fast": {
        "name": "⚡ Fast",
        "description": "Higher velocity for opted-in customer transactional alerts.",
        "min_delay": 4.0,
        "max_delay": 8.0,
        "batch_size": 30,
        "batch_pause": 30.0,
        "daily_cap": 200
    }
}


@dataclass
class AppConfig:
    """Typed application configuration schema with sensible default values."""
    browser: str = "chrome"
    profile_index: int = 0
    profile_dir: str = "__dedicated__"
    profile_name: str = "Dedicated WhatsApp Session"
    connection_status: str = "Not checked"
    data_file: str = "contacts_sample.xlsx"
    default_country_code: str = ""
    default_message: str = "Hello {name}, thank you for connecting with us! Here is your update."
    min_delay: float = 8.0
    max_delay: float = 15.0
    batch_size: int = 20
    batch_pause: float = 60.0
    daily_cap: int = 100
    attach_enabled: bool = False
    attachment_path: str = ""
    headless: bool = False
    sched_enabled: bool = False
    sched_time: str = "09:30"
    dev_mode: bool = False
    active_preset: str = "balanced"
    schema_version: int = CURRENT_SCHEMA_VERSION
    custom_presets: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def apply_preset(self, preset_key: str) -> bool:
        """Applies values from a built-in or custom preset."""
        preset = BUILTIN_PRESETS.get(preset_key) or self.custom_presets.get(preset_key)
        if not preset:
            return False
        if "min_delay" in preset:
            self.min_delay = float(preset["min_delay"])
        if "max_delay" in preset:
            self.max_delay = float(preset["max_delay"])
        if "batch_size" in preset:
            self.batch_size = int(preset["batch_size"])
        if "batch_pause" in preset:
            self.batch_pause = float(preset["batch_pause"])
        if "daily_cap" in preset:
            self.daily_cap = int(preset["daily_cap"])
        self.active_preset = preset_key
        return True

    def validate(self) -> Tuple[bool, List[str]]:
        """
        Validates configuration boundaries and logical consistency.
        Returns: (is_valid, list_of_errors_or_warnings)
        """
        issues = []

        if self.browser not in ("chrome", "edge", "brave", "firefox"):
            issues.append(f"Invalid browser '{self.browser}'. Must be 'chrome', 'edge', 'brave', or 'firefox'.")

        if self.min_delay < 1.0:
            issues.append(f"Min delay ({self.min_delay}s) is too aggressive (< 1.0s) and risks immediate ban.")

        if self.max_delay < self.min_delay:
            issues.append(f"Max delay ({self.max_delay}s) cannot be less than Min delay ({self.min_delay}s).")

        if self.batch_size < 1:
            issues.append("Batch size must be at least 1 message.")

        if self.batch_pause < 5.0:
            issues.append(f"Batch pause ({self.batch_pause}s) is too short (< 5.0s).")

        if self.daily_cap < 1:
            issues.append("Daily cap must be at least 1 message.")

        # Validate schedule time format HH:MM
        if self.sched_enabled or self.sched_time:
            time_match = re.match(r"^([01]?\d|2[0-3]):([0-5]\d)$", self.sched_time.strip())
            if not time_match:
                issues.append(f"Invalid schedule time '{self.sched_time}'. Expected 24-hr format HH:MM (e.g. 09:30).")

        # Attachment check if enabled
        if self.attach_enabled and self.attachment_path:
            if not os.path.isfile(self.attachment_path):
                issues.append(f"Configured attachment file not found: {self.attachment_path}")

        return (len(issues) == 0, issues)

    def to_dict(self) -> Dict[str, Any]:
        """Converts config instance to a clean dictionary compatible with legacy config.json."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        """Instantiates an AppConfig from dictionary with schema defaults and type coercion."""
        known_fields = cls.__dataclass_fields__.keys()
        filtered = {}
        for k, v in data.items():
            if k in known_fields:
                filtered[k] = v

        # Type coercions
        if "min_delay" in filtered:
            try:
                filtered["min_delay"] = float(filtered["min_delay"])
            except (ValueError, TypeError):
                filtered["min_delay"] = 8.0

        if "max_delay" in filtered:
            try:
                filtered["max_delay"] = float(filtered["max_delay"])
            except (ValueError, TypeError):
                filtered["max_delay"] = 15.0

        if "batch_size" in filtered:
            try:
                filtered["batch_size"] = int(filtered["batch_size"])
            except (ValueError, TypeError):
                filtered["batch_size"] = 20

        if "batch_pause" in filtered:
            try:
                filtered["batch_pause"] = float(filtered["batch_pause"])
            except (ValueError, TypeError):
                filtered["batch_pause"] = 60.0

        if "daily_cap" in filtered:
            try:
                filtered["daily_cap"] = int(filtered["daily_cap"])
            except (ValueError, TypeError):
                filtered["daily_cap"] = 100

        return cls(**filtered)


class ConfigManager:
    """Manages persistent reading, writing, and profile export of AppConfig."""

    @staticmethod
    def get_default_path() -> str:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, DEFAULT_CONFIG_FILE)

    @classmethod
    def load(cls, file_path: Optional[str] = None) -> AppConfig:
        """Loads configuration from file or returns safe defaults."""
        path = file_path or cls.get_default_path()
        if not os.path.isfile(path):
            logger.info(f"No configuration file found at {path}. Initializing default config.")
            return AppConfig()

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            config = AppConfig.from_dict(data)
            is_valid, issues = config.validate()
            if not is_valid:
                for issue in issues:
                    logger.warning(f"Config validation warning: {issue}")
            return config
        except Exception as e:
            logger.error(f"Error loading configuration from {path}: {e}. Falling back to default settings.")
            return AppConfig()

    @classmethod
    def save(cls, config: AppConfig, file_path: Optional[str] = None) -> bool:
        """Saves configuration to JSON file with schema formatting."""
        path = file_path or cls.get_default_path()
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(config.to_dict(), f, indent=4)
            logger.info(f"Configuration successfully saved to {os.path.basename(path)}")
            return True
        except Exception as e:
            logger.error(f"Failed to save configuration to {path}: {e}")
            return False

    @classmethod
    def get_config(cls, file_path: Optional[str] = None) -> AppConfig:
        return cls.load(file_path=file_path)

    @classmethod
    def save_config(cls, config: AppConfig, file_path: Optional[str] = None) -> bool:
        return cls.save(config, file_path=file_path)

    @classmethod
    def export_profile(cls, config: AppConfig, target_path: str) -> bool:
        """Exports named configuration profile to an external JSON file."""
        return cls.save(config, file_path=target_path)

    @classmethod
    def import_profile(cls, source_path: str) -> Optional[AppConfig]:
        """Imports named configuration profile from an external JSON file."""
        if not os.path.isfile(source_path):
            logger.error(f"Import profile source file not found: {source_path}")
            return None
        return cls.load(file_path=source_path)

