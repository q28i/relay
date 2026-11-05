"""
Unit tests for Spintax parsing in whatsapp_engine.py
"""

import pytest
from whatsapp_engine import process_spintax


def test_spintax_basic_options():
    options = {"Hi", "Hello", "Hey"}
    results = set()
    template = "{Hi|Hello|Hey} there!"
    for _ in range(50):
        out = process_spintax(template)
        word = out.split()[0]
        assert word in options
        results.add(word)
    # With 50 iterations and 3 choices, all 3 choices should be hit
    assert results == options


def test_spintax_nested():
    template = "{Hi|{Hello|Hey}} friend"
    valid = {"Hi friend", "Hello friend", "Hey friend"}
    for _ in range(30):
        out = process_spintax(template)
        assert out in valid


def test_spintax_preserves_template_tokens():
    template = "{Hello|Hi} {name}, your order #{order_id} is ready!"
    for _ in range(20):
        out = process_spintax(template)
        assert "{name}" in out
        assert "{order_id}" in out
        assert out.startswith("Hello ") or out.startswith("Hi ")


def test_spintax_no_spintax():
    plain = "This is a plain message with no variations."
    assert process_spintax(plain) == plain


def test_spintax_empty():
    assert process_spintax("") == ""


def test_spintax_multiple_blocks():
    template = "{Hi|Hello} {name}, {thanks|thank you} for reaching out!"
    for _ in range(20):
        out = process_spintax(template)
        assert out.startswith("Hi ") or out.startswith("Hello ")
        assert "thanks for" in out or "thank you for" in out

