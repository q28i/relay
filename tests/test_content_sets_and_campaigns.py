import os
import json
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.database import db

client = TestClient(app)


def test_variables_info_endpoint():
    """Verifies that the /api/templates/variables-info endpoint returns all documented variables."""
    res = client.get("/api/templates/variables-info")
    assert res.status_code == 200
    data = res.json()
    assert "variables" in data
    tokens = [v["token"] for v in data["variables"]]
    assert "{name}" in tokens
    assert "{first_name}" in tokens
    assert "{phone}" in tokens
    assert "{group}" in tokens
    assert "{language}" in tokens
    assert "{tier}" in tokens


def test_create_and_manage_text_set():
    """Verifies complete lifecycle of a Text Set: creation, new message creation, toggling, duplication."""
    # 1. Create Text Set
    res = client.post("/api/sets", json={
        "name": "Holiday Promo Series",
        "set_type": "text",
        "description": "Black Friday and Holiday messages",
        "allocation_mode": "balanced"
    })
    assert res.status_code == 201
    set_data = res.json()
    set_id = set_data["id"]
    assert set_data["name"] == "Holiday Promo Series"
    assert set_data["set_type"] == "text"

    # 2. Add new message directly in set
    res2 = client.post(f"/api/sets/{set_id}/new-message", json={
        "title": "Welcome Discount",
        "content": "Hello {name}! Use code HOLIDAY25 for 25% off."
    })
    assert res2.status_code == 200
    s_detail = res2.json()
    assert len(s_detail["items"]) == 1
    item = s_detail["items"][0]
    assert item["title"] == "Welcome Discount"
    assert item["is_included"] == 1
    item_id = item["id"]

    # 3. Add second message
    res3 = client.post(f"/api/sets/{set_id}/new-message", json={
        "title": "VIP Early Access",
        "content": "Exclusive early access for {first_name}! Shop now: https://example.com"
    })
    assert res3.status_code == 200
    s_detail = res3.json()
    assert len(s_detail["items"]) == 2

    # 4. Toggle temporary inclusion (Exclude first message from campaign)
    res4 = client.put(f"/api/sets/{set_id}/items/{item_id}/toggle?is_included=0")
    assert res4.status_code == 200
    updated_items = res4.json()["set"]["items"]
    first_item = next(it for it in updated_items if it["id"] == item_id)
    assert first_item["is_included"] == 0

    # 5. Duplicate set
    res5 = client.post(f"/api/sets/{set_id}/duplicate")
    assert res5.status_code == 200
    dup = res5.json()
    assert "Copy" in dup["name"]
    assert len(dup["items"]) == 2

    # Clean up duplicated set
    client.delete(f"/api/sets/{dup['id']}")


def test_create_and_manage_media_set():
    """Verifies Media Set creation, linking media assets, and toggling inclusion."""
    # Ensure at least 1 media asset exists
    media_list = client.get("/api/media").json()
    if not media_list:
        # Create a tiny test media asset
        sample_path = os.path.join("uploads", "media", "test_asset.png")
        os.makedirs(os.path.dirname(sample_path), exist_ok=True)
        with open(sample_path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4")
        aid = db.add_media_asset(
            title="Test Banner",
            filename="test_asset.png",
            file_path=os.path.abspath(sample_path),
            file_size=20,
            mime_type="image/png",
            asset_type="image"
        )
        media_list = [db.get_media_asset(aid)]

    media_id = media_list[0]["id"]

    # 1. Create Media Set
    res = client.post("/api/sets", json={
        "name": "Social Banners 2026",
        "set_type": "media",
        "description": "Visuals for campaigns",
        "allocation_mode": "balanced"
    })
    assert res.status_code == 201
    set_id = res.json()["id"]

    # 2. Add media asset to set
    res2 = client.post(f"/api/sets/{set_id}/items", json={
        "media_asset_ids": [media_id]
    })
    assert res2.status_code == 200
    s_detail = res2.json()["set"]
    assert len(s_detail["items"]) >= 1
    m_item = s_detail["items"][0]
    assert m_item["media_asset_id"] == media_id
    assert m_item["is_included"] == 1

    # 3. Toggle exclusion
    res3 = client.put(f"/api/sets/{set_id}/items/{m_item['id']}/toggle?is_included=0")
    assert res3.status_code == 200
    assert res3.json()["set"]["items"][0]["is_included"] == 0

    # 4. Toggle back to included
    res4 = client.put(f"/api/sets/{set_id}/items/{m_item['id']}/toggle?is_included=1")
    assert res4.status_code == 200
    assert res4.json()["set"]["items"][0]["is_included"] == 1


def test_import_export_text_set():
    """Verifies importing CSV into a Text Set and exporting to CSV."""
    res = client.post("/api/sets", json={
        "name": "Import Export Test Set",
        "set_type": "text"
    })
    set_id = res.json()["id"]

    csv_data = "Title,Body\nPromo 1,Hello {name}! Buy 1 get 1 free.\nPromo 2,Hey {first_name}! 50% discount today.\n"
    res_import = client.post(
        f"/api/sets/{set_id}/import",
        files={"file": ("promos.csv", csv_data.encode("utf-8"), "text/csv")}
    )
    assert res_import.status_code == 200
    data = res_import.json()
    assert data["imported_count"] == 2
    assert len(data["set"]["items"]) == 2

    # Test CSV Export
    res_export = client.get(f"/api/sets/{set_id}/export?format=csv")
    assert res_export.status_code == 200
    assert "Promo 1" in res_export.text
    assert "Promo 2" in res_export.text


def test_allocation_preview_with_sets():
    """Verifies pre-send allocation preview respects Text Sets, Media Sets, and temporary exclusions."""
    # Create Text Set with 2 items (1 included, 1 excluded)
    res_t = client.post("/api/sets", json={"name": "Alloc Text Set", "set_type": "text"})
    t_set_id = res_t.json()["id"]
    client.post(f"/api/sets/{t_set_id}/new-message", json={"title": "Active Msg", "content": "Hi {name}!"})
    client.post(f"/api/sets/{t_set_id}/new-message", json={"title": "Skipped Msg", "content": "Ignored message"})

    # Exclude second item
    t_set = client.get(f"/api/sets/{t_set_id}").json()
    second_item_id = t_set["items"][1]["id"]
    client.put(f"/api/sets/{t_set_id}/items/{second_item_id}/toggle?is_included=0")

    # Run allocation preview with custom sample contacts
    sample_contacts = [
        {"name": "Alice Green", "phone": "14155551111", "group": "VIP", "consent_status": "opted_in"},
        {"name": "Bob Vance", "phone": "14155552222", "group": "VIP", "consent_status": "opted_in"}
    ]
    res_preview = client.post("/api/campaigns/allocation-preview", json={
        "text_set_id": t_set_id,
        "custom_contacts": sample_contacts,
        "allocation_mode": "balanced"
    })
    assert res_preview.status_code == 200
    pdata = res_preview.json()
    assert len(pdata["allocations"]) == 2

    # Both contacts MUST get the Active Msg because the Skipped Msg is temporarily excluded!
    for alloc in pdata["allocations"]:
        assert "Hi " in alloc["rendered_message"]
        assert "Ignored message" not in alloc["rendered_message"]

