"""
Structured Logging Subsystem for WhatsApp Bulk Messenger Pro.
Provides rotating file logging, formatted console output, and sensitive data masking
(e.g. masking customer phone numbers in logs to protect privacy).
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

DEFAULT_LOG_FILE = "whatsapp_automation.log"
DEFAULT_MAX_BYTES = 2 * 1024 * 1024  # 2 MB per log file
DEFAULT_BACKUP_COUNT = 3


def mask_phone(phone: Optional[str]) -> str:
    """
    Masks middle digits of a phone number for privacy preservation in logs.
    Example: '919876543210' -> '919876****10'.
    """
    if not phone:
        return ""
    clean = str(phone).strip()
    length = len(clean)
    if length <= 5:
        return "*" * length
    if length <= 8:
        return clean[:2] + "****" + clean[-2:]
    # For standard international numbers (10-15 digits): keep first 6 and last 2
    prefix_len = min(6, length - 4)
    suffix_len = 2
    masked_count = length - prefix_len - suffix_len
    return clean[:prefix_len] + ("*" * max(masked_count, 3)) + clean[-suffix_len:]


def get_logger(name: str = "WhatsAppBulkMessenger", level: int = logging.INFO) -> logging.Logger:
    """
    Returns a configured Logger instance with console and rotating file handlers.
    Avoids duplicate handlers if called multiple times with the same name.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Console Handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. Rotating File Handler
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        log_path = os.path.join(base_dir, DEFAULT_LOG_FILE)
        file_handler = RotatingFileHandler(
            filename=log_path,
            maxBytes=DEFAULT_MAX_BYTES,
            backupCount=DEFAULT_BACKUP_COUNT,
            encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        # If filesystem access is restricted, console logging remains active
        pass

    return logger

