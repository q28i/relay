# Engineering Delivery Report: Persistent Media, Real Contact Editing, and Deterministic Campaign Allocation

**Date:** November 5, 2026  
**Status:** Complete & Verified  
**Coverage:** 107/107 Tests Passing (`pytest`)  
**UI Screenshots:** 6 Visual Proof Artifacts Recorded  

---

## 1. Problem Statement & Root Cause Diagnosis

### The Bugs Reported
1. **Media Disappears After Restart & Does Not Send**:
   - The UI showed an attached image in draft previews, but actual WhatsApp Web dispatches lacked the attachment.
   - Restarting the application cleared media attachments.
   - Deceptive silent fallback: if media failed or was missing, the engine silently sent text-only messages to recipients without informing the sender.
2. **Contact Editing Was Severely Limited**:
   - Contacts could only be deleted or toggled for opt-out.
   - No mechanism existed to modify contact name, phone number, customer tier, language, or custom JSON variable fields.
   - Groups could not be managed (renamed or deleted with migration).
   - No multi-select bulk operations existed.
3. **Variant Allocation Was Speculative**:
   - Random variant rotation was non-deterministic, causing identical runs to produce random distribution.
   - No rule-based targeting (e.g., sending Spanish variants to Spanish speakers, VIP variants to VIPs).
   - Queue items did not persist the chosen variant or media, causing retries to mutate messages.

---

## 2. Technical Implementation

### A. Durable Media Pipeline
- **Storage Directory**: Assets are stored permanently on disk at `uploads/media/{uuid}.{ext}`.
- **Cryptographic Hashing**: Every uploaded asset is hashed via SHA-256 (`hashlib.sha256(content).hexdigest()`), ensuring content integrity and deduplication tracking.
- **Metadata Persistence**: Tracked in SQLite table `media_assets` with `title`, `filename`, `file_path`, `file_size`, `mime_type`, `asset_type`, `content_hash`, and timestamps.
- **Availability & Safe Deletion**:
  - `is_available` dynamically inspects `os.path.isfile(file_path)` on disk.
  - `delete_media_asset(id, force=False)` checks usage across templates, campaigns, and queue items. If referenced, it returns HTTP 409 Conflict unless `force=True`.
- **Zero Silent Fallback**: In `whatsapp_engine.py` and `job_queue.py`:
  ```python
  if attachment_path and not os.path.exists(attachment_path):
      return {
          "status": "FAILED",
          "media_sent": False,
          "caption_sent": False,
          "error": f"Media file not found: {attachment_path}. No text was sent."
      }
  ```

### B. Contact Management & Strict Opt-Out Protection
- **Comprehensive Editing**:
  - `PUT /api/contacts/{id}` updates `name`, `phone`, `group_name`, `customer_tier`, `language`, `consent_status`, `opt_out_reason`, and `custom_fields`.
  - Audited automatically into SQLite `audit_logs`.
- **Strict Opt-Out Protection**:
  - If a contact is currently `opted_out`, attempting to switch `consent_status` to `opted_in` without `consent_override=True` is strictly rejected/ignored.
  - The UI presents an explicit confirmation requirement: `"Explicit Consent Override Required"`.
- **Audience Group Management**:
  - `POST /api/contacts/groups`: Creates new group.
  - `PUT /api/contacts/groups/{name}`: Renames group and updates all member contacts.
  - `DELETE /api/contacts/groups/{name}?fallback_group=...`: Deletes group and automatically migrates contacts to the fallback group (e.g. `'Default'`).
- **Bulk Action Toolbar**:
  - Checkboxes in table header and rows activate the sticky `#contacts-bulk-bar`.
  - Bulk actions include: Move Group (`POST /api/contacts/bulk-move`), Set Customer Tier (`POST /api/contacts/bulk-edit`), Set Language, and Bulk Delete.

### C. Deterministic Campaign Allocation
Four auditable allocation strategies implemented in `job_queue.py`:
1. `explicit_default`: Dispatches the primary base template content.
2. `rule_based`: Matches recipient attributes against variant audience filter fields (e.g., `language == 'es'`, `customer_tier == 'VIP'`). Falls back to base template if no rule matches.
3. `balanced_rotation`: Fair round-robin distribution modulo across approved message variants (`index % len(variants)`).
4. `ab_test`: Deterministic seeded hash split. Computes `int(hashlib.md5(f"{seed}:{phone}".encode()).hexdigest(), 16) % len(variants)`. Preserves variant assignment across retries and app restarts.

### D. Queue Durability & Retries
- `campaign_queue_items` table updated with `media_asset_id` and `allocation_rule`.
- Each queue item permanently records `recipient_name`, `phone`, `variant_id`, `media_asset_id`, `personalized_content`, and `idempotency_key`.
- On retry or server recovery, the worker executes against the stored queue item directly, guaranteeing zero mutation or variant drift.

---

## 3. Verification & Test Outcomes

### Unit & Integration Tests
Command: `pytest tests/test_media_and_contacts.py -v`
- `test_media_upload_persistence_and_hash`: PASSED
- `test_missing_media_file_detection`: PASSED
- `test_media_deletion_protection_when_referenced`: PASSED
- `test_contact_edit_persists_tier_group_language`: PASSED
- `test_contact_opt_out_protection_no_automatic_opt_in`: PASSED
- `test_group_management_rename_and_delete_with_migration`: PASSED
- `test_bulk_move_and_bulk_edit_contacts`: PASSED
- `test_rule_based_allocation`: PASSED
- `test_balanced_rotation_allocation`: PASSED
- `test_reproducible_seeded_ab_allocation`: PASSED
- `test_queue_item_recovery_and_retry_preserves_variant_and_media`: PASSED

Full suite: `pytest`: **107 passed, 0 failed** in 9.28s.

### Visual & Browser Verification Artifacts
Generated by automated headless Chrome Selenium suite:
1. `docs/screenshots/screen_contacts_bulk_selection.png`: Demonstrates sticky bulk action bar activating upon row selection.
2. `docs/screenshots/screen_modal_manage_groups.png`: Demonstrates group management modal with contact counts, rename, and delete actions.
3. `docs/screenshots/screen_modal_edit_contact.png`: Demonstrates contact editing modal with Tier, Language, and Opt-Out protection.
4. `docs/screenshots/screen_modal_media_library.png`: Demonstrates durable media library with thumbnails, SHA-256 badges, and usage counts.
5. `docs/screenshots/screen_modal_test_send_with_media.png`: Demonstrates test-send modal displaying attached media preview.
6. `docs/screenshots/screen_campaign_allocation_and_media.png`: Demonstrates campaign form with media picker, variant allocation strategy, and seed input.

