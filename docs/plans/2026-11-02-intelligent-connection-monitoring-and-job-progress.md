# Intelligent Connection Monitoring and Job Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a real-time connection state machine and background observer for WhatsApp Web (handling QR scanning, account sync, profile locking, and connection drops), integrate connection awareness into campaign queue processing, and deliver an interactive connection monitor and live progress interface.

**Architecture:** A singleton `ConnectionMonitor` manages the browser process and WebDriver lifecycle, continuously observing browser window status and WhatsApp Web DOM states via non-blocking background polling. It coordinates directly with `WhatsAppWebAdapter` and `job_worker` so campaign dispatching respects live connection states, safely pausing on disconnect and resuming without duplicates on reconnect. The frontend consumes live connection telemetry and presents a single unified connection card with an event timeline, dynamic action controls, and per-recipient job inspection.

**Tech Stack:** Python 3.14, FastAPI, Selenium WebDriver, SQLite, HTML5, CSS3 (Light + Void themes), Vanilla JavaScript.

**Spec:** User request: "Add Intelligent Connection Monitoring and Job Progress"

---

## Global Constraints
- Supported states: `starting_browser`, `opening_whatsapp`, `waiting_for_qr`, `syncing_account`, `connected`, `profile_locked`, `browser_closed`, `connection_lost`, `timed_out`, `unknown_error`.
- Never scrape, copy, expose, or store QR content, cookies, passwords, or session tokens.
- Never show "Opening..." indefinitely: every state must include a timestamp, timeout, and recovery action.
- Do not start campaign sends when connection is not `connected`; queue them as `WAITING_FOR_CONNECTION`.
- Mid-campaign disconnect must pause safely, preserve idempotency keys, and never mark unsent as sent.
- Phone numbers must be masked by default in activity and queue views (`+1 415 ••• ••71`).
- Maintain WCAG AAA/AA contrast in both Light and Void themes.

## Review Focus
1. **Dedicated profile QR scan:** Browser opens, detects QR code canvas, displays "Waiting for QR scan", detects user scan, and automatically transitions to "Connected".
2. **Dedicated profile persistent re-launch:** Browser opens with an already-authenticated session and immediately marks "Connected" without asking for QR.
3. **External browser window lock:** When an existing profile is already in use by Chrome/Edge, detects lock immediately, displays "Profile locked", and offers "Use dedicated session".
4. **Browser closure while waiting or sending:** If user closes the browser window, monitor detects `browser_closed` / `connection_lost` within 3 seconds and pauses any running campaign safely.
5. **Campaign auto-resume:** Campaign started while "Waiting for QR scan" enters `WAITING_FOR_CONNECTION` and automatically starts sending once QR is scanned, without sending duplicates.

---

### Task 1: Connection State Machine & Background Monitor (`backend/connection_monitor.py`)

**Files:**
- Create: `backend/connection_monitor.py`
- Modify: `backend/adapter.py:80-120`
- Test: `tests/test_connection_monitor.py`

**Steps:**
- [ ] Define the 10 connection states enum/constants: `starting_browser`, `opening_whatsapp`, `waiting_for_qr`, `syncing_account`, `connected`, `profile_locked`, `browser_closed`, `connection_lost`, `timed_out`, `unknown_error`.
- [ ] Implement `ConnectionMonitor` class with thread-safe state management, timeline event logging, and configurable timeouts (default 120s for QR scan).
- [ ] Implement driver probe logic: non-destructively inspects active driver for window closure, URL navigation to WhatsApp Web, QR canvas elements, syncing spinner, and chat list elements.
- [ ] Integrate with `WhatsAppWebAdapter` so it uses the monitor's active driver instance, eliminating driver lock conflicts.
- [ ] Write unit tests verifying state transitions, event timeline logging, and timeout recovery.

---

### Task 2: Connection API Endpoints & Actions (`backend/routers/browser.py`)

**Files:**
- Modify: `backend/routers/browser.py`
- Modify: `backend/models.py`
- Test: `tests/test_connection_endpoints.py`

**Steps:**
- [ ] Add `GET /api/browser-connection/live`: returns current state, state label, mode, browser/profile info, last checked timestamp, current activity message, timeline events, and dynamic action buttons.
- [ ] Add `POST /api/browser-connection/action`: supports actions (`open_browser`, `cancel`, `restart`, `change_profile`, `use_dedicated`, `refresh`).
- [ ] Update `/api/browser-profile/open` and `/api/browser-profile/dedicated` to coordinate with `ConnectionMonitor`.
- [ ] Write tests ensuring endpoints return contract-compliant status objects without blocking HTTP requests.

---

### Task 3: Connection-Aware Campaign Queue Execution (`backend/job_queue.py` & `backend/routers/jobs.py`)

**Files:**
- Modify: `backend/job_queue.py:80-380`
- Modify: `backend/database.py`
- Modify: `backend/routers/jobs.py`
- Test: `tests/test_connection_queue.py`

**Steps:**
- [ ] Add `WAITING_FOR_CONNECTION` status to campaign lifecycle.
- [ ] Check `connection_monitor.is_connected()` when scheduling or starting a campaign. If not connected, set status to `WAITING_FOR_CONNECTION` and do not dispatch messages.
- [ ] Register listener on `connection_monitor`: when connection reaches `connected`, automatically trigger worker for any campaign in `WAITING_FOR_CONNECTION` if user scheduled/approved it.
- [ ] In worker loop: check connection before each recipient. If disconnected, transition job to `WAITING_FOR_CONNECTION` / `PAUSED`, log safe pause event, and do not mark unsent as sent.
- [ ] Add per-recipient queue item details and retry metadata to `GET /api/jobs/{job_id}/queue` and `GET /api/jobs/{job_id}`.
- [ ] Write tests verifying pause on disconnect, resume on reconnect, and strict idempotency preservation.

---

### Task 4: Unified Connection Card & Dynamic Actions UI (`backend/static/`)

**Files:**
- Modify: `backend/static/index.html`
- Modify: `backend/static/styles.css`
- Modify: `backend/static/app.js`

**Steps:**
- [ ] In `index.html`: Replace fragmented buttons on Dashboard and Settings with the single unified **Intelligent Connection Monitor Card**:
  - Live status badge & pulsing dot
  - Selected profile & mode pill
  - Last checked time and live activity message
  - 5-step visual event timeline (Browser launched -> WhatsApp Web opened -> QR detected -> Login confirmed -> Connection ready)
  - Dynamic action buttons by state (`Open WhatsApp Web`, `Cancel`, `Restart Connection`, `Use Dedicated Session`, etc.)
- [ ] In `app.js`: Implement `startConnectionPolling()` polling `/api/browser-connection/live` every 2s while browser is active or monitoring.
- [ ] In `styles.css`: Add styles for connection card, pulsing badges, stepper timeline, and state transitions in both Light and Void themes.

---

### Task 5: Live Activity & Per-Recipient Progress Drawer UI (`backend/static/`)

**Files:**
- Modify: `backend/static/index.html`
- Modify: `backend/static/styles.css`
- Modify: `backend/static/app.js`

**Steps:**
- [ ] In `index.html`: Add live activity card displaying current recipient (masked by default, e.g. `+1 415 ••• ••71`), queue status (`Preparing`, `Waiting for connection`, `Sending`, `Retrying`, `Paused`), counters (Sent, Pending, Failed, Skipped), last successful action timestamp, and last error.
- [ ] In `index.html`: Add expandable per-recipient drawer/modal with recipient phone (masked), message preview, status badge, attempts, and error reason.
- [ ] In `app.js`: Implement real-time rendering of active queue progress and drawer inspection.
- [ ] In `styles.css`: Style drawer, status tags, and progress components.

---

### Task 6: End-to-End Verification & Automated Test Suite

**Files:**
- Create: `scratch/verify_connection_and_progress.py`
- Test: `pytest`

**Steps:**
- [ ] Run full unit test suite with `pytest`.
- [ ] Run automated Selenium E2E script verifying:
  1. Dedicated session without login: QR detected, "Waiting for QR scan", activity countdown, dynamic buttons.
  2. Automatic transition to Connected when authenticated.
  3. App re-launch with authenticated session: connects immediately.
  4. Browser closed: detects connection loss and displays recovery actions.
  5. Campaign queued without connection: enters `WAITING_FOR_CONNECTION`.
  6. Connection restored: campaign resumes without duplicate sends.
  7. Mid-campaign connection loss: pauses safely.
  8. Capture screenshots of waiting, connected, blocked, and resumed states.
- [ ] Write delivery report artifact and report findings.

