"""
Unit tests for interruptible sleep in whatsapp_engine.py.
"""

import time
import pytest
from whatsapp_engine import WhatsAppEngine


class DummyDriver:
    pass


def test_interruptible_sleep_normal():
    engine = WhatsAppEngine(DummyDriver())
    t0 = time.time()
    ok = engine._interruptible_sleep(duration=0.2, step=0.05)
    t1 = time.time()
    assert ok is True
    assert (t1 - t0) >= 0.18


def test_interruptible_sleep_stopped():
    engine = WhatsAppEngine(DummyDriver())
    engine.stop()
    t0 = time.time()
    # If stopped, it should return False immediately without sleeping for 10s
    ok = engine._interruptible_sleep(duration=10.0, step=0.05)
    t1 = time.time()
    assert ok is False
    assert (t1 - t0) < 0.2

