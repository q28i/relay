"""
Test-Driven Development Suite for Priority Fix:
1. Media persistence, hashing, and honest missing-file detection.
2. WhatsApp Web test-send with media and caption.
3. Contact editing (tier, group, language, phone, consent).
4. Group management (create, rename, delete with migration).
5. Bulk contact actions (move group, edit tier/language/consent).
6. Deterministic, auditable campaign allocation (rule-based, balanced rotation, explicit default, reproducible seed).
7. Queue durability and restart recovery preserving selected variant and media.
"""

import os
import io
import json
import time
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.app import app
from backend.database import db
from backend.job_queue import BackgroundJobWorker
from backend.adapter import MockMessagingProvider
from whatsapp_engine import WhatsAppEngine


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. MEDIA PERSISTENCE, HASHING, & HONEST MISSING FILE DETECTION
# ==============================================================================

def test_media_upload_persistence_and_hash(client):
    """Verifies media is saved to durable storage, SHA-256 computed, and persisted in SQLite."""
    file_bytes = b"Sample PNG Image Content for WhatsApp Attachment Test"
    file_obj = io.BytesIO(file_bytes)
    
    response = client.post(
        "/api/media/upload",
        files={"file": ("test_promo.png", file_obj, "image/png")},
        data={"title": "Promo Banner 2026", "asset_type": "image"}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "id" in data
    assert data["title"] == "Promo Banner 2026"
    assert "content_hash" in data
    assert len(data["content_hash"]) == 64  # SHA-256 hex string
    assert data["is_available"] is True

    # Retrieve details
    get_res = client.get(f"/api/media/{data['id']}")
    assert get_res.status_code == 200
    details = get_res.json()
    assert details["content_hash"] == data["content_hash"]
    assert os.path.isfile(details["file_path"])

    # Clean up test asset
    client.delete(f"/api/media/{data['id']}")


def test_missing_media_file_detection(client):
    """Verifies that if a media file is missing from disk, it is honestly marked unavailable."""
    # Insert media record pointing to non-existent file
    non_existent_path = os.path.join(os.getcwd(), "uploads", "media", "non_existent_ghost.png")
    if os.path.exists(non_existent_path):
        os.remove(non_existent_path)

    asset_id = db.add_media_asset(
        title="Ghost Asset",
        filename="non_existent_ghost.png",
        file_path=non_existent_path,
        file_size=1024,
        mime_type="image/png",
        asset_type="image",
        content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )

    asset = db.get_media_asset(asset_id)
    assert asset is not None
    assert asset["is_available"] is False

    # Attempting to send test-send with missing media must fail honestly, NOT send text-only!
    send_res = client.post(
        "/api/browser-profile/test-send",
        json={
            "phone": "+14155552671",
            "message": "Check our ghost promo!",
            "media_id": asset_id
        }
    )
    assert send_res.status_code in (400, 500)
    err_detail = send_res.json().get("detail", {})
    msg = err_detail.get("message", "") if isinstance(err_detail, dict) else str(err_detail)
    assert "media" in msg.lower() or "missing" in msg.lower() or "unavailable" in msg.lower()

    # Clean up
    db.delete_media_asset(asset_id, force=True)


def test_media_deletion_protection_when_referenced(client):
    """Verifies a media asset cannot be deleted without force if referenced by an active/scheduled campaign."""
    # 1. Create media
    file_bytes = b"Brochure content"
    res = client.post(
        "/api/media/upload",
        files={"file": ("brochure.pdf", io.BytesIO(file_bytes), "application/pdf")},
        data={"title": "Q4 Brochure", "asset_type": "document"}
    )
    asset_id = res.json()["id"]

    # 2. Reference in campaign
    db.create_campaign(
        name="Brochure Campaign",
        template_id=None,
        group_name="Default",
        attachment_path=res.json()["file_path"],
        media_asset_id=asset_id
    )

    # 3. Attempt delete without force must return 409 Conflict
    del_res = client.delete(f"/api/media/{asset_id}")
    assert del_res.status_code == 409
    d = del_res.json()
    msg = d.get("message") or (d["detail"]["message"] if isinstance(d.get("detail"), dict) else str(d.get("detail", "")))
    assert "referenced" in msg.lower()

    # 4. Delete with force succeeds
    del_force = client.delete(f"/api/media/{asset_id}?force=true")
    assert del_force.status_code == 200
    assert del_force.json()["success"] is True


# ==============================================================================
# 2. CONTACT EDITING & MANAGEMENT
# ==============================================================================

def test_contact_edit_persists_tier_group_language(client):
    """Verifies editing a contact updates tier, group, language, custom fields, and audits changes."""
    # Create contact
    contact_res = client.post(
        "/api/contacts",
        json={
            "name": "Jane Doe",
            "phone": "+14155559876",
            "group_name": "Default",
            "consent_status": "opted_in",
            "customer_tier": "Regular",
            "language": "en"
        }
    )
    assert contact_res.status_code == 200
    cid = contact_res.json()["id"]

    # Edit contact to VIP tier, VIP group, Spanish language
    update_res = client.put(
        f"/api/contacts/{cid}",
        json={
            "name": "Jane Doe VIP",
            "phone": "+14155559876",
            "group_name": "VIP",
            "customer_tier": "VIP",
            "language": "es",
            "consent_status": "opted_in",
            "custom_fields": {"vip_level": "Gold", "loyalty_points": "500"}
        }
    )
    assert update_res.status_code == 200, update_res.text
    updated = update_res.json()
    assert updated["name"] == "Jane Doe VIP"
    assert updated["group_name"] == "VIP"
    assert updated["customer_tier"] == "VIP"
    assert updated["language"] == "es"

    # Reload from DB and verify persistence
    c_db = db.get_contact(cid)
    assert c_db["customer_tier"] == "VIP"
    assert c_db["language"] == "es"
    assert c_db["group_name"] == "VIP"

    # Verify audit log recorded the edit
    logs = db.get_audit_logs(limit=10)
    matching = [l for l in logs if f"contact #{cid}" in l["message"].lower() or "jane doe" in l["message"].lower()]
    assert len(matching) > 0

    # Clean up
    client.delete(f"/api/contacts/{cid}")


def test_contact_opt_out_protection_no_automatic_opt_in(client):
    """Ensures an opted-out contact cannot be automatically changed to opted-in without explicit override."""
    # 1. Create opted-out contact
    contact_res = client.post(
        "/api/contacts",
        json={
            "name": "Opted Out User",
            "phone": "+14155559999",
            "group_name": "Default",
            "consent_status": "opted_out",
            "opt_out_reason": "Requested unsubscription"
        }
    )
    cid = contact_res.json()["id"]
    assert contact_res.json()["consent_status"] == "opted_out"

    # 2. Regular edit without explicit confirmation must NOT overwrite opted_out to opted_in
    edit_res = client.put(
        f"/api/contacts/{cid}",
        json={
            "name": "Opted Out User Edited",
            "phone": "+14155559999",
            "group_name": "Default",
            "customer_tier": "VIP",
            "consent_status": "opted_in"  # Attempting to change to opted_in without confirm
        }
    )
    # Must reject or preserve opted_out
    c_check = db.get_contact(cid)
    assert c_check["consent_status"] == "opted_out", "Contact must NEVER be automatically changed from opted_out to opted_in!"

    # Clean up
    client.delete(f"/api/contacts/{cid}")


def test_group_management_rename_and_delete_with_migration(client):
    """Verifies creating, renaming, and deleting groups with contact migration."""
    # 1. Create group
    g_res = client.post("/api/contacts/groups", json={"name": "Beta Testers", "description": "Early access users"})
    assert g_res.status_code == 200

    # 2. Add contact to group
    c_res = client.post("/api/contacts", json={"name": "Beta User", "phone": "+14155551122", "group_name": "Beta Testers"})
    cid = c_res.json()["id"]

    # 3. Rename group
    rename_res = client.put(
        "/api/contacts/groups/Beta%20Testers",
        json={"name": "Early Adopters", "description": "Renamed early access users"}
    )
    assert rename_res.status_code == 200

    # Verify contact was updated to the new group name
    c_check = db.get_contact(cid)
    assert c_check["group_name"] == "Early Adopters"

    # 4. Delete group with fallback migration to 'Default'
    del_res = client.delete("/api/contacts/groups/Early%20Adopters?fallback_group=Default")
    assert del_res.status_code == 200

    # Verify contact moved to Default
    c_after_del = db.get_contact(cid)
    assert c_after_del["group_name"] == "Default"

    # Clean up
    client.delete(f"/api/contacts/{cid}")


def test_bulk_move_and_bulk_edit_contacts(client):
    """Verifies bulk moving contacts between groups and bulk editing tier and language."""
    # Create 3 contacts
    c1 = client.post("/api/contacts", json={"name": "Bulk 1", "phone": "+14155553001", "group_name": "Default"}).json()["id"]
    c2 = client.post("/api/contacts", json={"name": "Bulk 2", "phone": "+14155553002", "group_name": "Default"}).json()["id"]
    c3 = client.post("/api/contacts", json={"name": "Bulk 3", "phone": "+14155553003", "group_name": "Default"}).json()["id"]

    # Bulk move c1 and c2 to VIP group
    move_res = client.post(
        "/api/contacts/bulk-move",
        json={"contact_ids": [c1, c2], "target_group": "VIP"}
    )
    assert move_res.status_code == 200
    assert move_res.json()["updated_count"] == 2

    assert db.get_contact(c1)["group_name"] == "VIP"
    assert db.get_contact(c2)["group_name"] == "VIP"
    assert db.get_contact(c3)["group_name"] == "Default"

    # Bulk edit tier to Enterprise and language to Spanish
    bulk_edit_res = client.post(
        "/api/contacts/bulk-edit",
        json={"contact_ids": [c1, c2, c3], "customer_tier": "Enterprise", "language": "es"}
    )
    assert bulk_edit_res.status_code == 200
    assert bulk_edit_res.json()["updated_count"] == 3

    for cid in [c1, c2, c3]:
        c = db.get_contact(cid)
        assert c["customer_tier"] == "Enterprise"
        assert c["language"] == "es"
        client.delete(f"/api/contacts/{cid}")


# ==============================================================================
# 3. CAMPAIGN ALLOCATION: RULE-BASED, BALANCED ROTATION, & REPRODUCIBLE SEED
# ==============================================================================

def test_rule_based_allocation(client):
    """Verifies recipients are matched to variants by rules (e.g. language/tier)."""
    # 1. Create template with 2 variants
    t_name = f"Bilingual Promo {time.time()}"
    t_res = client.post("/api/templates", json={"name": t_name, "content": "Hello {name}!"})
    assert t_res.status_code == 200, t_res.text
    tid = t_res.json()["id"]

    # Spanish variant
    client.post(
        f"/api/templates/{tid}/variants",
        json={
            "variant_name": "Spanish Version",
            "purpose": "Language localization",
            "audience_filter_field": "language",
            "audience_filter_value": "es",
            "content": "¡Hola {name}! Oferta especial para ti."
        }
    )

    # VIP variant
    client.post(
        f"/api/templates/{tid}/variants",
        json={
            "variant_name": "VIP Version",
            "purpose": "VIP Tier Offer",
            "audience_filter_field": "customer_tier",
            "audience_filter_value": "VIP",
            "content": "Dear VIP {name}, exclusive rewards await."
        }
    )

    # Test audience: 1 Spanish, 1 VIP, 1 Default English
    contacts = [
        {"name": "Carlos", "phone": "+14155554001", "language": "es", "customer_tier": "Regular"},
        {"name": "Victoria", "phone": "+14155554002", "language": "en", "customer_tier": "VIP"},
        {"name": "Edward", "phone": "+14155554003", "language": "en", "customer_tier": "Regular"}
    ]

    worker = BackgroundJobWorker()
    c_name = f"RuleBasedTest_{time.time()}"
    job = worker.start_campaign_job(
        campaign_name=c_name,
        contacts=contacts,
        template_content="Default fallback {name}",
        template_id=tid,
        allocation_method="rule_based",
        use_mock=True
    )
    job_id = job["id"]

    # Check staged queue items
    items = db.get_queue_items(job_id=job_id, limit=10)
    assert len(items) == 3

    carlos_item = next(i for i in items if i["recipient_name"] == "Carlos")
    victoria_item = next(i for i in items if i["recipient_name"] == "Victoria")
    edward_item = next(i for i in items if i["recipient_name"] == "Edward")

    assert "¡Hola Carlos!" in carlos_item["resolved_message"]
    assert "Rule-based" in carlos_item["allocation_rule"]
    assert "VIP Victoria" in victoria_item["resolved_message"]
    assert "Default fallback Edward" in edward_item["resolved_message"]

    worker.cancel_job(job_id)
    client.delete(f"/api/templates/{tid}")


def test_balanced_rotation_allocation(client):
    """Verifies deterministic round-robin distribution across approved alternatives."""
    t_name = f"Rotation Template {time.time()}"
    t_res = client.post("/api/templates", json={"name": t_name, "content": "Base {name}"})
    assert t_res.status_code == 200, t_res.text
    tid = t_res.json()["id"]

    # Add 2 variants
    client.post(f"/api/templates/{tid}/variants", json={"variant_name": "Creative A", "purpose": "Angle A", "content": "Variant A {name}"})
    client.post(f"/api/templates/{tid}/variants", json={"variant_name": "Creative B", "purpose": "Angle B", "content": "Variant B {name}"})

    contacts = [
        {"name": f"User {i}", "phone": f"+1415555500{i}"} for i in range(1, 7)
    ]

    worker = BackgroundJobWorker()
    job = worker.start_campaign_job(
        campaign_name="RotationTest",
        contacts=contacts,
        template_content="Base {name}",
        template_id=tid,
        allocation_method="balanced_rotation",
        use_mock=True
    )
    job_id = job["id"]

    items = db.get_queue_items(job_id=job_id, limit=10)
    assert len(items) == 6

    # Expect alternating: Creative A, Creative B, Creative A, Creative B...
    for idx, item in enumerate(items):
        expected_variant = "Variant A" if (idx % 2 == 0) else "Variant B"
        assert expected_variant in item["resolved_message"]
        assert "Balanced rotation" in item["allocation_rule"]

    worker.cancel_job(job_id)
    client.delete(f"/api/templates/{tid}")


def test_reproducible_seeded_ab_allocation(client):
    """Verifies A/B test allocation is reproducible given the same campaign seed."""
    t_name = f"Seeded AB {time.time()}"
    t_res = client.post("/api/templates", json={"name": t_name, "content": "Base {name}"})
    assert t_res.status_code == 200, t_res.text
    tid = t_res.json()["id"]
    client.post(f"/api/templates/{tid}/variants", json={"variant_name": "Alt 1", "purpose": "Angle 1", "content": "Alt 1 {name}"})
    client.post(f"/api/templates/{tid}/variants", json={"variant_name": "Alt 2", "purpose": "Angle 2", "content": "Alt 2 {name}"})

    contacts = [{"name": f"Cust {i}", "phone": f"+1415555600{i}"} for i in range(1, 11)]

    worker = BackgroundJobWorker()
    # Run 1 with seed 12345
    job1 = worker.start_campaign_job(
        campaign_name="SeedTest1",
        contacts=contacts,
        template_content="Base {name}",
        template_id=tid,
        allocation_method="reproducible_ab_test",
        allocation_seed=12345,
        use_mock=True
    )
    items1 = db.get_queue_items(job_id=job1["id"], limit=20)
    worker.cancel_job(job1["id"])

    # Run 2 with same seed 12345
    job2 = worker.start_campaign_job(
        campaign_name="SeedTest2",
        contacts=contacts,
        template_content="Base {name}",
        template_id=tid,
        allocation_method="reproducible_ab_test",
        allocation_seed=12345,
        use_mock=True
    )
    items2 = db.get_queue_items(job_id=job2["id"], limit=20)
    worker.cancel_job(job2["id"])

    # Every recipient must have identical assigned variant across both runs!
    for i1, i2 in zip(items1, items2):
        assert i1["resolved_message"] == i2["resolved_message"]
        assert i1["variant_id"] == i2["variant_id"]

    client.delete(f"/api/templates/{tid}")


# ==============================================================================
# 4. QUEUE DURABILITY & RECOVERY PRESERVING SELECTED VARIANT & MEDIA
# ==============================================================================

def test_queue_item_recovery_and_retry_preserves_variant_and_media():
    """Verifies that when a queue item is retried or loaded after restart, its selected variant and media remain immutable."""
    worker = BackgroundJobWorker()
    job_id = f"job_durable_{int(time.time())}"

    # Insert queue item directly
    db.create_job(job_id, "DurableCampaign", total_count=1)
    db.bulk_enqueue_items(
        campaign_id="DurableCampaign",
        job_id=job_id,
        items=[{
            "idempotency_key": f"key_{job_id}",
            "recipient_name": "Alice Springs",
            "recipient_phone": "+14155557788",
            "variant_id": 99,
            "variant_purpose": "Exclusive VIP Promo",
            "resolved_message": "Hello Alice, VIP 20% off!",
            "media_path": "C:\\fake\\path\\promo.png",
            "media_asset_id": 42,
            "allocation_rule": "Rule-based: customer_tier='VIP'",
            "status": "PENDING",
            "max_retries": 3,
            "error_message": ""
        }]
    )

    items = db.get_queue_items(job_id=job_id, limit=1)
    item = items[0]
    assert item["variant_id"] == 99
    assert item["media_asset_id"] == 42
    assert item["media_path"] == "C:\\fake\\path\\promo.png"
    assert item["allocation_rule"] == "Rule-based: customer_tier='VIP'"

    # Simulate retry
    db.update_queue_item_status(item["id"], "RETRYING", error_message="Network glitch", retry_count=1)
    retried_item = db.get_queue_items(job_id=job_id, limit=1)[0]

    # Content and references MUST NOT change on retry
    assert retried_item["variant_id"] == 99
    assert retried_item["media_asset_id"] == 42
    assert retried_item["resolved_message"] == "Hello Alice, VIP 20% off!"
    assert retried_item["retry_count"] == 1

    worker.cancel_job(job_id)
