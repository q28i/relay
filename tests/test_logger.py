"""
Unit tests for logger.py (structured logging and phone masking).
"""

import logging
from logger import get_logger, mask_phone


def test_mask_phone_standard():
    assert mask_phone("919876543210") == "919876****10"
    assert mask_phone("+14155552671") == "+14155****71"


def test_mask_phone_short():
    assert mask_phone("12345") == "*****"
    assert mask_phone("") == ""
    assert mask_phone(None) == ""


def test_get_logger_singleton():
    l1 = get_logger("TestLogger")
    l2 = get_logger("TestLogger")
    assert l1 is l2
    assert isinstance(l1, logging.Logger)

