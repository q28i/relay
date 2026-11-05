"""
Comprehensive Automated Test Suite for WhatsApp Automation Web Dashboard API.
Tests REST endpoints, contact CRUD, column mapping, Spintax tester,
campaign pre-flight validation, mock job dispatches, and configuration presets.
"""

import os
import pytest
import sqlite3
from fastapi.testclient import TestClient

from backend.app import app
from backend.database import db

client = TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def clean_test_database_artifacts():
    """Ensure test runs never leave test artifacts in the database."""
    def cleanup():
        try:
            conn = sqlite3.connect('whatsapp_web.db')
            c = conn.cursor()
            c.execute("DELETE FROM contact_groups WHERE name LIKE 'Test Partner Group%' OR name = 'Hi lol'")
            c.execute("DELETE FROM templates WHERE name LIKE 'Updated Title%' OR name LIKE 'Seasonal Discount%' OR name LIKE 'Template to Edit%' OR name LIKE 'Updated Template%' OR name LIKE 'Friendly Welcome%' OR name LIKE 'Promo Campaign%' OR name LIKE 'Temporary Template%'")
            c.execute("DELETE FROM message_variants WHERE template_id NOT IN (SELECT id FROM templates)")
            c.execute("DELETE FROM jobs WHERE campaign_name LIKE 'API Automated Test%' OR campaign_name LIKE 'Scheduled%'")
            c.execute("DELETE FROM job_results WHERE job_id NOT IN (SELECT id FROM jobs)")
            c.execute("DELETE FROM campaign_queue_items WHERE job_id NOT IN (SELECT id FROM jobs)")
            c.execute("DELETE FROM contacts WHERE name LIKE 'Bruce Wayne%' OR name LIKE 'Consent Test%'")
            c.execute("DELETE FROM suppression_list WHERE reason LIKE '%GDPR%' OR source = 'dashboard_operator' OR source = 'web_opt_out_portal'")
            conn.commit()
            conn.close()
        except Exception:
            pass

    yield
    cleanup()


class TestHealthAndStaticRoutes:
    """Verifies system health check and static SPA file serving."""

    def test_health_check(self):
        res = client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert data["version"] == "2.0.0"

    def test_serve_dashboard_index(self):
        res = client.get("/")
        assert res.status_code == 200
        assert "<title>Relay" in res.text

    def test_serve_favicon(self):
        res = client.get("/favicon.ico")
        assert res.status_code == 200
        assert "image/svg+xml" in res.headers.get("content-type", "")

    def test_serve_static_styles(self):
        res = client.get("/static/styles.css")
        assert res.status_code == 200
        assert "--primary:" in res.text

    def test_serve_static_js(self):
        res = client.get("/static/app.js")
        assert res.status_code == 200
        assert "class WhatsAppDashboardApp" in res.text


class TestContactsEndpoints:
    """Verifies contact ingestion, validation, normalization, and group management."""

    def test_create_and_get_contact_group(self):
        import uuid
        gname = f"Test Partner Group {uuid.uuid4().hex[:6]}"
        res = client.post("/api/contacts/groups", json={
            "name": gname,
            "description": "API Integration Test Audience"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == gname

        # Verify group listing
        list_res = client.get("/api/contacts/groups")
        assert list_res.status_code == 200
        groups = list_res.json()
        names = [g["name"] for g in groups]
        assert gname in names

    def test_add_single_contact(self):
        res = client.post("/api/contacts", json={
            "name": "Bruce Wayne",
            "phone": "+1 (415) 555-2671",
            "group_name": "Test Partner Group",
            "custom_fields": {"company": "Wayne Enterprises"}
        })
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "Bruce Wayne"
        assert data["phone"] == "14155552671"
        assert data["group_name"] == "Test Partner Group"

    def test_reject_invalid_phone_number(self):
        res = client.post("/api/contacts", json={
            "name": "Invalid Recipient",
            "phone": "not-a-number",
            "group_name": "Default"
        })
        assert res.status_code == 400
        assert "Invalid phone number format" in res.json()["detail"]

    def test_list_contacts_with_search_and_filter(self):
        res = client.get("/api/contacts?group=Test Partner Group&search=Bruce")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] >= 1
        assert any(c["name"] == "Bruce Wayne" for c in data["items"])

    def test_phone_cleaner_endpoint(self):
        res = client.post("/api/contacts/clean", json={
            "raw_phones": ["09876-543-210", "+1 (415) 555-2671", "invalid_str"],
            "default_country_code": "91"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["total_input"] == 3
        assert data["valid_count"] == 2
        assert data["invalid_count"] == 1

    def test_export_contacts_csv(self):
        res = client.get("/api/contacts/export?group=Test Partner Group")
        assert res.status_code == 200
        assert "text/csv" in res.headers["content-type"]
        assert "Bruce Wayne" in res.text


class TestTemplatesEndpoints:
    """Verifies template creation, variable auto-extraction, Spintax tester, and CRUD."""

    def test_create_template_with_variable_extraction(self):
        import uuid
        tname = f"Seasonal Discount {uuid.uuid4().hex[:6]}"
        res = client.post("/api/templates", json={
            "name": tname,
            "content": "{Hi|Hello} {name}, get 30% off your next order with code {promo_code}!"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == tname
        assert "name" in data["variables"]
        assert "promo_code" in data["variables"]

    def test_spintax_test_endpoint(self):
        res = client.post("/api/templates/spintax-test", json={
            "text": "{Good morning|Greetings|Hello} {name}!",
            "sample_count": 5
        })
        assert res.status_code == 200
        data = res.json()
        assert len(data["variations"]) == 5
        for var in data["variations"]:
            assert any(greet in var for greet in ["Good morning", "Greetings", "Hello"])
            assert "{name}" in var

    def test_update_template(self):
        import uuid
        init_name = f"Template to Edit {uuid.uuid4().hex[:6]}"
        updated_name = f"Updated Title {uuid.uuid4().hex[:6]}"
        create_res = client.post("/api/templates", json={
            "name": init_name,
            "content": "Initial body {name}"
        })
        tid = create_res.json()["id"]

        # Update it
        update_res = client.put(f"/api/templates/{tid}", json={
            "name": updated_name,
            "content": "Updated body {name} at {company}"
        })
        assert update_res.status_code == 200
        data = update_res.json()
        assert data["name"] == updated_name
        assert "company" in data["variables"]

    def test_delete_template(self):
        import uuid
        temp_name = f"Temporary Template {uuid.uuid4().hex[:6]}"
        create_res = client.post("/api/templates", json={
            "name": temp_name,
            "content": "Delete me soon"
        })
        tid = create_res.json()["id"]

        del_res = client.delete(f"/api/templates/{tid}")
        assert del_res.status_code == 200
        assert del_res.json()["success"] is True

        get_res = client.get(f"/api/templates/{tid}")
        assert get_res.status_code == 404


class TestCampaignsAndJobQueue:
    """Verifies pre-flight audit, dry-run simulation, and mock background job execution."""

    def test_validate_campaign_preflight(self):
        res = client.post("/api/campaigns/validate", json={
            "custom_contacts": [
                {"name": "Alice", "phone": "919876543210"},
                {"name": "Bob", "phone": "919876543211"},
                {"name": "Alice Duplicate", "phone": "919876543210"}
            ],
            "template_content": "Hello {name}, your reminder is scheduled.",
            "min_delay": 8.0,
            "max_delay": 15.0,
            "batch_size": 20,
            "batch_pause": 60.0,
            "daily_cap": 100
        })
        assert res.status_code == 200
        data = res.json()
        assert data["total_contacts"] == 3
        assert data["duplicate_count"] == 1
        assert data["valid_contacts"] == 3
        assert data["estimated_duration_minutes"] > 0

    def test_dry_run_simulation(self):
        res = client.post("/api/campaigns/dry-run", json={
            "custom_contacts": [
                {"name": "Peter Parker", "phone": "14155552671"},
                {"name": "Clark Kent", "phone": "14155552672"}
            ],
            "template_content": "{Hi|Greetings} {name}, this is a test.",
            "min_delay": 8.0,
            "max_delay": 15.0,
            "deduplicate": True
        })
        assert res.status_code == 200
        data = res.json()
        assert data["total_simulated"] == 2
        for r in data["results"]:
            assert "name" in r
            assert "simulated_delay_s" in r

    def test_launch_mock_campaign_and_monitor(self):
        from backend.job_queue import job_worker
        job_worker._active_job = None
        res = client.post("/api/campaigns/launch", json={
            "campaign_name": "API Automated Test Campaign",
            "custom_contacts": [
                {"name": "Test Contact 1", "phone": "919876543210"},
                {"name": "Test Contact 2", "phone": "919876543211"}
            ],
            "template_content": "Hello {name}, automated test message.",
            "min_delay": 1.0,
            "max_delay": 2.0,
            "use_mock": True
        })
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        job_id = data["job_id"]
        assert job_id

        # Verify job details retrieval
        job_res = client.get(f"/api/jobs/{job_id}")
        assert job_res.status_code == 200
        job_data = job_res.json()
        assert job_data["campaign_name"] == "API Automated Test Campaign"
        assert job_data["status"] in ("QUEUED", "RUNNING", "COMPLETED")

        # Verify CSV export for job
        csv_res = client.get(f"/api/jobs/{job_id}/export")
        assert csv_res.status_code == 200
        assert "text/csv" in csv_res.headers["content-type"]


class TestConfigAndBrowserRoutes:
    """Verifies configuration bounds enforcement, presets, and browser diagnostics."""

    def test_get_and_apply_preset(self):
        # Apply safe preset
        res = client.post("/api/config/preset", json={"preset_name": "safe"})
        assert res.status_code == 200
        data = res.json()
        assert data["applied_preset"] == "safe"
        assert data["preset_details"]["min_delay"] == 12.0

        # Verify config reflects safe preset
        cfg_res = client.get("/api/config")
        assert cfg_res.status_code == 200
        cfg = cfg_res.json()["config"]
        assert cfg["min_delay"] == 12.0
        assert cfg["active_preset"] == "safe"

    def test_reject_invalid_config_bounds(self):
        # max_delay less than min_delay should be rejected
        res = client.put("/api/config", json={
            "min_delay": 20.0,
            "max_delay": 5.0
        })
        assert res.status_code == 422

    def test_system_hardware_info(self):
        res = client.get("/api/config/system-info")
        assert res.status_code == 200
        data = res.json()
        assert "device_id" in data
        assert "system" in data
        assert "machine" in data

    def test_browser_status_check(self):
        res = client.get("/api/browser/status")
        assert res.status_code == 200
        data = res.json()
        assert "active" in data
        assert "logged_in" in data

    def test_list_installed_browsers_and_profiles(self):
        res = client.get("/api/browser/browsers")
        assert res.status_code == 200
        data = res.json()
        assert "browsers" in data
        browser_keys = [b["key"] for b in data["browsers"]]
        assert "chrome" in browser_keys
        assert "edge" in browser_keys
        assert "brave" in browser_keys
        assert "firefox" in browser_keys

        prof_res = client.get("/api/browser/profiles?browser=chrome")
        assert prof_res.status_code == 200
        pdata = prof_res.json()
        assert "profiles" in pdata
        assert any(p["dir"] == "__dedicated__" for p in pdata["profiles"])

    def test_select_profile_requires_owner_confirmation(self):
        # Must fail without confirmation
        res = client.post("/api/browser/select", json={
            "browser": "chrome",
            "profile_dir": "__dedicated__",
            "profile_name": "Dedicated WhatsApp Session",
            "owner_confirmed": False
        })
        assert res.status_code == 400
        assert "Account owner confirmation is required" in res.json()["detail"]

        # Succeeds with confirmation
        res_ok = client.post("/api/browser/select", json={
            "browser": "chrome",
            "profile_dir": "__dedicated__",
            "profile_name": "Dedicated WhatsApp Session",
            "owner_confirmed": True
        })
        assert res_ok.status_code == 200
        data = res_ok.json()
        assert data["success"] is True
        assert data["connection"]["profile_dir"] == "__dedicated__"
        assert data["connection"]["status"] == "Not checked"

        # Check GET /api/browser/connection
        conn_res = client.get("/api/browser/connection")
        assert conn_res.status_code == 200
        cdata = conn_res.json()
        assert cdata["profile_dir"] == "__dedicated__"
        assert cdata["status"] in ("Not checked", "Active in Relay")

    def test_browser_disconnect(self):
        res = client.post("/api/browser/disconnect")
        assert res.status_code == 200
        assert res.json()["success"] is True

    def test_browser_profile_route_aliases_and_robustness(self):
        """Ensures all browser profile endpoints, aliases, and HTTP methods prevent 404 errors."""
        # 1. Root /api/browser endpoint
        root_res = client.get("/api/browser")
        assert root_res.status_code == 200
        assert "browsers" in root_res.json()

        # 2. Standard contract /api/browser-profiles
        profs_res = client.get("/api/browser-profiles")
        assert profs_res.status_code == 200
        pdata = profs_res.json()
        assert "browsers" in pdata
        assert "total_browsers" in pdata
        assert any(b["key"] == "chrome" for b in pdata["browsers"])

        # 3. Standard contract /api/browser-profile/selection
        sel_get = client.get("/api/browser-profile/selection")
        assert sel_get.status_code == 200
        assert "profile_dir" in sel_get.json()
        assert "is_selected" in sel_get.json()

        # 4. Standard contract PUT /api/browser-profile/selection
        put_sel = client.put("/api/browser-profile/selection", json={
            "browser": "chrome",
            "profile_dir": "__dedicated__",
            "profile_name": "Dedicated WhatsApp Session",
            "owner_confirmed": True
        })
        assert put_sel.status_code == 200
        assert put_sel.json()["success"] is True

        # 5. Standard contract POST /api/browser-profile/dedicated
        ded_res = client.post("/api/browser-profile/dedicated")
        assert ded_res.status_code == 200
        assert ded_res.json()["selection"]["profile_dir"] == "__dedicated__"

        # 6. Standard contract POST /api/browser-profile/test
        test_post = client.post("/api/browser-profile/test")
        assert test_post.status_code == 200
        assert "status" in test_post.json()

        # 7. Singular alias /api/browser/profile
        prof_singular = client.get("/api/browser/profile?browser=chrome")
        assert prof_singular.status_code == 200
        assert "profiles" in prof_singular.json()

        # 8. Alias /api/browser/profile/select
        sel_alias = client.post("/api/browser/profile/select", json={
            "browser": "chrome",
            "profile_dir": "__dedicated__",
            "profile_name": "Dedicated WhatsApp Session",
            "owner_confirmed": True
        })
        assert sel_alias.status_code == 200
        assert sel_alias.json()["success"] is True

        # 9. Session status alias /api/browser/session
        sess_res = client.get("/api/browser/session")
        assert sess_res.status_code == 200
        assert "status" in sess_res.json()

        # 10. GET /api/browser/test in addition to POST
        test_get_res = client.get("/api/browser/test")
        assert test_get_res.status_code == 200
        assert "status" in test_get_res.json()

    def test_browser_profile_structured_errors(self):
        """Verifies structured errors for missing confirmation, missing browser, and invalid profile."""
        # 1. Missing confirmation
        res1 = client.put("/api/browser-profile/selection", json={
            "browser": "chrome",
            "profile_dir": "__dedicated__",
            "profile_name": "Dedicated WhatsApp Session",
            "owner_confirmed": False
        })
        assert res1.status_code == 400
        d1 = res1.json()
        assert d1.get("code") == "CONFIRMATION_REQUIRED"
        assert "confirmation is required" in d1.get("message", "").lower()
        assert "action" in d1

        # 2. Unsupported browser
        res2 = client.put("/api/browser-profile/selection", json={
            "browser": "safari_nonexistent",
            "profile_dir": "__dedicated__",
            "profile_name": "Safari Test",
            "owner_confirmed": True
        })
        assert res2.status_code == 400
        d2 = res2.json()
        assert d2.get("code") == "BROWSER_NOT_SUPPORTED"

        # 3. Non-existent profile
        res3 = client.put("/api/browser-profile/selection", json={
            "browser": "chrome",
            "profile_dir": "TotallyFakeProfile12345",
            "profile_name": "Fake Profile",
            "owner_confirmed": True
        })
        assert res3.status_code == 400
        d3 = res3.json()
        assert d3.get("code") == "PROFILE_NOT_FOUND"
        assert "action" in d3

    def test_browser_profiles_empty_fallback(self, monkeypatch):
        """Verifies that if no browsers are detected, the endpoint returns a helpful message instead of 404."""
        from browser_manager import BrowserManager
        monkeypatch.setattr(BrowserManager, "get_installed_browsers", classmethod(lambda cls: {}))

        res = client.get("/api/browser-profiles")
        assert res.status_code == 200
        data = res.json()
        assert data["browsers"] == []
        assert data["total_browsers"] == 0
        assert "No browser profiles were found" in data["message"]

    def test_test_send_validation(self):
        # Invalid phone format
        bad_res = client.post("/api/browser/test-send", json={
            "phone": "invalid",
            "message": "Hello test"
        })
        assert bad_res.status_code == 400

        # Empty message
        empty_res = client.post("/api/browser/test-send", json={
            "phone": "+14155552671",
            "message": "   "
        })
        assert empty_res.status_code == 400


class TestConsentAndSuppression:
    """Verifies consent status tracking and global suppression list enforcement."""

    def test_update_contact_consent(self):
        # Create a contact
        res = client.post("/api/contacts", json={
            "name": "Consent Test Subject",
            "phone": "+1 415 555 8899",
            "group_name": "Default",
            "consent_status": "opted_in",
            "consent_source": "checkout_form"
        })
        assert res.status_code == 200
        cid = res.json()["id"]

        # Update consent to opted_out
        up_res = client.put(f"/api/contacts/{cid}/consent", json={
            "consent_status": "opted_out",
            "opt_out_reason": "Requested via SMS STOP reply"
        })
        assert up_res.status_code == 200
        assert up_res.json()["consent_status"] == "opted_out"
        assert up_res.json()["opt_out_reason"] == "Requested via SMS STOP reply"

    def test_suppression_list_crud(self):
        test_phone = "+1 415 555 9900"
        # Add to suppression list
        add_res = client.post("/api/contacts/suppression", json={
            "phone": test_phone,
            "reason": "customer_unsubscribed",
            "source": "web_opt_out_portal"
        })
        assert add_res.status_code == 200
        assert add_res.json()["phone"] == "14155559900"

        # List suppression items
        list_res = client.get("/api/contacts/suppression?search=14155559900")
        assert list_res.status_code == 200
        data = list_res.json()
        assert data["total"] >= 1
        item = [i for i in data["items"] if i["phone"] == "14155559900"][0]
        supp_id = item["id"]

        # Delete suppression entry
        del_res = client.delete(f"/api/contacts/suppression/{supp_id}")
        assert del_res.status_code == 200
        assert del_res.json()["success"] is True


class TestMediaAssets:
    """Verifies media asset uploading, listing, and inspection."""

    def test_upload_and_inspect_media_asset(self):
        import io
        fake_png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        files = {
            "file": ("test_banner.png", io.BytesIO(fake_png_data), "image/png")
        }
        data = {
            "title": "Welcome Promo Banner",
            "asset_type": "banner"
        }
        up_res = client.post("/api/media/upload", files=files, data=data)
        assert up_res.status_code == 200
        asset = up_res.json()
        assert asset["title"] == "Welcome Promo Banner"
        assert asset["asset_type"] == "banner"
        assert asset["mime_type"] == "image/png"
        asset_id = asset["id"]

        # List assets
        list_res = client.get("/api/media")
        assert list_res.status_code == 200
        assets = list_res.json()
        assert any(a["id"] == asset_id for a in assets)

        # Retrieve single asset
        get_res = client.get(f"/api/media/{asset_id}")
        assert get_res.status_code == 200
        assert get_res.json()["title"] == "Welcome Promo Banner"

        # Cleanup
        del_res = client.delete(f"/api/media/{asset_id}")
        assert del_res.status_code == 200
        assert del_res.json()["success"] is True


class TestMessageVariantsAndPreviewResolve:
    """Verifies legitimate purpose-driven variants and transparent recipient preview resolution."""

    def test_variants_crud_and_preview_resolve(self):
        import uuid
        tname = f"Promo Campaign {uuid.uuid4().hex[:6]}"
        t_res = client.post("/api/templates", json={
            "name": tname,
            "content": "Hello {name}, thank you for your order!"
        })
        assert t_res.status_code == 200
        tid = t_res.json()["id"]

        # Add a Spanish language variant
        v_res = client.post(f"/api/templates/{tid}/variants", json={
            "template_id": tid,
            "variant_name": "Spanish Order Confirmation",
            "purpose": "Language localization for Spanish-speaking customers",
            "audience_filter_field": "language",
            "audience_filter_value": "es",
            "content": "Hola {name}, gracias por su compra!",
            "approval_status": "approved"
        })
        assert v_res.status_code == 200
        variant = v_res.json()
        assert variant["variant_name"] == "Spanish Order Confirmation"
        vid = variant["id"]

        # Resolve preview for an English recipient (matches Primary/Default)
        prev_en = client.post("/api/templates/preview-resolve", json={
            "template_id": tid,
            "contact_data": {"name": "John Doe", "language": "en"}
        })
        assert prev_en.status_code == 200
        res_en = prev_en.json()
        assert "Hello John Doe" in res_en["rendered_content"]

        # Resolve preview for a Spanish recipient (matches Spanish variant)
        prev_es = client.post("/api/templates/preview-resolve", json={
            "template_id": tid,
            "contact_data": {"name": "Mateo Rossi", "language": "es"}
        })
        assert prev_es.status_code == 200
        res_es = prev_es.json()
        assert res_es["resolved_variant_id"] == vid
        assert "Hola Mateo Rossi" in res_es["rendered_content"]
        assert "Explicit match" in res_es["eligibility_reason"]

        # Delete variant
        del_v = client.delete(f"/api/templates/variants/{vid}")
        assert del_v.status_code == 200

        # Delete template
        del_t = client.delete(f"/api/templates/{tid}")
        assert del_t.status_code == 200


class TestCampaignReviewAndQueue:
    """Verifies 5-stage campaign review audit and queue status endpoint."""

    def test_campaign_review_audit(self):
        res = client.post("/api/campaigns/review", json={
            "custom_contacts": [
                {"name": "Valid Recipient", "phone": "14155550001", "consent_status": "opted_in"},
                {"name": "Opted Out Recipient", "phone": "14155550002", "consent_status": "opted_out"}
            ],
            "template_content": "Notice for {name}",
            "min_delay": 8.0,
            "max_delay": 15.0,
            "batch_size": 20,
            "batch_pause": 60.0,
            "daily_cap": 100
        })
        assert res.status_code == 200
        data = res.json()
        assert data["total_contacts"] == 2
        assert data["eligible_contacts"] == 1
        assert data["suppressed_count"] == 1
        assert data["consent_breakdown"]["opted_in"] == 1
        assert data["consent_breakdown"]["opted_out"] == 1

    def test_campaign_scheduling(self):
        """Verifies scheduling a campaign into the future creates a SCHEDULED job with cancellation support."""
        from datetime import datetime, timedelta
        from backend.job_queue import job_worker
        job_worker.cancel_job(job_worker._active_job.get("id")) if job_worker._active_job else None

        future_time = (datetime.now() + timedelta(hours=2)).isoformat()
        res = client.post("/api/campaigns/launch", json={
            "campaign_name": "Scheduled Black Friday Reminder",
            "custom_contacts": [
                {"name": "Early Bird", "phone": "14155551234"}
            ],
            "template_content": "Don't miss out, {first_name}!",
            "scheduled_at": future_time,
            "use_mock": True
        })
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SCHEDULED"
        job_id = data["job_id"]

        # Cancel the scheduled job cleanly
        cancel_res = client.post(f"/api/jobs/{job_id}/action", json={"action": "cancel"})
        assert cancel_res.status_code == 200

    def test_template_variable_fallback_rendering(self):
        """Verifies smart variable fallback {name|Customer}, {first_name}, and custom fallbacks."""
        prev = client.post("/api/templates/preview-resolve", json={
            "contact_data": {"name": "Clark Kent"},
            "fallback_content": "Hello {first_name}, your organization {company|Daily Planet} is ready."
        })
        assert prev.status_code == 200
        data = prev.json()
        assert "Hello Clark" in data["rendered_content"]
        assert "Daily Planet" in data["rendered_content"]

        # Blank name fallback
        prev2 = client.post("/api/templates/preview-resolve", json={
            "contact_data": {"name": ""},
            "fallback_content": "Dear {name}, thank you!"
        })
        assert prev2.status_code == 200
        assert "Dear Customer" in prev2.json()["rendered_content"]

    def test_cross_channel_suppression_sync(self):
        """Verifies setting contact consent to opted_out syncs to global suppression list."""
        c_res = client.post("/api/contacts", json={
            "name": "Sync Test Subject",
            "phone": "+1 415 555 7711",
            "group_name": "Default",
            "consent_status": "opted_in"
        })
        assert c_res.status_code == 200
        cid = c_res.json()["id"]

        # Switch to opted_out
        up_res = client.put(f"/api/contacts/{cid}/consent", json={
            "consent_status": "opted_out",
            "opt_out_reason": "Requested opt-out"
        })
        assert up_res.status_code == 200
        assert db.is_phone_suppressed("14155557711") is True

        # Switch back to opted_in
        up_res2 = client.put(f"/api/contacts/{cid}/consent", json={
            "consent_status": "opted_in"
        })
        assert up_res2.status_code == 200
        assert db.is_phone_suppressed("14155557711") is False

        # Cleanup
        client.delete(f"/api/contacts/{cid}")

    def test_activity_logs_export_csv(self):
        res = client.get("/api/logs/export")
        assert res.status_code == 200
        assert "text/csv" in res.headers["content-type"]
        assert "Timestamp,Level,Module,Message" in res.text

    def test_config_backup_and_restore(self):
        # 1. Download backup
        backup_res = client.get("/api/config/backup")
        assert backup_res.status_code == 200
        assert "application/json" in backup_res.headers["content-type"]
        data = backup_res.json()
        assert "config" in data
        assert "templates" in data
        assert "groups" in data

        # 2. Restore backup
        import io
        import json
        backup_bytes = io.BytesIO(json.dumps(data).encode("utf-8"))
        restore_res = client.post(
            "/api/config/restore",
            files={"file": ("test_backup.json", backup_bytes, "application/json")}
        )
        assert restore_res.status_code == 200
        assert restore_res.json()["success"] is True

    def test_job_retry_failed_recipients(self):
        import uuid
        import time
        from backend.job_queue import job_worker
        job_worker._active_job = None

        camp_name = f"Failed Retry Test {uuid.uuid4().hex[:6]}"
        p1 = f"1415{uuid.uuid4().int % 10000000:07d}"
        p2 = f"1415{uuid.uuid4().int % 10000000:07d}"

        launch_res = client.post("/api/campaigns/launch", json={
            "campaign_name": camp_name,
            "custom_contacts": [
                {"name": "Alice Green", "phone": p1},
                {"name": "Bob Brown", "phone": p2}
            ],
            "template_content": "Hello {name}",
            "use_mock": True
        })
        assert launch_res.status_code == 200
        job_id = launch_res.json()["job_id"]

        # Wait for initial mock job to conclude
        for _ in range(40):
            if not job_worker._active_job or job_worker._active_job.get("status") not in ("QUEUED", "RUNNING"):
                break
            time.sleep(0.05)
        time.sleep(0.1)

        # Simulate a failed queue item in DB
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE campaign_queue_items
                SET status = 'FAILED', error_message = 'Simulated timeout error'
                WHERE job_id = ?
            """, (job_id,))
            conn.commit()

        # Call retry endpoint
        retry_res = client.post(f"/api/jobs/{job_id}/retry-failed")
        assert retry_res.status_code == 200
        retry_data = retry_res.json()
        assert retry_data["success"] is True
        assert retry_data["retried_count"] >= 1
        assert "new_job_id" in retry_data
