"""
Tests for Stage 1: Contact Normalization, Deduplication, Demo Record Detection, and Merging.
"""

import pytest
from fastapi.testclient import TestClient
from backend.app import app
from backend.database import db


@pytest.fixture
def client():
    return TestClient(app)


def test_phone_normalization_helper():
    """Validates that normalize_phone strips spaces, dashes, parens, and standardizes digits."""
    from backend.database import normalize_phone
    assert normalize_phone("+1 (415) 555-1234") == "14155551234"
    assert normalize_phone("  +91 76009 58393 ") == "917600958393"
    assert normalize_phone("+44-20-7946-0958") == "442079460958"
    assert normalize_phone("917622029755") == "917622029755"


def test_demo_record_identification_and_preservation():
    """
    Verifies that get_identified_demo_records identifies synthetic test fixtures
    while strictly protecting genuine contacts like Gaurav or Me.
    """
    # Insert genuine contacts
    g_id = db.add_contact(name="Gaurav", phone="+91 76009 58393", group_name="Default")
    m_id = db.add_contact(name="Me", phone="+91 76220 29755", group_name="Default")

    # Insert synthetic test fixtures
    d1 = db.add_contact(name="Jane Doe", phone="+14155559876", group_name="Default")
    d2 = db.add_contact(name="Beta User", phone="+14155551122", group_name="Default")
    d3 = db.add_contact(name="Bulk 1", phone="+14155553001", group_name="Default")
    d4 = db.add_contact(name="Opted Out User", phone="+14155559999", group_name="Default")

    demo_records = db.get_identified_demo_records()
    demo_ids = [r["id"] for r in demo_records]

    # Genuine records must NEVER be classified as demo
    assert g_id not in demo_ids
    assert m_id not in demo_ids

    # Synthetic fixtures must be identified
    assert d1 in demo_ids
    assert d2 in demo_ids
    assert d3 in demo_ids
    assert d4 in demo_ids

    # Clean up test insertions
    for cid in [g_id, m_id, d1, d2, d3, d4]:
        db.delete_contact(cid)


def test_remove_identified_demo_records_requires_confirmation(client):
    """
    Verifies POST /api/contacts/demo-records/remove requires explicit confirmation,
    deletes only confirmed demo records, and preserves genuine records.
    """
    g_id = db.add_contact(name="Gaurav", phone="917600958393")
    d1 = db.add_contact(name="Jane Doe Demo", phone="14155559876")
    d2 = db.add_contact(name="Bulk 2 Demo", phone="14155553002")

    # Unconfirmed attempt should be rejected
    res_unconf = client.post("/api/contacts/demo-records/remove", json={"confirmed": False})
    assert res_unconf.status_code == 400

    # Confirmed removal
    res_conf = client.post("/api/contacts/demo-records/remove", json={"confirmed": True})
    assert res_conf.status_code == 200
    data = res_conf.json()
    assert data["deleted_count"] >= 2

    # Genuine contact still exists
    assert db.get_contact(g_id) is not None
    # Demo contacts are deleted
    assert db.get_contact(d1) is None
    assert db.get_contact(d2) is None

    # Cleanup
    db.delete_contact(g_id)


def test_duplicate_detection_and_merge_workflow(client):
    """
    Verifies detection of duplicate phone numbers and transactional merge into a primary record.
    """
    c1 = db.add_contact(name="Primary Contact", phone="+91 98765 43210", group_name="Default", customer_tier="Regular")
    c2 = db.add_contact(name="Duplicate 1", phone="919876543210", group_name="VIP", customer_tier="VIP")

    dups = db.get_duplicate_contacts()
    assert len(dups) >= 1
    dup_cluster = next((d for d in dups if d["normalized_phone"] == "919876543210"), None)
    assert dup_cluster is not None
    assert c1 in dup_cluster["contact_ids"]
    assert c2 in dup_cluster["contact_ids"]

    # Test merge endpoint: merge c2 into c1
    merge_res = client.post("/api/contacts/merge", json={
        "primary_id": c1,
        "duplicate_ids": [c2],
        "merged_data": {"customer_tier": "VIP", "group_name": "VIP"}
    })
    assert merge_res.status_code == 200
    m_data = merge_res.json()
    assert m_data["success"] is True

    # Primary record updated and duplicate removed
    primary = db.get_contact(c1)
    assert primary is not None
    assert primary["customer_tier"] == "VIP"
    assert db.get_contact(c2) is None

    # Cleanup
    db.delete_contact(c1)


def test_add_contact_deduplication(client):
    """
    Verifies that adding a contact with an already existing normalized phone number
    handles deduplication honestly according to policy.
    """
    res1 = client.post("/api/contacts", json={"name": "Alice Smith", "phone": "+1 415 555 7777"})
    assert res1.status_code == 200
    cid1 = res1.json()["id"]

    # Attempt to add same phone with different formatting
    res2 = client.post("/api/contacts", json={"name": "Alice Duplicate", "phone": "1-415-555-7777", "deduplicate": True})
    assert res2.status_code == 409  # Conflict
    detail = res2.json()["detail"]
    msg = detail.get("message") if isinstance(detail, dict) else str(detail)
    assert "already exists" in msg.lower()

    # Cleanup
    db.delete_contact(cid1)


def test_bulk_delete_contacts_server_side(client):
    """Verifies that bulk delete deletes multiple contacts in a single transactional call."""
    c1 = db.add_contact(name="Batch 1", phone="1234567801")
    c2 = db.add_contact(name="Batch 2", phone="1234567802")
    c3 = db.add_contact(name="Batch 3", phone="1234567803")

    del_res = client.post("/api/contacts/bulk-delete", json={"contact_ids": [c1, c2, c3]})
    assert del_res.status_code == 200
    assert del_res.json()["deleted_count"] == 3

    assert db.get_contact(c1) is None
    assert db.get_contact(c2) is None
    assert db.get_contact(c3) is None


def test_bulk_copy_contacts_endpoint(client):
    """Verifies copying contacts into a target group creates copies with the new group name."""
    c1 = db.add_contact(name="User Original", phone="9988776655", group_name="Default")
    
    copy_res = client.post("/api/contacts/bulk-copy", json={"contact_ids": [c1], "target_group": "Newsletter"})
    assert copy_res.status_code == 200
    assert copy_res.json()["copied_count"] == 1

    contacts = db.get_contacts(group_name="Newsletter")
    copied = next((c for c in contacts if c["phone"] == "9988776655"), None)
    assert copied is not None
    assert copied["group_name"] == "Newsletter"

    # Original still exists in Default
    assert db.get_contact(c1)["group_name"] == "Default"

    # Cleanup
    db.delete_contact(c1)
    db.delete_contact(copied["id"])

