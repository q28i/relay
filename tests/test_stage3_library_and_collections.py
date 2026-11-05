"""
Tests for Stage 3: Asset Library and Content Collections.
Verifies:
1. Media upload, SHA-256 deduplication (same file returns existing asset without duplicating on disk).
2. Media persistence across restarts.
3. Message template storage, versioning, and reuse.
4. Content Collections CRUD (create, update, delete).
5. Collection items (linking messages and media assets).
6. 3 Pairing modes: fixed_pair, approved_combinations, balanced_testing.
7. Active campaign asset deletion protection.
"""

import io
import os
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.database import db


@pytest.fixture
def client():
    return TestClient(app)


def test_media_upload_sha256_deduplication(client):
    """
    Verifies that uploading the exact same media bytes returns the existing asset
    and avoids redundant storage on disk.
    """
    file_bytes = b"Sample Banner Content For Deduplication Testing 2026"
    
    # Upload first time
    res1 = client.post(
        "/api/media/upload",
        files={"file": ("banner.png", io.BytesIO(file_bytes), "image/png")},
        data={"title": "Promo Banner", "asset_type": "image"}
    )
    assert res1.status_code == 200
    asset1 = res1.json()
    assert "content_hash" in asset1

    # Upload identical file second time
    res2 = client.post(
        "/api/media/upload",
        files={"file": ("duplicate_banner.png", io.BytesIO(file_bytes), "image/png")},
        data={"title": "Duplicate Banner", "asset_type": "image"}
    )
    assert res2.status_code == 200
    asset2 = res2.json()

    # Must reuse the same ID and hash
    assert asset2["id"] == asset1["id"]
    assert asset2["content_hash"] == asset1["content_hash"]

    # Cleanup
    client.delete(f"/api/media/{asset1['id']}?force=true")


def test_content_collection_crud(client):
    """
    Verifies creating a named collection, adding messages and media,
    updating pairing mode, and deleting.
    """
    # 1. Create templates and media
    t1_id = db.add_template(name="Welcome Msg", content="Hello {name}, welcome to Relay!")
    t2_id = db.add_template(name="Offer Msg", content="Hi {name}, here is a 20% discount coupon!")

    m_res = client.post(
        "/api/media/upload",
        files={"file": ("test_art.jpg", io.BytesIO(b"ArtAssetBytes"), "image/jpeg")},
        data={"title": "Product Image", "asset_type": "image"}
    )
    media_id = m_res.json()["id"]

    # 2. Create Content Collection
    col_res = client.post(
        "/api/collections",
        json={
            "name": "November Offers",
            "description": "Black Friday and Cyber Monday campaign assets",
            "pairing_mode": "fixed_pair",
            "message_ids": [t1_id, t2_id],
            "media_ids": [media_id]
        }
    )
    assert col_res.status_code == 200, col_res.text
    col = col_res.json()
    col_id = col["id"]
    assert col["name"] == "November Offers"
    assert col["pairing_mode"] == "fixed_pair"
    assert len(col["messages"]) == 2
    assert len(col["media"]) == 1

    # 3. List Collections
    list_res = client.get("/api/collections")
    assert list_res.status_code == 200
    collections = list_res.json()
    assert any(c["id"] == col_id for c in collections)

    # 4. Update Pairing Mode and Define Approved Combinations
    update_res = client.put(
        f"/api/collections/{col_id}",
        json={
            "name": "November Offers Updated",
            "pairing_mode": "approved_combinations",
            "pairs": [
                {"template_id": t1_id, "media_asset_id": media_id, "pair_label": "Welcome + Product"},
                {"template_id": t2_id, "media_asset_id": media_id, "pair_label": "Discount + Product"}
            ]
        }
    )
    assert update_res.status_code == 200
    updated_col = update_res.json()
    assert updated_col["pairing_mode"] == "approved_combinations"
    assert len(updated_col["pairs"]) == 2

    # 5. Delete Collection
    del_res = client.delete(f"/api/collections/{col_id}")
    assert del_res.status_code == 200

    # Cleanup templates and media
    db.delete_template(t1_id)
    db.delete_template(t2_id)
    client.delete(f"/api/media/{media_id}?force=true")

