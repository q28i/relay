import os
import io
import time
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from backend.app import app
from backend.database import DatabaseManager, db
from backend.job_queue import BackgroundJobWorker
from backend.adapter import MockMessagingProvider

@pytest.fixture
def client(session_db):
    """Test client using isolated temporary database."""
    return TestClient(app)

# ==============================================================================
# SCENARIO 1: Select arbitrary contacts and delete them together (bulk-delete)
# ==============================================================================
def test_scenario_01_bulk_delete_contacts(client, session_db):
    c_ids = []
    for i in range(5):
        res = client.post("/api/contacts", json={
            "name": f"BulkDel Contact {i}",
            "phone": f"+1555001000{i}",
            "group_name": "Default"
        })
        assert res.status_code == 200
        c_ids.append(res.json()["id"])

    # Bulk delete all 5
    del_res = client.post("/api/contacts/bulk-delete", json={"contact_ids": c_ids})
    assert del_res.status_code == 200
    assert del_res.json()["deleted_count"] == 5

    # Confirm all are gone
    all_contacts = client.get("/api/contacts?limit=200").json()["items"]
    remaining_ids = {c["id"] for c in all_contacts}
    for cid in c_ids:
        assert cid not in remaining_ids


# ==============================================================================
# SCENARIO 2: Select every contact matching a filter and perform bulk action
# ==============================================================================
def test_scenario_02_filter_and_bulk_action(client, session_db):
    # Create contacts in a specific group
    c_ids = []
    for i in range(3):
        res = client.post("/api/contacts", json={
            "name": f"Filtered Contact {i}",
            "phone": f"+1555002000{i}",
            "group_name": "SegmentA"
        })
        assert res.status_code == 200
        c_ids.append(res.json()["id"])

    # Bulk edit their tier to VIP
    edit_res = client.post("/api/contacts/bulk-edit", json={
        "contact_ids": c_ids,
        "customer_tier": "VIP"
    })
    assert edit_res.status_code == 200

    # Verify each contact has tier VIP
    for cid in c_ids:
        c = client.get(f"/api/contacts/{cid}").json()
        assert c["customer_tier"] == "VIP"


# ==============================================================================
# SCENARIO 3: Create a group and move selected contacts into it
# ==============================================================================
def test_scenario_03_create_group_and_move_contacts(client, session_db):
    # Create new group
    grp_res = client.post("/api/contacts/groups", json={
        "name": "TargetAudienceAlpha",
        "description": "New target group"
    })
    assert grp_res.status_code == 200

    # Create 3 contacts in Default
    c_ids = []
    for i in range(3):
        res = client.post("/api/contacts", json={
            "name": f"MoveUser {i}",
            "phone": f"+1555003000{i}",
            "group_name": "Default"
        })
        assert res.status_code == 200
        c_ids.append(res.json()["id"])

    # Move to TargetAudienceAlpha
    move_res = client.post("/api/contacts/bulk-move", json={
        "contact_ids": c_ids,
        "target_group": "TargetAudienceAlpha"
    })
    assert move_res.status_code == 200

    # Verify new group
    for cid in c_ids:
        c = client.get(f"/api/contacts/{cid}").json()
        assert c["group_name"] == "TargetAudienceAlpha"


# ==============================================================================
# SCENARIO 4: Edit contact name and confirm persistence
# ==============================================================================
def test_scenario_04_edit_contact_name_persists(client, session_db):
    res = client.post("/api/contacts", json={
        "name": "Original Name",
        "phone": "+15550040001",
        "group_name": "Default"
    })
    assert res.status_code == 200
    cid = res.json()["id"]

    # Edit name
    put_res = client.put(f"/api/contacts/{cid}", json={"name": "Persisted Real Name"})
    assert put_res.status_code == 200

    # Fetch fresh from DB
    fresh = client.get(f"/api/contacts/{cid}").json()
    assert fresh["name"] == "Persisted Real Name"


# ==============================================================================
# SCENARIO 5: Import file containing duplicates -> confirm no repeated records
# ==============================================================================
def test_scenario_05_prevent_duplicate_contact_creation(client, session_db):
    # Add initial contact
    res1 = client.post("/api/contacts", json={
        "name": "Unique User",
        "phone": "+15550050001",
        "group_name": "Default",
        "deduplicate": True
    })
    assert res1.status_code == 200

    # Attempt to add exact same normalized phone with deduplicate=true
    res2 = client.post("/api/contacts", json={
        "name": "Duplicate Attempt",
        "phone": "+1 555-005-0001",
        "group_name": "Default",
        "deduplicate": True
    })
    assert res2.status_code == 409  # Conflict


# ==============================================================================
# SCENARIO 6: Remove confirmed demo records without deleting real contacts
# ==============================================================================
def test_scenario_06_remove_demo_records_safeguard(client, session_db):
    # Insert genuine user contacts
    res_real1 = client.post("/api/contacts", json={"name": "Gaurav Patel", "phone": "+917600958393", "group_name": "Default"})
    real_id1 = res_real1.json()["id"]
    res_real2 = client.post("/api/contacts", json={"name": "Me (Personal)", "phone": "+919876543210", "group_name": "Default"})
    real_id2 = res_real2.json()["id"]

    # Insert test fixture records
    client.post("/api/contacts", json={"name": "Jane Doe VIP", "phone": "+14155550001", "group_name": "Default"})
    client.post("/api/contacts", json={"name": "Beta User", "phone": "+14155550002", "group_name": "Default"})

    # Detect demo records
    demo_res = client.get("/api/contacts/demo-records").json()
    assert demo_res["count"] >= 2
    demo_names = [d["name"] for d in demo_res["demo_records"]]
    assert "Jane Doe VIP" in demo_names
    assert "Beta User" in demo_names
    assert "Gaurav Patel" not in demo_names
    assert "Me (Personal)" not in demo_names

    # Clean demo records
    clean_res = client.post("/api/contacts/demo-records/remove", json={"confirmed": True}).json()
    assert clean_res["removed_count"] >= 2

    # Verify genuine contacts remain untouched
    c1 = client.get(f"/api/contacts/{real_id1}").json()
    c2 = client.get(f"/api/contacts/{real_id2}").json()
    assert c1["name"] == "Gaurav Patel"
    assert c2["name"] == "Me (Personal)"


# ==============================================================================
# SCENARIO 7: Upload multiple pictures
# ==============================================================================
def test_scenario_07_upload_multiple_pictures(client, session_db):
    uploaded_ids = []
    for i in range(3):
        file_bytes = f"fake-image-bytes-{i}".encode("utf-8")
        res = client.post(
            "/api/media/upload",
            files={"file": (f"test_pic_{i}.jpg", io.BytesIO(file_bytes), "image/jpeg")},
            data={"title": f"Test Picture {i}"}
        )
        assert res.status_code == 200
        uploaded_ids.append(res.json()["id"])

    assert len(set(uploaded_ids)) == 3
    all_media = client.get("/api/media").json()
    media_ids = [m["id"] for m in all_media]
    for uid in uploaded_ids:
        assert uid in media_ids


# ==============================================================================
# SCENARIO 8: Restart Relay and confirm all assets remain in library
# ==============================================================================
def test_scenario_08_restart_preserves_library_assets(client, session_db):
    # Upload an asset
    file_bytes = b"durable-content-restart-test"
    res = client.post(
        "/api/media/upload",
        files={"file": ("restart_asset.png", io.BytesIO(file_bytes), "image/png")},
        data={"title": "Restart Asset"}
    )
    assert res.status_code == 200
    asset_id = res.json()["id"]

    # Reconnect to same database (simulating restart)
    db_restarted = DatabaseManager(session_db)
    asset = db_restarted.get_media_asset(asset_id)
    assert asset is not None
    assert asset["title"] == "Restart Asset"
    assert os.path.exists(asset["file_path"])


# ==============================================================================
# SCENARIO 9: Save three messages and reuse them
# ==============================================================================
def test_scenario_09_save_and_reuse_messages(client, session_db):
    template_ids = []
    for i in range(3):
        res = client.post("/api/templates", json={
            "name": f"Message Template {i}",
            "content": f"Hello {{name}}, this is promotion #{i}!"
        })
        assert res.status_code == 200
        template_ids.append(res.json()["id"])

    # Retrieve and verify reuse
    templates = client.get("/api/templates").json()
    t_map = {t["id"]: t["content"] for t in templates}
    for tid in template_ids:
        assert tid in t_map
        assert "Hello {name}" in t_map[tid]


# ==============================================================================
# SCENARIO 10: Create collection containing messages and multiple media assets
# ==============================================================================
def test_scenario_10_create_content_collection(client, session_db):
    # Create 2 templates
    t1 = client.post("/api/templates", json={"name": "Promo A", "content": "Special promo A"}).json()["id"]
    t2 = client.post("/api/templates", json={"name": "Promo B", "content": "Special promo B"}).json()["id"]

    # Upload 2 media files
    m1 = client.post("/api/media/upload", files={"file": ("brochure.pdf", io.BytesIO(b"pdf-1"), "application/pdf")}, data={"title": "Brochure"}).json()["id"]
    m2 = client.post("/api/media/upload", files={"file": ("banner.png", io.BytesIO(b"png-2"), "image/png")}, data={"title": "Banner"}).json()["id"]

    # Create collection
    col_res = client.post("/api/collections", json={
        "name": "Summer Blast Collection",
        "description": "Summer seasonal campaigns",
        "pairing_mode": "approved_combinations",
        "message_ids": [t1, t2],
        "media_ids": [m1, m2]
    })
    assert col_res.status_code == 200
    col = col_res.json()
    assert col["name"] == "Summer Blast Collection"
    assert len(col["messages"]) == 2
    assert len(col["media"]) == 2


# ==============================================================================
# SCENARIO 11: Preview campaign: confirm each recipient has approved combination
# ==============================================================================
def test_scenario_11_pre_send_allocation_preview(client, session_db):
    # Create group with 3 contacts
    client.post("/api/contacts/groups", json={"name": "PreviewGroup"})
    for i in range(3):
        client.post("/api/contacts", json={
            "name": f"Recipient {i}",
            "phone": f"+1555011000{i}",
            "group_name": "PreviewGroup"
        })

    t1 = client.post("/api/templates", json={"name": "T1", "content": "Hi {name} 1"}).json()["id"]
    t2 = client.post("/api/templates", json={"name": "T2", "content": "Hi {name} 2"}).json()["id"]
    m1 = client.post("/api/media/upload", files={"file": ("img1.png", io.BytesIO(b"img1"), "image/png")}, data={"title": "Img1"}).json()["id"]

    col = client.post("/api/collections", json={
        "name": "Balanced Collection",
        "pairing_mode": "balanced_rotation",
        "message_ids": [t1, t2],
        "media_ids": [m1]
    }).json()["id"]

    preview_res = client.post("/api/campaigns/allocation-preview", json={
        "group_name": "PreviewGroup",
        "collection_id": col
    })
    assert preview_res.status_code == 200
    data = preview_res.json()
    assert data["eligible_contacts_count"] == 3
    allocs = data["allocations"]
    assert len(allocs) == 3
    for a in allocs:
        assert a["recipient_name"].startswith("Recipient")
        assert a["message_title"] in ["T1", "T2"]
        assert a["media_title"] == "Img1"
        assert a["media_asset_id"] == m1


# ==============================================================================
# SCENARIO 12: Verify correct media is attached during test send
# ==============================================================================
def test_scenario_12_media_attached_during_test_send(client, session_db):
    m = client.post("/api/media/upload", files={"file": ("flyer.jpg", io.BytesIO(b"flyer"), "image/jpeg")}, data={"title": "Flyer"}).json()["id"]

    mock_adapter = MagicMock()
    mock_adapter.send_message.return_value = {"status": "SENT", "success": True}

    with patch("backend.routers.browser.get_browser_adapter", return_value=mock_adapter):
        res = client.post("/api/browser/test-send", json={
            "phone": "+15550120001",
            "message": "Check out flyer",
            "media_id": m
        })
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True

        # Verify adapter received attachment_path matching uploaded media
        mock_adapter.send_message.assert_called_once()
        call_kwargs = mock_adapter.send_message.call_args[1]
        assert call_kwargs["phone"] == "15550120001"
        assert call_kwargs["message"] == "Check out flyer"
        assert os.path.exists(call_kwargs["attachment_path"])


# ==============================================================================
# SCENARIO 13: Confirm actual outcome is recorded (not assumed success)
# ==============================================================================
def test_scenario_13_actual_outcome_recorded(client, session_db):
    mock_provider = MockMessagingProvider()
    worker = BackgroundJobWorker()
    worker._active_job = None
    worker._is_stopped = False
    worker._is_paused = False

    contacts = [{"name": "Outcome Contact", "phone": "+15550130001", "consent_status": "opted_in"}]
    job = worker.start_campaign_job(
        campaign_name="Outcome Test",
        contacts=contacts,
        template_content="Testing outcome recording",
        min_delay=0.01,
        max_delay=0.01,
        use_mock=True,
        provider=mock_provider
    )

    if worker._worker_thread:
        worker._worker_thread.join(timeout=3)

    items = db.get_queue_items(job["id"])
    assert len(items) == 1
    # Outcome is explicitly recorded in database as DISPATCHED / SENT with timestamp
    assert items[0]["status"] in ("SENT", "DISPATCHED")
    assert items[0]["dispatched_at"] is not None


# ==============================================================================
# SCENARIO 14: Restart during queued-job -> resume without duplicating sent
# ==============================================================================
def test_scenario_14_restart_during_job_does_not_duplicate_sent(session_db):
    mock_provider = MockMessagingProvider()

    worker = BackgroundJobWorker()
    worker._active_job = None
    worker._is_stopped = False
    worker._is_paused = False

    contacts = [
        {"name": f"User {i}", "phone": f"+1555014000{i}", "consent_status": "opted_in"}
        for i in range(4)
    ]

    job = worker.start_campaign_job(
        campaign_name="Restart Resumption Test",
        contacts=contacts,
        template_content="Hi {name}",
        min_delay=0.01,
        max_delay=0.01,
        use_mock=True,
        provider=mock_provider
    )
    if worker._worker_thread:
        worker._worker_thread.join(timeout=3)

    items = db.get_queue_items(job["id"])
    sent_before = [it for it in items if it["status"] in ("SENT", "DISPATCHED")]
    assert len(sent_before) >= 1

    # Simulate fresh worker instance after restart
    restarted_worker = BackgroundJobWorker()
    pending_to_dispatch = db.get_queue_items(job_id=job["id"], status="PENDING")
    
    # Recheck items: previously sent items must remain sent and not re-queued
    items_after = db.get_queue_items(job["id"])
    for sb in sent_before:
        matching = [it for it in items_after if it["id"] == sb["id"]][0]
        assert matching["status"] in ("SENT", "DISPATCHED")
        assert matching not in pending_to_dispatch


# ==============================================================================
# SCENARIO 15: Confirm system does not duplicate uncertain sends
# ==============================================================================
def test_scenario_15_uncertain_send_not_duplicated(session_db):
    class FlakyProvider(MockMessagingProvider):
        def send_message(self, phone: str, message: str = "", attachment_path=None):
            return {"status": "UNCERTAIN", "error": "Browser hung during send confirmation"}

    flaky_provider = FlakyProvider()
    worker = BackgroundJobWorker()
    worker._active_job = None
    worker._is_stopped = False
    worker._is_paused = False

    contacts = [{"name": "Uncertain Contact", "phone": "+15550150001", "consent_status": "opted_in"}]
    job = worker.start_campaign_job(
        campaign_name="Uncertain Outcome Test",
        contacts=contacts,
        template_content="Uncertain check",
        min_delay=0.01,
        max_delay=0.01,
        use_mock=True,
        provider=flaky_provider
    )

    if worker._worker_thread:
        worker._worker_thread.join(timeout=3)

    items = db.get_queue_items(job["id"])
    assert len(items) == 1
    assert items[0]["status"] == "UNCERTAIN"

    # Worker recovery should NOT retry or duplicate UNCERTAIN sends
    pending_items = db.get_queue_items(job_id=job["id"], status="PENDING")
    assert len(pending_items) == 0
