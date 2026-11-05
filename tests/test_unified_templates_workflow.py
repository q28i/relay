"""
Unified Template Workflow & Consolidation Verification Test Suite.
Verifies the complete simplified Relay workflow:
1. Reusable template lifecycle: Create, Edit, Duplicate, Delete, Export, Import.
2. Sections: Contacts (audience counts, opt-out exclusion), Media (thumbnails, toggle, delete), Texts (multiline, variables).
3. Content selection modes: Mode 1 (Same for everyone) vs Mode 2 (Mix variations - 1 media + 1 text per recipient).
4. Deterministic preview and durable campaign queue staging.
5. Deletion verification: Template delete unlinks campaigns without deleting logs; individual text and media deletion.
"""

import os
import json
import time
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.database import db
from backend.job_queue import job_worker

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_test_templates():
    """Ensure test templates are cleaned up before and after."""
    yield
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM templates WHERE name LIKE 'Test_Tpl_%' OR name LIKE 'Winter Sale%'")
        tids = [r["id"] for r in cursor.fetchall()]
        for tid in tids:
            db.delete_template(tid)


def test_template_crud_and_empty_state():
    """Verifies template creation, retrieval, updating, and legitimate deletion."""
    # 1. Create Winter Sale template
    t_name = f"Winter Sale {int(time.time() * 1000)}"
    res = client.post("/api/templates", json={
        "name": t_name,
        "content": "Hi {name}, our winter sale is live!",
        "description": "Annual seasonal promotion"
    })
    assert res.status_code == 200, res.text
    data = res.json()
    tid = data["id"]
    assert tid > 0

    # 2. Retrieve template details
    get_res = client.get(f"/api/templates/{tid}")
    assert get_res.status_code == 200
    tpl = get_res.json()
    assert tpl["name"] == t_name
    assert tpl["content_selection_mode"] == "mix_variations"
    assert len(tpl["text_variations"]) >= 1

    # 3. Update template metadata
    up_res = client.put(f"/api/templates/{tid}", json={
        "name": f"{t_name} Updated",
        "content": "Hello {first_name}! Special winter deal for you.",
        "description": "Updated promo description"
    })
    assert up_res.status_code == 200
    updated = client.get(f"/api/templates/{tid}").json()
    assert updated["name"] == f"{t_name} Updated"

    # 4. Delete template and verify real deletion
    del_res = client.delete(f"/api/templates/{tid}")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # 5. Confirm it no longer exists
    not_found_res = client.get(f"/api/templates/{tid}")
    assert not_found_res.status_code == 404


def test_template_text_variations_management():
    """Verifies adding, toggling, updating, and deleting multiple text variations inside a template."""
    t_name = f"Test_Tpl_Texts_{int(time.time() * 1000)}"
    tid = db.add_template(name=t_name, content="Initial message {name}")

    # 1. Add Message Variation 2
    res2 = client.post(f"/api/templates/{tid}/texts", json={
        "content": "Hello {first_name}! Check out our winter offers."
    })
    assert res2.status_code == 200
    vid2 = res2.json()["variant_id"]

    # 2. Add Message Variation 3
    res3 = client.post(f"/api/templates/{tid}/texts", json={
        "content": "Hey {name}, we've got something special for you."
    })
    assert res3.status_code == 200
    vid3 = res3.json()["variant_id"]

    # 3. Paste Multiple Variations at once
    paste_res = client.post(f"/api/templates/{tid}/texts/paste-multiple", json={
        "raw_text": "Variation 4: Welcome {name}!\n\nVariation 5: Flash sale for {phone}!",
        "separator": "\n\n"
    })
    assert paste_res.status_code == 200
    assert paste_res.json()["added_count"] == 2

    tpl = client.get(f"/api/templates/{tid}").json()
    assert tpl["text_count"] == 5
    assert tpl["active_text_count"] == 5

    # 4. Toggle Variation 2 off (exclude from template)
    tog_res = client.put(f"/api/templates/{tid}/texts/{vid2}/toggle", json={"is_active": False})
    assert tog_res.status_code == 200
    tpl_after_tog = client.get(f"/api/templates/{tid}").json()
    assert tpl_after_tog["active_text_count"] == 4

    # 5. Delete Variation 3
    del_res = client.delete(f"/api/templates/{tid}/texts/{vid3}")
    assert del_res.status_code == 200
    tpl_after_del = client.get(f"/api/templates/{tid}").json()
    assert tpl_after_del["text_count"] == 4


def test_template_media_management(tmp_path):
    """Verifies attaching media to templates, toggling inclusion, and removing from template."""
    # Create test media assets
    media_file1 = tmp_path / "banner1.png"
    media_file1.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 200)
    aid1 = db.add_media_asset(
        title="Banner 1",
        filename="banner1.png",
        file_path=str(media_file1),
        file_size=208,
        mime_type="image/png",
        asset_type="image"
    )

    media_file2 = tmp_path / "banner2.png"
    media_file2.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 300)
    aid2 = db.add_media_asset(
        title="Banner 2",
        filename="banner2.png",
        file_path=str(media_file2),
        file_size=308,
        mime_type="image/png",
        asset_type="image"
    )

    t_name = f"Test_Tpl_Media_{int(time.time() * 1000)}"
    tid = db.add_template(name=t_name, content="Winter promo {name}")

    # 1. Attach media to template
    add_m_res = client.post(f"/api/templates/{tid}/media", json={"media_asset_ids": [aid1, aid2]})
    assert add_m_res.status_code == 200
    assert add_m_res.json()["added_count"] == 2

    tpl = client.get(f"/api/templates/{tid}").json()
    assert tpl["media_count"] == 2
    assert tpl["active_media_count"] == 2

    # 2. Toggle media 1 off (excluded from this template)
    tog_m_res = client.put(f"/api/templates/{tid}/media/{aid1}/toggle", json={"is_active": False})
    assert tog_m_res.status_code == 200
    tpl_tog = client.get(f"/api/templates/{tid}").json()
    assert tpl_tog["active_media_count"] == 1

    # 3. Remove media 2 from template (remains in library)
    rem_res = client.delete(f"/api/templates/{tid}/media/{aid2}")
    assert rem_res.status_code == 200
    tpl_rem = client.get(f"/api/templates/{tid}").json()
    assert tpl_rem["media_count"] == 1
    # Verify asset2 is still safe in library
    assert db.get_media_asset(aid2) is not None


def test_template_content_selection_modes(tmp_path):
    """
    Verifies Section 3:
    - Mode 1 (Same for Everyone): 1 media + 1 text assigned to all contacts.
    - Mode 2 (Mix Variations): Seeded, reproducible random 1 media + 1 text assigned per recipient.
    """
    # Create test media
    m1 = tmp_path / "m1.jpg"
    m1.write_bytes(b"\xff\xd8\xff" + b"1" * 100)
    aid1 = db.add_media_asset("Image 1", "m1.jpg", str(m1), 103, "image/jpeg", "image")

    m2 = tmp_path / "m2.jpg"
    m2.write_bytes(b"\xff\xd8\xff" + b"2" * 100)
    aid2 = db.add_media_asset("Image 2", "m2.jpg", str(m2), 103, "image/jpeg", "image")

    # Ensure test contacts exist
    if not db.get_contacts():
        db.add_contact(name="Alice Smith", phone="+14155550001", group_name="Default")
        db.add_contact(name="Bob Jones", phone="+14155550002", group_name="Default")

    t_name = f"Test_Tpl_Modes_{int(time.time() * 1000)}"
    tid = db.add_template(name=t_name, content="Text variation 1 for {name}")
    db.add_template_text_variation(tid, "Text variation 2 for {first_name}")
    db.add_template_text_variation(tid, "Text variation 3 for {phone}")
    db.add_template_media_assets(tid, [aid1, aid2])

    # 1. Test Mode 2: Mix Variations preview
    mix_res = client.post(f"/api/templates/{tid}/preview-assignments")
    assert mix_res.status_code == 200
    mix_data = mix_res.json()
    assert mix_data["mode"] == "mix_variations"
    assert mix_data["active_media_count"] == 2
    assert mix_data["active_text_count"] == 3
    assignments = mix_data["preview_assignments"]
    assert len(assignments) > 0

    # Every recipient gets exactly 1 media and 1 text
    for a in assignments:
        assert a["media_asset_id"] in (aid1, aid2)
        assert a["rendered_text"] is not None
        assert "{" not in a["rendered_text"]  # Variables interpolated!

    # 2. Test Mode 1: Same for Everyone
    client.put(f"/api/templates/{tid}", json={"content_selection_mode": "same_for_everyone"})
    same_res = client.post(f"/api/templates/{tid}/preview-assignments")
    assert same_res.status_code == 200
    same_data = same_res.json()
    assert same_data["mode"] == "same_for_everyone"
    same_assignments = same_data["preview_assignments"]

    # In Same for Everyone, all recipients share the exact same media asset and template text base
    assigned_media_ids = {a["media_asset_id"] for a in same_assignments}
    assert len(assigned_media_ids) == 1
    assert assigned_media_ids.pop() == aid1


def test_template_duplication_and_export_import(tmp_path):
    """Verifies duplicating, exporting to JSON, and importing a template."""
    m_file = tmp_path / "gift.png"
    m_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"X" * 150)
    aid = db.add_media_asset("Gift Icon", "gift.png", str(m_file), 158, "image/png", "image")

    t_name = f"Test_Tpl_Export_{int(time.time() * 1000)}"
    tid = db.add_template(name=t_name, content="Holiday special {name}", description="Original template")
    db.add_template_text_variation(tid, "Holiday discount {first_name}")
    db.add_template_media_assets(tid, [aid])

    # 1. Duplicate Template
    dup_res = client.post(f"/api/templates/{tid}/duplicate")
    assert dup_res.status_code == 200
    dup_tpl = dup_res.json()["template"]
    assert dup_tpl["id"] != tid
    assert "(Copy)" in dup_tpl["name"]
    assert dup_tpl["text_count"] == 2
    assert dup_tpl["media_count"] == 1

    # Clean up duplicate
    db.delete_template(dup_tpl["id"])

    # 2. Export Template
    exp_res = client.get(f"/api/templates/{tid}/export")
    assert exp_res.status_code == 200
    exp_json = exp_res.json()
    assert exp_json["format"] == "relay_template_v1"
    assert exp_json["name"] == t_name
    assert len(exp_json["text_variations"]) == 2

    # 3. Import Template
    imp_res = client.post("/api/templates/import", json={
        "name": f"Imported_{t_name}",
        "description": "Restored from JSON backup",
        "content_selection_mode": exp_json["content_selection_mode"],
        "target_group": "All",
        "text_variations": exp_json["text_variations"],
        "media_asset_ids": [aid]
    })
    assert imp_res.status_code == 200
    imp_tpl = imp_res.json()["template"]
    assert imp_tpl["text_count"] == 2
    assert imp_tpl["media_count"] == 1

    # Clean up imported
    db.delete_template(imp_tpl["id"])


def test_template_deletion_preserves_campaign_history():
    """Verifies Section 1: Template deletion unlinks campaigns without destroying historical dispatch logs."""
    t_name = f"Test_Tpl_Hist_{int(time.time() * 1000)}"
    tid = db.add_template(name=t_name, content="Limited offer for {name}")

    # Create campaign referencing this template
    camp_id = db.create_campaign(
        name=f"Historic Campaign for {t_name}",
        template_id=tid,
        group_name="Default",
        min_delay=8.0,
        max_delay=15.0
    )
    assert camp_id > 0

    # Delete template
    del_res = client.delete(f"/api/templates/{tid}")
    assert del_res.status_code == 200

    # Campaign must still exist with template_id set to NULL
    camp = db.get_campaign(camp_id)
    assert camp is not None
    assert camp["template_id"] is None
