"""
Unit tests for validator.py (pre-flight audit, deduplication, dry-run simulation).
"""

import pytest
from validator import PreFlightValidator, DryRunEngine, ValidationReport
from config_manager import AppConfig


def test_audit_clean_contacts():
    contacts = [
        {"phone": "919876543210", "name": "Alice", "message": "Hello Alice"},
        {"phone": "919876543211", "name": "Bob", "message": "Hello Bob"},
    ]
    cfg = AppConfig()
    report = PreFlightValidator.audit_contacts(contacts, cfg)

    assert report.total_contacts == 2
    assert report.valid_contacts == 2
    assert report.duplicate_count == 0
    assert report.invalid_phone_count == 0
    assert report.is_ready_to_send is True
    assert report.estimated_duration_minutes > 0


def test_audit_duplicate_contacts():
    contacts = [
        {"phone": "919876543210", "name": "Alice", "message": "Hello Alice"},
        {"phone": "919876543210", "name": "Alice Duplicate", "message": "Hello Alice"},
        {"phone": "919876543212", "name": "Charlie", "message": "Hello Charlie"},
    ]
    cfg = AppConfig()
    report = PreFlightValidator.audit_contacts(contacts, cfg)

    assert report.total_contacts == 3
    assert report.valid_contacts == 3
    assert report.duplicate_count == 1
    assert len(report.duplicates) == 1
    assert report.duplicates[0]["phone"] == "919876543210"
    assert any("duplicate" in r.lower() for r in report.recommendations)


def test_audit_invalid_phone():
    contacts = [
        {"phone": "12345", "name": "Invalid Short", "message": "Hello"},
        {"phone": "abcdef", "name": "Non Digit", "message": "Hello"},
        {"phone": "919876543210", "name": "Valid", "message": "Hello"},
    ]
    cfg = AppConfig()
    report = PreFlightValidator.audit_contacts(contacts, cfg)

    assert report.invalid_phone_count == 2
    assert report.valid_contacts == 1


def test_deduplicate_contacts():
    contacts = [
        {"phone": "919876543210", "name": "First"},
        {"phone": "919876543211", "name": "Second"},
        {"phone": "919876543210", "name": "First Duplicate"},
        {"phone": "919876543212", "name": "Third"},
    ]
    deduped, removed = PreFlightValidator.deduplicate_contacts(contacts)

    assert removed == 1
    assert len(deduped) == 3
    assert [c["name"] for c in deduped] == ["First", "Second", "Third"]


def test_dry_run_simulation():
    contacts = [
        {"phone": "919876543210", "name": "Alice", "message": "{Hi|Hello} Alice!"},
        {"phone": "919876543211", "name": "Bob", "message": "{Hi|Hello} Bob!"},
    ]
    cfg = AppConfig()
    simulation = DryRunEngine.simulate_campaign(contacts, cfg, sample_size=2)

    assert simulation["is_ready"] is True
    assert simulation["total_recipients"] == 2
    assert len(simulation["sample_messages"]) == 2
    sample0 = simulation["sample_messages"][0]
    assert sample0["name"] == "Alice"
    assert "Alice!" in sample0["simulated_message"]
    assert "919876" in sample0["phone_masked"]

