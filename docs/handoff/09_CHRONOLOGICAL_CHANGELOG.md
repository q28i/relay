# 09 — Chronological Engineering Changelog

This document provides a complete chronological audit of all engineering phases, user requirements addressed, root causes identified, and solutions deployed across the project lifecycle.

---

### Phase 1: Legacy Tkinter to Modern FastAPI Web Stack
- **Context:** The original system was a single-threaded Python Tkinter desktop app ([`gui.py`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/gui.py)) with high crash vulnerability during automated sending.
- **Actions Taken:**
  - Designed and deployed an asynchronous FastAPI backend ([`backend/app.py`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/backend/app.py)).
  - Built an SQLite database layer ([`backend/database.py`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/backend/database.py)) for persistent contacts, templates, campaigns, and jobs.
  - Constructed a single-page web dashboard ([`backend/static/index.html`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/backend/static/index.html), [`backend/static/app.js`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/backend/static/app.js)) with live WebSocket telemetry.

---

### Phase 2: Ship-Readiness Audit & Security Review
- **Context:** Comprehensive security review before testing live browser automation.
- **Actions Taken:**
  - Enforced strict E.164 phone number normalization and input sanitization in [`validator.py`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/validator.py).
  - Added global suppression lists (Do Not Call / Opt-Out) to prevent unauthorized messaging.
  - Implemented safe file upload handlers with strict MIME-type and size validation in [`backend/routers/media.py`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/backend/routers/media.py).
  - Masked customer phone numbers in logs and telemetry (`logger.py`).

---

### Phase 3: Browser & Profile Picker ("Messaging Connection")
- **User Request:** Add a setup flow allowing operators to choose an existing local browser profile already signed into WhatsApp Web.
- **Actions Taken:**
  - Created [`browser_manager.py`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/browser_manager.py) to detect installed Chrome, Edge, Brave, and Firefox instances.
  - Parsed `Local State` (JSON) to extract human profile names (`"Default"`, `"Profile 1"`, etc.).
  - Added Profile Picker Modal in UI with honest statuses (`Not checked`, `Signed in`, `Needs QR sign-in`, `Browser unavailable`, `Could not verify`).

---

### Phase 4: Skill-Guided Architectural Simplification
- **User Request:** Challenge UI clutter, eliminate over-engineered dashboard widgets, and apply Karpathy guidelines.
- **Actions Taken:**
  - Removed redundant mock charts and speculative analytics cards.
  - Replaced multi-step fragmented navigation with a focused 5-tab layout (Dashboard, Contacts, Templates, Campaigns, Activity, Settings).
  - Consolidated state synchronization into single-responsibility controller methods in [`app.js`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/backend/static/app.js).

---

### Phase 5: High-Fidelity WhatsApp Web Conversation Preview
- **User Request:** Replace primitive phone preview with an authentic, familiar WhatsApp Web conversation preview.
- **Actions Taken:**
  - Designed responsive chat layout in [`styles.css`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/backend/static/styles.css) with recipient header, presence indicator, and micro-dot wallpaper pattern.
  - Styled sent and received chat bubbles with authentic WhatsApp green/white colors, timestamps, and SVG double checkmarks.
  - Added live template variable interpolation (`{{name}}`, `{{company}}`).
  - Implemented one-click toggle between Desktop Preview and Mobile Frame Preview.

---

### Phase 6: Product UI Redesign & Custom File Dropzone
- **User Request:** Stop using default browser file controls (`"Choose File / No file chosen"`) and improve visual hierarchy.
- **Actions Taken:**
  - Replaced browser file inputs with a custom drag-and-drop file target.
  - Added visual format badges (Images, Documents), size constraints, and instant remove actions.
  - Polished form labels, input heights, and primary action affordances.

---

### Phase 7: Urgent Fix for Browser Profile Routes & 404 Mismatches
- **User Request:** Fix non-functional browser profile setup showing repeated 404 errors.
- **Actions Taken:**
  - Diagnosed route mismatches between frontend API calls and FastAPI router registration.
  - Added route aliases in [`backend/routers/browser.py`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/backend/routers/browser.py) for `/api/browser-profiles`, `/api/browser/profiles`, `/api/browser-profile/selection`, etc.
  - Replaced generic toast error alerts with structured error payloads (`code`, `message`, `action`).

---

### Phase 8: Safe Browser Profile Locking & Button Disambiguation
- **User Request:** Fix crashes when selected Chrome profile is open in a desktop window; fix confusing error message sequence.
- **Actions Taken:**
  - Root Cause: Chromium places exclusive file locks on `User Data/lockfile`. Spawning a second process crashes with socket exit codes.
  - Implemented non-destructive lock inspection in [`browser_manager.py`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/browser_manager.py#L106-L126).
  - Built the **Two-Model Architecture**: Dedicated Relay Session (app-managed `whatsapp_browser_session/`) vs Existing Browser Profile.
  - Created inline locked profile card with 3 safe actions: "Use dedicated session" (recommended), "Choose another profile", "I closed Chrome — try again".
  - Strictly segregated "Test Connection" (DOM authentication probe) from "Send Test Message" (message dispatch).
  - Deduplicated UI toasts to prevent notification spam.

---

### Phase 9: Premium Dark Theme — "Void" (Onyx)
- **User Request:** Add a bespoke near-black luxury dark theme rather than an inverted light theme.
- **Actions Taken:**
  - Designed the **Void (Onyx)** theme with charcoal/onyx surfaces (`#08090A`, `#121417`, `#16191D`), graphite borders (`#22262B`), warm off-white text (`#EDEDED`), and emerald-teal glowing accents (`#0D9488`).
  - Implemented zero-flash theme bootstrapping script in `<head>`.
  - Added authentic WhatsApp Web dark-mode message bubbles (`#005C4B` outgoing, `#202C33` incoming).
  - Added pure CSS `.void-atmosphere` particle backdrop with `@media (prefers-reduced-motion)` support.

---

### Phase 10: Intelligent Connection Monitoring & Campaign Queue Auto-Resume
- **User Request:** Fix button hanging on "Opening..."; add real-time connection state machine and automatic login detection for dedicated sessions.
- **Actions Taken:**
  - Diagnosed 3 compounding causes: passive launch without URL navigation, dual-driver lock contention, and one-shot timeout without observation loop.
  - Built [`backend/connection_monitor.py`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/backend/connection_monitor.py) with 10 deterministic lifecycle states and a non-blocking 1.8s DOM observation loop.
  - Unified Dashboard and Settings with a **5-Step Visual Timeline Stepper** and live activity ticker.
  - Built **Pre-Flight Campaign Gating**: campaigns launched while unauthenticated transition to `WAITING_FOR_CONNECTION` (0 messages burned).
  - Implemented **Auto-Resume**: once the operator completes phone QR scan, the monitor detects login and automatically resumes campaign dispatch.
  - Built Recipient Queue Inspection Drawer (`#modal-job-drawer`) in Activity tab.

---

### Phase 11: Accessible Interactive Choice Controls
- **User Request:** Fix "fake" static card boxes for Theme and Connection Model choices into real interactive controls.
- **Actions Taken:**
  - Upgraded Theme options (`System`, `Light`, `Void`) into semantic `<fieldset role="radiogroup">` with native accessible `<input type="radio">`, custom `.radio-indicator`, `:focus-visible` focus rings, instant apply/preview, `localStorage` persistence, and toast feedback.
  - Upgraded Connection Model choices (`Dedicated Relay Session` vs `Existing Browser Profile`) into interactive radio cards with `Selected` badges and dynamically revealed action trays.
  - Upgraded Campaign Wizard Pace options (`Normal`, `Relaxed`, `Fast`) into accessible radio cards.
  - Upgraded Activity Status filters into an accessible segmented control container with `aria-pressed="true|false"`.
  - Automated verification script (`scratch/verify_interactive_cards.py`) passed; all 49 backend unit and integration tests passed (`100%`).

---

### Phase 12: Production Handoff Documentation Suite
- **User Request:** Log and document everything completed to date in a dedicated folder as handoff documentation.
- **Actions Taken:**
  - Created [`handoff/`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/handoff) suite containing 10 comprehensive documents covering system architecture, browser automation, connection engine, queue subsystem, design system, API references, test verification, runbook, and changelog.
  - Created top-level [`HANDOFF.md`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/HANDOFF.md) root pointer.

---

### Phase 13: Persistent Media, Real Contact Editing, and Deterministic Campaign Allocation
- **User Request:** Media disappears after restart; attached images do not send; contacts cannot be edited; lack of group management; lack of deterministic variant allocation.
- **Actions Taken:**
  - Built durable local media storage pipeline in `uploads/media/` with SHA-256 cryptographic hashing and SQLite persistence.
  - Implemented honest missing-file detection: halts permanently with error `"Media file not found: <path>. No text was sent."` Silently sending text when media is configured is completely prohibited.
  - Added Media Library modal (`#modal-media-library`) with thumbnail previews, content hash badges, availability flags, and referencing campaign usage counts with protected deletion.
  - Delivered interactive Contact Editing (`#modal-edit-contact`) covering Name, Phone, Group, Customer Tier, Language, Consent, and Custom Fields with strict opt-out protection requiring explicit override.
  - Delivered Audience Group Management (`#modal-manage-groups`) covering create, rename, and delete with automatic contact migration to fallback group.
  - Delivered sticky Contacts Bulk Action toolbar (`#contacts-bulk-bar`) supporting bulk group move, bulk tier set, bulk language set, and bulk delete.
  - Delivered 4 deterministic, auditable variant allocation models (`explicit_default`, `rule_based`, `balanced_rotation`, `ab_test`) with persisted random seed.
  - Added 11 automated test scenarios in [`tests/test_media_and_contacts.py`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/tests/test_media_and_contacts.py) (100% pass rate).
  - Executed Selenium headless Chrome integration test generating 6 visual proof screenshots in [`docs/screenshots/`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/docs/screenshots).
- **Reference:** See [`10_PERSISTENT_MEDIA_REAL_CONTACTS_AND_CAMPAIGN_ALLOCATION.md`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/docs/handoff/10_PERSISTENT_MEDIA_REAL_CONTACTS_AND_CAMPAIGN_ALLOCATION.md).

---

### Phase 14: Automatic Browser Conflict Resolution & Session Lifecycle Manager
- **User Request:** Fix the browser-profile locking problem permanently. When clicking Start Session or Test Connection, Relay should automatically handle browser-process conflicts and establish a working session.
- **Actions Taken:**
  - Built `SessionLifecycleManager` singleton (`backend/session_lifecycle.py`) tracking driver PID, browser PID, child process PIDs, creation timestamps, Relay ownership flags, and persisted metadata (`whatsapp_browser_session/relay_session.json`).
  - Implemented automatic graceful termination (`WM_CLOSE` via Win32 ctypes followed by tree termination) for previous Relay-owned browser instances without prompt.
  - Implemented strict personal browser window protection: never force-kills or executes indiscriminate `taskkill /F /IM chrome.exe`. Discovered personal browser windows trigger an accessible confirmation modal (`#modal-confirm-browser-restart`) with warning and Dedicated Session fallback.
  - Ensured process isolation: unrelated Chrome/Edge profiles running elsewhere on the user's computer are left completely untouched.
  - Integrated healthy session reuse: if an existing Relay session is connected and responsive, `Start Session` and `Test Connection` reuse it without relaunching.
  - Added launch concurrency mutex (`threading.Lock`) preventing race conditions or duplicate browser windows on rapid clicks.
  - Built automated orphaned session recovery upon application restart.
  - Created 10-scenario automated verification suite in [`tests/test_browser_conflict_resolution.py`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/tests/test_browser_conflict_resolution.py) (10/10 passed).
  - Verified full test suite (117/117 passed, 100% pass rate).
  - Executed Selenium visual verification script generating 4 proof screenshots in [`docs/screenshots/`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/docs/screenshots).
- **Reference:** See [`11_BROWSER_CONFLICT_RESOLUTION_AND_SESSION_LIFECYCLE.md`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/docs/handoff/11_BROWSER_CONFLICT_RESOLUTION_AND_SESSION_LIFECYCLE.md).



