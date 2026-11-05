# 10 — Persistent Media, Real Contact Editing, and Deterministic Campaign Allocation

## 1. Executive Summary

This engineering handoff documents the implementation and verification of the priority fixes addressing:
1. **Durable Media Storage & Honest WhatsApp Web Sending**: Elimination of silent text-only fallbacks, implementation of local disk storage (`uploads/media/`), SHA-256 content hashing, durable SQLite media asset tracking, and a Media Library interface.
2. **Interactive Contact Management & Group Operations**: Full-fledged contact editing (Name, Phone, Group, Customer Tier, Language, Consent, Custom Fields), group creation/renaming/deletion with fallback contact migration, and multi-select bulk actions (bulk move, bulk tier, bulk language, bulk delete).
3. **Strict Opt-Out Protection**: Safeguards ensuring opted-out recipients can never be automatically or accidentally re-opted in without explicit, auditable user confirmation (`consent_override: true`).
4. **Deterministic, Auditable Campaign Allocation**: Four auditable variant allocation models (`explicit_default`, `rule_based`, `balanced_rotation`, `ab_test`) with persisted random seed ensuring identical recipients receive identical variants across retries.
5. **Queue Item Durability & Recovery**: Permanent storage of chosen variant and media reference on queue items so restarts and retries never mutate scheduled messages.

---

## 2. Root Cause Analysis

### Issue A: Media Not Sending & Disappearing on Restart
- **Root Cause**: The frontend previously maintained temporary browser `Blob` or `File` object references in memory. The backend test-send and campaign launch endpoints accepted a text body, but lacked durable media foreign keys. When a browser session reloaded or a campaign was queued, the temporary file reference vanished, causing the engine to silently fall back to sending text-only messages without notifying the operator.
- **Solution**: 
  - Created durable directory `uploads/media/` inside the application workspace.
  - Implemented `POST /api/media/upload` which computes a SHA-256 cryptographic digest of the binary payload, saves the file to disk, and records metadata in SQLite table `media_assets`.
  - Added strict guardrails in `whatsapp_engine.py` and `job_queue.py`: if an attachment path is missing from disk, the job halts with status `FAILED_PERMANENT` and the explicit reason `"Media file not found: <path>. No text was sent."` Silently sending text when media was configured is strictly disallowed.

### Issue B: Contact Table Read-Only & Lack of Group Management
- **Root Cause**: Contacts only allowed toggling opt-out or deleting rows. No endpoints or UI existed to modify contact names, phone numbers, customer tiers, languages, or custom variables. Audience groups were static strings without rename or delete capabilities.
- **Solution**:
  - Implemented `PUT /api/contacts/{id}` and `GET /api/contacts/{id}` supporting all fields.
  - Added `POST /api/contacts/bulk-move` and `POST /api/contacts/bulk-edit`.
  - Built group management endpoints (`POST /api/contacts/groups`, `PUT /api/contacts/groups/{name}`, `DELETE /api/contacts/groups/{name}?fallback_group=...`) with safe contact migration so deleting a group never orphans contacts.

### Issue C: Accidental Re-Opt In Risk
- **Root Cause**: A simple edit or bulk update could accidentally flip an opted-out contact back to `opted_in`.
- **Solution**: 
  - Added a backend check in `update_contact()` and `bulk_edit_contacts()`: if an existing contact has `consent_status == 'opted_out'`, any change to `opted_in` without `consent_override=True` is rejected or preserves the `opted_out` status.
  - The UI presents an explicit warning card requiring the operator to check `"Explicit Consent Override Required"` before saving.

---

## 3. Architecture & Data Flow

```
[Media Upload]
       │
       ▼
 [SHA-256 Hash] ──► [Save to uploads/media/<uuid>.<ext>] ──► [Insert into SQLite media_assets]
                                                                     │
                                                                     ▼
[Campaign Launch] ◄────────────────────────────────────────── [Media Library]
       │
       ▼
[Allocation Strategy]
  ├── explicit_default (Primary base template)
  ├── rule_based (Match recipient tier/lang/custom)
  ├── balanced_rotation (Round-robin across alternatives)
  └── ab_test (Deterministic MD5 modulo with seed)
       │
       ▼
[Persist Queue Items] ──► (recipient, variant_id, media_asset_id, resolved_message, idempotency_key)
       │
       ▼
[Worker Execution]
  ├── Verify media file exists on disk (fail closed if missing)
  ├── Open chat in WhatsApp Web
  ├── Attach file via native file input
  ├── Type caption into text container
  └── Confirm delivery & record media_sent=true
```

---

## 4. UI Components Delivered

| Component | Location | Description |
| :--- | :--- | :--- |
| **Contacts Bulk Action Bar** | `#contacts-bulk-bar` | Sticky toolbar displayed when contacts are selected. Displays selection count, Move to Group dropdown, Set Tier dropdown, Set Language dropdown, Deselect All, and Bulk Delete. |
| **Contact Edit Modal** | `#modal-edit-contact` | Form editing Name, Phone, Group, Tier (`Regular`, `VIP`, `Enterprise`, `Partner`), Language (`en`, `es`, `fr`, etc.), Consent Status, and Custom JSON fields. Enforces explicit override when un-suppressing. |
| **Manage Groups Modal** | `#modal-manage-groups` | Group listing with contact counts. Supports inline group creation, safe renaming, and deletion with fallback group migration. |
| **Durable Media Library** | `#modal-media-library` | Asset card grid displaying thumbnails, title, MIME type, file size, SHA-256 hash badge, and referencing campaign usage count. Supports direct upload and selection for drafts. |
| **Test Send Modal with Media** | `#modal-test-send` | Displays attached media thumbnail, filename, and size confirmation, guaranteeing media will dispatch alongside caption text. |
| **Campaign Allocation Controls** | `#tab-campaigns` | Media attachment picker and variant allocation strategy selector (`explicit_default`, `rule_based`, `balanced_rotation`, `ab_test`) with seed input. |

---

## 5. Verification & Test Evidence

### Automated Test Matrix
1. `tests/test_media_and_contacts.py`: **11 passed, 0 failed** in 2.45s:
   - `test_media_upload_persistence_and_hash` (Uploads file, validates SHA-256 digest and disk existence).
   - `test_missing_media_file_detection` (Verifies missing file marks `is_available: false` and blocks text-only dispatch).
   - `test_media_deletion_protection_when_referenced` (Returns 409 Conflict if referenced by campaign; allows force delete).
   - `test_contact_edit_persists_tier_group_language` (Verifies updates to tier, group, language, and audit logs).
   - `test_contact_opt_out_protection_no_automatic_opt_in` (Verifies opted-out contact cannot be converted without override).
   - `test_group_management_rename_and_delete_with_migration` (Verifies group rename and delete with contact migration).
   - `test_bulk_move_and_bulk_edit_contacts` (Verifies bulk group move and bulk tier/lang edits).
   - `test_rule_based_allocation` (Verifies attribute-based variant routing for Spanish and VIP recipients).
   - `test_balanced_rotation_allocation` (Verifies round-robin allocation across recipients).
   - `test_reproducible_seeded_ab_allocation` (Verifies identical split across repeated runs with seed=42).
   - `test_queue_item_recovery_and_retry_preserves_variant_and_media` (Verifies worker preserves variant and media across retries).
2. Full pytest suite: **107 passed, 0 failed** across all test files in 9.28s.

### Visual & End-to-End Proof
The Selenium integration suite executed against the live local server (`http://127.0.0.1:8000`) verified all UI interactions:
- `screen_contacts_bulk_selection.png`: Demonstrates sticky bulk action toolbar appearing upon selecting contacts.
- `screen_modal_manage_groups.png`: Demonstrates Manage Groups modal with group counts and rename/delete actions.
- `screen_modal_edit_contact.png`: Demonstrates Contact Edit modal with Customer Tier, Language, and Consent Status.
- `screen_modal_media_library.png`: Demonstrates Media Library with thumbnails, SHA-256 badges, and usage counts.
- `screen_modal_test_send_with_media.png`: Demonstrates Test Send modal showing attached media preview.
- `screen_campaign_allocation_and_media.png`: Demonstrates Campaign Form with Media Picker, Allocation Strategy, and Seed.

