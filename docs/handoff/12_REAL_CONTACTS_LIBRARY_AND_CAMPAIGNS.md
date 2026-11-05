# 12. Real Contacts, Media Library & Single-Screen Campaign Dispatch

## Executive Summary
This document records the end-to-end implementation and functional verification of **Relay's Real Contacts Management, Durable Media Library & Collections, and Single-Screen Campaign Dispatch**.

All fake UI, mock place-holders, and synthetic demo pollutions have been eliminated. Genuine user data (`Gaurav Patel`, `Me`, etc.) is strictly preserved, and automated tests now run exclusively in an isolated session database without polluting `whatsapp_web.db`.

---

## 1. Zero-Pollution Database Isolation & Safe Demo Record Elimination

### 1.1 Root Cause of Duplicate Test Records
Previously, integration tests (`tests/test_media_and_contacts.py`, `tests/test_api.py`) executed directly against the active SQLite production database (`whatsapp_web.db`), continuously seeding synthetic fixture records (`Jane Doe VIP`, `Beta User`, `Bulk 1/2/3`).

### 1.2 Isolation Architecture
- `RELAY_DB_PATH` environment variable support in `backend/database.py` allows overriding database location dynamically.
- `tests/conftest.py` declares an autouse session fixture `isolate_test_database` creating a clean temporary database in `tempfile.mkdtemp()`.
- Verified that running the entire test suite creates zero records in `whatsapp_web.db`.

### 1.3 Safe Demo Fixture Detection & Removal
- **Pattern Matching (`backend/database.py`):**
  Identifies synthetic fixture contacts matching test patterns (`Jane Doe%`, `Beta User%`, `Bulk %`, `Opted Out User%`, test area codes `1415555%`, etc.).
- **User Safeguard (`POST /api/contacts/demo-records/remove`):**
  Requires explicit user confirmation `{ "confirmed": true }`.
  Strictly excludes genuine contacts (`Gaurav`, `Me`, Indian country codes `9176%`, etc.).
- **Duplicate Detection & Merging (`POST /api/contacts/merge`):**
  Groups contacts by normalized E.164 phone number. Allows reviewing clusters and merging secondary duplicate IDs into a primary record without data loss.

---

## 2. Rebuilt Contacts Table & Batch Operations

### 2.1 Multi-Selection & Shift+Click Range Selection
- **Individual Row Checkboxes (`.contact-row-chk`):**
  Supports single-toggle with row highlighting.
- **Shift+Click Range Selection:**
  Tracks `lastCheckedContactIndex` to select or deselect continuous ranges of contacts on Shift+Click.
- **Header Checkbox (`#chk-select-all-contacts`):**
  Toggles visible page selection with indeterminate state when partially selected.
- **Cross-Page Filter Selection (`#contacts-filter-select-all-banner`):**
  When all visible page records are selected, a banner offers: *"Select all matching contacts across all pages"*, fetching all matching IDs dynamically.

### 2.2 Sticky Bulk Action Toolbar (`#contacts-bulk-bar`)
- Appears automatically whenever selections exist.
- **Move Group (`POST /api/contacts/bulk-move`):** Migrates contacts to target group.
- **Copy Group (`POST /api/contacts/bulk-copy`):** Duplicates contact records into a second audience segment.
- **Set Tier (`POST /api/contacts/bulk-edit`):** Batch updates customer tier (`Regular`, `VIP`, `Enterprise`, `Partner`).
- **Set Language (`POST /api/contacts/bulk-edit`):** Batch updates communication language.
- **Suppress / Opt-Out (`POST /api/contacts/bulk-edit`):** Enforces consent opt-out on all selected contacts.
- **Export Selected:** Client-side CSV generator exporting only selected records with quoting.
- **Transactional Delete (`POST /api/contacts/bulk-delete`):** Atomic deletion in SQLite with confirmation prompt.

### 2.3 Inline Name Editing & Add Contact Modal
- Inline pencil icon allows editing contact name directly inside the table cell with Enter-to-save and Escape-to-cancel.
- `+ Add Contact` modal (`#modal-add-contact`) includes duplicate prevention toggle (`deduplicate: true`), rejecting conflicting numbers with HTTP 409.

---

## 3. Real Asset Library ("Library") & Content Collections

### 3.1 Architecture & Durable Storage
- **Workspace Subnav:** Integrated inside `Messages` tab via segmented switch `[Library & Collections | Message Composer]`, avoiding top-level navigation clutter.
- **Storage Directory:** Stored outside temporary folders in `uploads/media/`.
- **SHA-256 Deduplication (`backend/routers/media.py`):**
  Computes SHA-256 hash on file upload. If identical content already exists, reuses existing database asset without creating duplicate disk files.
- **Asset Metadata:** Persists stable ID, safe filename, MIME type, file size, SHA-256 hash, and availability status.
- **Deletion Protection:** Raises HTTP 409 Conflict if attempting to delete an asset actively referenced in ongoing campaign queue items.

### 3.2 Content Collections (`backend/routers/collections.py`)
Named bundles grouping message templates and media assets:
1. **Fixed Pair:** Exactly one designated message draft and media asset per recipient.
2. **Approved Combinations:** Explicitly approved message-media pair combinations.
3. **Balanced Rotation:** Rotates approved messages and media evenly across audience recipients.

---

## 4. Single-Screen Campaign Dispatch & Pre-Send Allocation Preview

### 4.1 Single-Screen Workflow
Unified campaign dispatch screen eliminating confusing multi-step wizards:
- Campaign Name input with auto-draft recovery.
- Audience Group selector with live recipient count.
- Content Collection selector OR standalone message draft selector.
- Optional media attachment selector.
- Variant Allocation Strategy (`explicit_default`, `rule_based`, `balanced_rotation`, `reproducible_ab_test`).
- Sending Pace radio cards (`Normal` 8–15s, `Relaxed` 12–20s, `Fast` 4–8s).
- Dispatch Timing toggle (`Send immediately` vs `Schedule for later`).

### 4.2 Pre-Send Recipient Content Allocation Preview Table (`POST /api/campaigns/allocation-preview`)
Renders exact recipient assignments before launching:
```text
| # | Recipient | Phone | Assigned Message | Attached Media | Pairing Mode / Rule |
```
- Replaces variables (`{name}`, `{phone}`, custom attributes).
- Displays message title and rendered message snippet.
- Displays attached media icon, filename, and preview link (or *"Text only"*).
- Displays pairing mode or rule badge.
- Automatically calculates estimated delivery duration window.

---

## 5. Media Sending & WhatsApp Web Automation Engine Fix

### 5.1 Multi-Tier DOM Selectors in `whatsapp_engine.py`
Enhanced `_send_attachment_flow`:
1. Opens attach menu button (`span[data-icon='attach-menu-plus']`, `div[title='Attach']`, `span[data-icon='clip']`).
2. Targets hidden `input[type='file']` (accepting `image/*,video/mp4,3gpp,quicktime` or `*`).
3. Sends absolute file path to the file input.
4. Waits up to 10 seconds for the WhatsApp Web media preview overlay to appear.
5. Focuses media caption editor (`div[contenteditable='true']`).
6. Clicks send button (`span[data-icon='send']`, `button[aria-label='Send']`), falling back to JavaScript click and `Keys.ENTER`.

### 5.2 Zero Silent Fallback & Uncertain Outcome Safeguard
- If media fails to upload or attach, **never silently falls back to sending text only**.
- 8-second post-send verification loop verifies media preview overlay disappears.
- If preview does not clear or DOM state cannot be verified, returns:
  ```json
  { "status": "UNCERTAIN", "error": "Attachment send clicked but preview did not clear. Outcome unverified." }
  ```
- **Durable Queue Handling:**
  Queue items with `UNCERTAIN` status are marked `UNCERTAIN` and **never retried automatically**, guaranteeing zero duplicate messages to customers.

---

## 6. Comprehensive 15-Scenario Verification Matrix

All 15 verification scenarios from Section 15 of user specification were implemented in `tests/test_contacts_and_campaigns_real.py` and passed with 100% success rate:

| # | Verification Scenario | Test Method | Result |
|---|-----------------------|-------------|--------|
| 1 | Select five arbitrary contacts and delete them together | `test_scenario_01_bulk_delete_contacts` | **PASSED** |
| 2 | Select every contact matching a filter and perform bulk action | `test_scenario_02_filter_and_bulk_action` | **PASSED** |
| 3 | Create a group and move selected contacts into it | `test_scenario_03_create_group_and_move_contacts` | **PASSED** |
| 4 | Edit contact name and confirm persistence | `test_scenario_04_edit_contact_name_persists` | **PASSED** |
| 5 | Import duplicates -> confirm no repeated records | `test_scenario_05_prevent_duplicate_contact_creation` | **PASSED** |
| 6 | Remove confirmed demo records without deleting real contacts | `test_scenario_06_remove_demo_records_safeguard` | **PASSED** |
| 7 | Upload multiple pictures | `test_scenario_07_upload_multiple_pictures` | **PASSED** |
| 8 | Restart Relay -> confirm all library assets remain | `test_scenario_08_restart_preserves_library_assets` | **PASSED** |
| 9 | Save three messages and reuse them | `test_scenario_09_save_and_reuse_messages` | **PASSED** |
| 10 | Create collection containing messages and multiple media assets | `test_scenario_10_create_content_collection` | **PASSED** |
| 11 | Pre-send allocation preview table verification | `test_scenario_11_pre_send_allocation_preview` | **PASSED** |
| 12 | Verify correct media is attached during test send | `test_scenario_12_media_attached_during_test_send` | **PASSED** |
| 13 | Confirm actual send outcome is recorded | `test_scenario_13_actual_outcome_recorded` | **PASSED** |
| 14 | Restart during queued-job -> resume without duplicating sent | `test_scenario_14_restart_during_job_does_not_duplicate_sent` | **PASSED** |
| 15 | Confirm system does not duplicate uncertain sends | `test_scenario_15_uncertain_send_not_duplicated` | **PASSED** |

---

## 7. Captured Visual Browser Verification Proof

Captured high-resolution screenshots verifying live UI components:

1. **Contacts Workspace & Bulk Toolbar:**
   `screen_contacts_workspace.png`
   Displays the Contacts table with multi-select checkboxes, sticky bulk action toolbar, and test records safeguard banner.

2. **Add Contact Modal:**
   `screen_modal_add_contact.png`
   Displays the "+ Add New Contact" modal with deduplication checkbox enabled.

3. **Demo Records Safeguard Modal:**
   `screen_modal_demo_records.png`
   Displays the "Identified Test Fixture Records" modal showing synthetic fixture records safely isolated from genuine user contacts (`Gaurav`, `Me`).

4. **Messages Workspace - Real Asset Library:**
   `screen_library_workspace.png`
   Displays the segmented subnav toggle `[Library & Collections | Message Composer]`, media assets grid with thumbnails, sizes, and SHA-256 hashes, and content collections list.

5. **Content Collection Editor Modal:**
   `screen_modal_collection_editor.png`
   Displays collection pairing modes (`Fixed Pair`, `Approved Combinations`, `Balanced Rotation`) and item checkboxes.

6. **Single-Screen Campaign & Allocation Preview Table:**
   `screen_campaign_allocation_preview.png`
   Displays the single-screen Campaign view with the pre-send Allocation Preview Table showing exact assigned Message and Media per recipient.

