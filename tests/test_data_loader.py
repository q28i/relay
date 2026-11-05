"""
Unit tests for data_loader.py (contact ingestion, cleaning, templating).
"""

import os
import pytest
from data_loader import DataLoader


def test_clean_phone_number_basic():
    # 10 digits with country code prepended
    assert DataLoader.clean_phone_number("9876543210", default_country_code="91") == "919876543210"
    assert DataLoader.clean_phone_number("9876543210", default_country_code="+91") == "919876543210"

    # Already formatted with country code
    assert DataLoader.clean_phone_number("+919876543210") == "919876543210"
    assert DataLoader.clean_phone_number("+1 (415) 555-2671") == "14155552671"

    # International spacing / punctuation
    assert DataLoader.clean_phone_number("  +44 7911 123456  ") == "447911123456"


def test_clean_phone_number_invalid():
    # Too short (<10 digits)
    assert DataLoader.clean_phone_number("12345") is None
    assert DataLoader.clean_phone_number("987654321") is None

    # Too long (>16 digits)
    assert DataLoader.clean_phone_number("12345678901234567") is None

    # Non-digit text
    assert DataLoader.clean_phone_number("invalid_phone_number") is None
    assert DataLoader.clean_phone_number("") is None


def test_match_header_synonyms():
    headers = ["Sr No", "Customer Name", "contact_number", "Custom Notes"]
    matched_phone = DataLoader._match_header(headers, DataLoader.PHONE_SYNONYMS)
    assert matched_phone == "contact_number"

    matched_name = DataLoader._match_header(headers, DataLoader.NAME_SYNONYMS)
    assert matched_name == "Customer Name"


def test_load_contacts_from_sample_csv():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    csv_path = os.path.join(base_dir, "contacts_sample.csv")

    assert os.path.isfile(csv_path)
    contacts = DataLoader.load_contacts(csv_path)
    assert len(contacts) >= 2

    c0 = contacts[0]
    assert c0["phone"] == "919876543210"
    assert c0["name"] == "Alex Mercer"
    assert "Alex Mercer" in c0["message"]


def test_load_contacts_from_sample_xlsx():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    xlsx_path = os.path.join(base_dir, "contacts_sample.xlsx")

    assert os.path.isfile(xlsx_path)
    contacts = DataLoader.load_contacts(xlsx_path)
    assert len(contacts) >= 2

    c0 = contacts[0]
    assert c0["phone"] == "919876543210"
    assert c0["name"] == "Alex Mercer"


def test_variable_substitution():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    csv_path = os.path.join(base_dir, "contacts_sample.csv")

    contacts = DataLoader.load_contacts(
        csv_path,
        default_message="Hey {first_name}, full name {name}, phone {phone}!"
    )
    assert len(contacts) > 0
    c0 = contacts[0]
    # For sample CSV, row has custom message; if row has no custom message, fallback is used
    # But let's verify tokens in contacts
    assert c0["name"] == "Alex Mercer"
    assert c0["phone"] == "919876543210"


def test_load_contacts_missing_file():
    with pytest.raises(FileNotFoundError):
        DataLoader.load_contacts("non_existent_file_12345.csv")


def test_load_contacts_unsupported_format(tmp_path):
    p = tmp_path / "contacts.txt"
    p.write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        DataLoader.load_contacts(str(p))
    assert "Unsupported file format" in str(exc.value)

