# Relay Engineering Incident History & Defect Ledger

This document provides a chronological record of critical software defects, root causes, architectural fixes, verification evidence, and residual risks encountered throughout Relay's development.

---

## Chronological Defect Ledger

### Incident 1: Hardcoded Contact Data in UI
- **Symptoms**: The contacts table displayed static sample records regardless of CSV imports.
- **Confirmed Root Cause**: `backend/static/app.js` contained an inline mock array overriding SQLite API results.
- **Files Involved**: `backend/static/app.js`, `backend/routers/contacts.py`
- **Fix Implemented**: Removed static mock array; connected table rendering directly to `GET /api/contacts`.
- **Verification**: Loaded CSV with 50 unique contacts; verified exact rendering in UI.
- **Remaining Risk**: Large contact sets (>5,000) require paginated scrolling to maintain DOM performance.

---

### Incident 2: Missing Bulk-Selection Controls
- **Symptoms**: Operators could not select or delete multiple contacts simultaneously.
- **Confirmed Root Cause**: UI lacked batch checkbox handlers and bulk action endpoints.
- **Files Involved**: `backend/static/app.js`, `backend/routers/contacts.py`, `backend/database.py`
- **Fix Implemented**: Added `POST /api/contacts/bulk-delete` and `POST /api/contacts/bulk-move`; implemented "Select All" header checkbox in the SPA.
- **Verification**: Batch selected and deleted 20 test contacts; verified persistence in SQLite.
- **Remaining Risk**: Accidental bulk deletion requires operator confirmation modals.

---

### Incident 3: Media Library Test-Data Contamination
- **Symptoms**: Media Library displayed three leftover placeholder images (`asset_dummy_*.jpg`) that the operator never uploaded.
- **Confirmed Root Cause**: Initial database seeding scripts inserted test fixture assets on startup.
- **Files Involved**: `backend/database.py`, `backend/routers/media.py`
- **Fix Implemented**: Removed automatic test fixture seeding; added hash-based deduplication and clean asset deletion.
- **Verification**: Inspected `media_assets` table; confirmed zero unapproved or ghost records.
- **Remaining Risk**: If an operator deletes a media file directly from the filesystem, database references must report `is_available: false`.

---

### Incident 4: Template Save API Failures (404 Not Found)
- **Symptoms**: Clicking "Save Template" resulted in `Failed to save template: Not Found`.
- **Confirmed Root Cause**: Route mismatch. Frontend called `POST /api/templates/{id}/save`, but backend had registered `PUT /api/templates/{id}`.
- **Files Involved**: `backend/routers/templates.py`, `backend/static/app.js`
- **Fix Implemented**: Registered explicit `POST /api/templates/{template_id}/save` route with schema validation.
- **Verification**: Created and saved templates with multiple variants; verified 200 OK responses.
- **Relevant Commit**: Historical template route alignment.
- **Remaining Risk**: Frontend must keep request payload schemas synchronized with Pydantic models.

---

### Incident 5: Browser-Profile Persistence Failures
- **Symptoms**: Relay forgot the selected browser profile on server restart, requiring repeated re-selection.
- **Confirmed Root Cause**: Profile preferences were stored only in memory within the FastAPI application instance.
- **Files Involved**: `config_manager.py`, `backend/connection_monitor.py`
- **Fix Implemented**: Persisted `saved_config` directly to `config.json` with automatic restoration during startup.
- **Verification**: Configured persistent profile, restarted server process, verified immediate session reuse.
- **Remaining Risk**: Corrupted or manually edited `config.json` files fall back to dedicated defaults.

---

### Incident 6: WhatsApp Connection-State Inconsistencies
- **Symptoms**: UI displayed "Disconnected" or "Cannot be automated" even though WhatsApp Web was open and authenticated.
- **Confirmed Root Cause**: Observation worker checked only a single selector that was absent during WhatsApp Web's subtle UI updates.
- **Files Involved**: `backend/connection_monitor.py`
- **Fix Implemented**: Expanded `sync_selectors` and `app_shell_selectors` to include multiple modern selectors (`div#main`, `div[data-testid='chat-list']`, `canvas[aria-label='Scan this QR code']`).
- **Verification**: Simulated network interruptions and verified clean transitions from `SYNCING_ACCOUNT` to `CONNECTED`.
- **Remaining Risk**: WhatsApp Web redesigns could change top-level app container identifiers.

---

### Incident 7: Media Attachment Failures
- **Symptoms**: Campaigns with media files failed to open the file picker or upload files.
- **Confirmed Root Cause**: Hidden file inputs had `style="display: none;"`, causing Selenium `send_keys` to reject interaction.
- **Files Involved**: `whatsapp_engine.py`
- **Fix Implemented**: Injected JavaScript to force `arguments[0].style.display = 'block'; arguments[0].style.visibility = 'visible';` prior to `send_keys`.
- **Verification**: Verified file delivery to input across Chrome and Edge drivers.
- **Remaining Risk**: OS-level permissions restricting browser access to the `uploads/` directory.

---

### Incident 8: Missing Captions on Outgoing Media
- **Symptoms**: Media was transmitted, but the accompanying text caption was omitted.
- **Confirmed Root Cause**: Caption typing executed before the media preview modal finished rendering its contenteditable container.
- **Files Involved**: `whatsapp_engine.py`
- **Fix Implemented**: Added explicit polling loop waiting for `PREVIEW_CONTAINER_SELECTORS` before querying caption elements.
- **Verification**: Verified caption rendering in preview before clicking Send.
- **Remaining Risk**: Lexical/React editor updates in WhatsApp Web could delay element readiness.

---

### Incident 9: Duplicate Media Retries on Partial Sends
- **Symptoms**: When a follow-up text failed in `image_then_text` mode, retrying the recipient re-sent the image, causing duplicate customer photos.
- **Confirmed Root Cause**: Retry engine lacked stage-awareness and re-executed the entire pipeline from scratch.
- **Files Involved**: `backend/job_queue.py`, `whatsapp_engine.py`
- **Fix Implemented**: Introduced `stage="text_only"`, `last_successful_stage="media"`, and `recovery_eligibility="retry_text_only"`.
- **Verification**: Simulated text failure; verified that automatic retry dispatched text only.
- **Relevant Commit**: `c074afb`
- **Remaining Risk**: Operator manually resetting stage flags could trigger a full re-send.

---

### Incident 10: Stuck Media Preview Overlays
- **Symptoms**: After clicking media Send, the preview modal remained visible on screen. Relay hung for 30s and failed.
- **Confirmed Root Cause**: The send button click failed to propagate because animation overlays intercepted the event.
- **Files Involved**: `whatsapp_engine.py`
- **Fix Implemented**: Multi-stage click fallback: native element click &rarr; ActionChains &rarr; JavaScript dispatchEvent; added forced preview dismissal (`_dismiss_media_preview(force=True)`).
- **Verification**: Verified overlay dismissal across 50 simulated send cycles.
- **Relevant Commit**: `0b3da50`
- **Remaining Risk**: Extremely slow network connections delaying media upload completion.

---

### Incident 11: Headless Browser Layout Problems
- **Symptoms**: Headless dispatch worked on single sends but broke on multi-recipient campaigns because UI elements were missing.
- **Confirmed Root Cause**: Headless Chrome defaulted to an 800x600 viewport, triggering WhatsApp Web's mobile drawer layout.
- **Files Involved**: `browser_manager.py`
- **Fix Implemented**: Added `--window-size=1920,1080` and `--start-maximized` to headless launch options.
- **Verification**: Compared DOM tree between headed and headless runs; verified identical desktop layout.
- **Relevant Commit**: `0b3da50`
- **Remaining Risk**: Multi-monitor setups with non-standard DPI scaling.

---

### Incident 12: False Connection-Loss Detection
- **Symptoms**: During campaign dispatch, Relay erroneously reported "Session Disconnected" and attempted to restart the browser.
- **Confirmed Root Cause**: Connection monitor executed driver commands simultaneously with the dispatch engine, causing WebDriver timeout exceptions.
- **Files Involved**: `backend/connection_monitor.py`, `backend/job_queue.py`
- **Fix Implemented**: Introduced `_session_dispatch_lock`. Connection monitor yields whenever an active send is in progress.
- **Verification**: Ran full 3-recipient campaign; verified zero connection-loss warnings during dispatch.
- **Relevant Commit**: `4c63256`
- **Remaining Risk**: WebDriver crashing due to operating system out-of-memory events.

---

### Incident 13: Incorrect Outgoing-Message Verification
- **Symptoms**: Relay marked media as `SENT` when only a plain text message had been delivered.
- **Confirmed Root Cause**: Outgoing message observer checked only for the presence of new message bubbles without verifying whether the bubble contained media elements (`img`, `video`).
- **Files Involved**: `whatsapp_engine.py`
- **Fix Implemented**: Enhanced `_get_outgoing_message_data` to inspect child nodes for `img`, `video`, `data-testid='media-canvas'`, and explicitly check `require_media=True`.
- **Verification**: Dispatched plain text in a media test; verified engine correctly returned `FAILED`.
- **Relevant Commit**: `8c3d824`, `961f5dc`
- **Remaining Risk**: WhatsApp changing DOM tag names for media rendering.

---

### Incident 14: Sticker-Input Misrouting (The "Sticker Bug")
- **Symptoms**: Uploaded JPEG photos were sent as stickers; captions were typed into the background composer.
- **Confirmed Root Cause**: Static hidden input `<input accept="image/*">` (Sticker Maker) matched before dynamic Photos & Videos input.
- **Files Involved**: `whatsapp_engine.py`
- **Fix Implemented**: Intercepted `HTMLInputElement.prototype.click` on `Photos & videos` button; strictly validated `accept` attribute contains `video`; excluded `closest('footer')` for captions.
- **Verification**: Verified `input_accept="image/*,video/mp4..."`, `is_sticker=False`, and normal photo bubble delivery in chat.
- **Relevant Commit**: `4c63256`
- **Remaining Risk**: WhatsApp renaming the "Photos & videos" aria-label in localized languages.

---

### Incident 15: Browser Monitoring Contention
- **Symptoms**: Intermittent `StaleElementReferenceException` during media upload.
- **Confirmed Root Cause**: Observation worker was querying the DOM while the dispatch engine was uploading files.
- **Files Involved**: `backend/connection_monitor.py`
- **Fix Implemented**: `_session_dispatch_lock` acquired during all attachment flows.
- **Verification**: Ran 25 parallel observation-vs-dispatch stress tests; zero contention exceptions.
- **Relevant Commit**: `4c63256`
- **Remaining Risk**: Long dispatch timeouts (>60s) keep monitor paused for extended periods.

---

### Incident 16: Multi-Recipient Queue Interruptions on Uncertain Outcomes
- **Symptoms**: An unconfirmed send on recipient 1 caused the queue to halt, but the UI showed `RUNNING` or `PAUSED` without clear operator instructions.
- **Confirmed Root Cause**: Status remained ambiguous, creating confusion on whether to resume or cancel.
- **Files Involved**: `backend/job_queue.py`, `backend/static/app.js`
- **Fix Implemented**: Explicitly transitioned job status to `RECONCILIATION_REQUIRED`; displayed amber warning badge and banner in the UI instructing manual chat check.
- **Verification**: Triggered simulated uncertain send; verified campaign paused and UI displayed `Reconciliation Required`.
- **Relevant Commit**: `1237ccd`
- **Remaining Risk**: Operators resuming without checking the actual chat may create duplicates if the send succeeded.

---

### Incident 17: Working Photo-with-Caption Delivery Baseline
- **Symptoms**: N/A (Confirmed Working State).
- **Confirmed Status**:
  - Outgoing message is a standard photographic bubble.
  - Caption `123 automation check` is attached directly to the image.
  - 3 out of 3 recipients processed successfully.
  - Zero sticker misrouting.
- **Verification**: Live test screenshot verified on user environment; 236 automated tests passing.
- **Relevant Commit**: `1237ccd` (and `4c63256`)
- **Remaining Risk**: External WhatsApp Web DOM changes require continuous regression verification.
