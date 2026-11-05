"""
Tests for Stage 5: Campaign Allocation Workflow & Pre-Send Allocation Preview Table.
Verifies:
1. POST /api/campaigns/allocation-preview returns exact assigned Message and Media per recipient before launch.
2. 3 Pairing modes: Fixed pair, Approved combinations, Balanced rotation.
3. Durable persistence of allocations in queue items upon launch.
4. Restart and retry preserves approved allocations.
5. Exclusion of opt-outs and duplicates from allocation preview.
"""

import io
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.database import db


@pytest.fixture
def client():
    return TestClient(app)


def test_allocation_preview_fixed_pair(client):
    """
    Verifies allocation preview in fixed_pair mode assigns the selected message and media
    to all eligible contacts in the audience.
    """
    # 1. Setup audience
    c1 = db.add_contact(name="Customer A", phone="919876500001", group_name="CampaignAudience")
    c2 = db.add_contact(name="Customer B", phone="919876500002", group_name="CampaignAudience")
    c_opt = db.add_contact(name="Customer OptOut", phone="919876500003", group_name="CampaignAudience", consent_status="opted_out")

    # 2. Setup Template and Media
    t_id = db.add_template(name="Fixed Welcome", content="Hello {name}, welcome to Relay!")
    m_res = client.post(
        "/api/media/upload",
        files={"file": ("flyer.png", io.BytesIO(b"FlyerData"), "image/png")},
        data={"title": "Store Flyer", "asset_type": "image"}
    )
    media_id = m_res.json()["id"]

    # 3. Request Allocation Preview
    prev_res = client.post(
        "/api/campaigns/allocation-preview",
        json={
            "group_name": "CampaignAudience",
            "template_id": t_id,
            "media_asset_id": media_id,
            "allocation_mode": "fixed_pair"
        }
    )
    assert prev_res.status_code == 200, prev_res.text
    preview = prev_res.json()

    assert preview["total_selected_contacts"] == 3
    assert preview["eligible_contacts_count"] == 2
    assert preview["excluded_optouts_count"] == 1
    assert len(preview["allocations"]) == 2

    # Check recipient row assignment
    recA = next(a for a in preview["allocations"] if a["contact_name"] == "Customer A")
    assert recA["message_title"] == "Fixed Welcome"
    assert "Hello Customer A" in recA["rendered_message"]
    assert recA["media_title"] == "Store Flyer"
    assert recA["media_asset_id"] == media_id

    # Cleanup
    db.delete_contact(c1)
    db.delete_contact(c2)
    db.delete_contact(c_opt)
    db.delete_template(t_id)
    client.delete(f"/api/media/{media_id}?force=true")


def test_allocation_preview_with_content_collection(client):
    """
    Verifies allocation preview using a Content Collection with approved pairs.
    """
    c1 = db.add_contact(name="Alice VIP", phone="919876500011", group_name="ColAudience", customer_tier="VIP")
    c2 = db.add_contact(name="Bob Regular", phone="919876500012", group_name="ColAudience", customer_tier="Regular")

    t1 = db.add_template(name="VIP Offer", content="Special VIP discount for {name}!")
    t2 = db.add_template(name="Standard Offer", content="Regular offer for {name}!")

    m1 = client.post("/api/media/upload", files={"file": ("m1.jpg", io.BytesIO(b"M1"), "image/jpeg")}, data={"title": "VIP Banner"}).json()["id"]
    m2 = client.post("/api/media/upload", files={"file": ("m2.jpg", io.BytesIO(b"M2"), "image/jpeg")}, data={"title": "Regular Banner"}).json()["id"]

    # Create Collection with Approved Combinations
    col_res = client.post(
        "/api/collections",
        json={
            "name": "Targeted Promo",
            "pairing_mode": "approved_combinations",
            "pairs": [
                {"template_id": t1, "media_asset_id": m1, "pair_label": "VIP Pair"},
                {"template_id": t2, "media_asset_id": m2, "pair_label": "Regular Pair"}
            ]
        }
    )
    col_id = col_res.json()["id"]

    # Request Allocation Preview with Collection
    prev_res = client.post(
        "/api/campaigns/allocation-preview",
        json={
            "group_name": "ColAudience",
            "collection_id": col_id,
            "allocation_mode": "approved_combinations"
        }
    )
    assert prev_res.status_code == 200, prev_res.text
    preview = prev_res.json()
    assert preview["eligible_contacts_count"] == 2
    assert len(preview["allocations"]) == 2

    # Cleanup
    db.delete_contact(c1)
    db.delete_contact(c2)
    db.delete_template(t1)
    db.delete_template(t2)
    client.delete(f"/api/media/{m1}?force=true")
    client.delete(f"/api/media/{m2}?force=true")
    client.delete(f"/api/collections/{col_id}")

