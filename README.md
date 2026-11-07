# Relay — WhatsApp Automation & Campaign Relay

Relay is a local, resilient WhatsApp automation platform designed for personalized outreach, customer notifications, and media delivery directly through persistent Chromium browser sessions.

---

## Technical Overview & Documentation Hub

Comprehensive architectural specifications, incident post-mortems, testing runbooks, and operational guides are maintained in the [`docs/`](docs/) directory:

- **[System Architecture (`docs/ARCHITECTURE.md`)](docs/ARCHITECTURE.md)**: Full component specification, FastAPI backend, SQLite schema, and 5 interactive Mermaid lifecycle diagrams.
- **[WhatsApp Media Pipeline (`docs/WHATSAPP_MEDIA_PIPELINE.md`)](docs/WHATSAPP_MEDIA_PIPELINE.md)**: Forensic history of the Sticker Bug, dynamic file input interception via `HTMLInputElement.prototype.click`, and zero-silent-drop caption enforcement.
- **[Dispatch Engine (`docs/DISPATCH_ENGINE.md`)](docs/DISPATCH_ENGINE.md)**: Campaign creation, anti-ban pacing jitter, session locking, durable queue recovery, and failure isolation.
- **[Browser Session Management (`docs/BROWSER_SESSIONS.md`)](docs/BROWSER_SESSIONS.md)**: Persistent dedicated session (`whatsapp_browser_session/`), Chromium 136+ compatibility, cached driver resolution, and conflict resolution.
- **[Incident History & Defect Ledger (`docs/INCIDENT_HISTORY.md`)](docs/INCIDENT_HISTORY.md)**: Chronological record of 17 historical engineering defects, root causes, and verified fixes.
- **[Operator & User Guide (`docs/USER_GUIDE.md`)](docs/USER_GUIDE.md)**: Step-by-step instructions for importing contacts, building templates, launching campaigns, and monitoring activity.
- **[Testing & Verification Framework (`docs/TESTING.md`)](docs/TESTING.md)**: Test suite organization, database isolation, 236 passing automated tests, and regression checklists.
- **[Security & Safety Policy (`docs/SECURITY.md`)](docs/SECURITY.md)**: Local credential boundaries, phone number privacy masking, opt-out suppression, and anti-ban limits.

---

## Core Capabilities

- **Unified Photo & Caption Delivery**: Dispatches authentic photographic media attachments with bound captions (`image_with_caption`), strictly bypassing WhatsApp's sticker workflow.
- **Persistent Dedicated Browser Sessions**: Stores WhatsApp Web authentication tokens locally in `whatsapp_browser_session/`. Scan the QR code once; sessions reconnect automatically across restarts.
- **Anti-Ban Pacing & Jitter**: Emulates natural human typing rhythms with configurable randomized delay intervals (8–15s), batch cooldown pauses (60–90s per 20 sends), and daily volume caps.
- **Organic Content Personalization**: Resolves curly-bracket Spintax (`{Hi|Hello|Hey}`) and dynamic contact variables (`{name}`, `{phone}`) so that no two outgoing messages are textually identical.
- **Durable State & Duplicate Prevention**: Backed by SQLite. Any unconfirmed send automatically transitions the campaign to `RECONCILIATION_REQUIRED`, halting execution to protect against duplicate messaging.

---

## Technology Stack

- **Backend**: Python 3.10+ (FastAPI, Uvicorn ASGI, Pydantic)
- **Automation Harness**: Selenium WebDriver 4.x controlling Google Chrome / Microsoft Edge / Brave
- **Database**: Local SQLite 3 with thread-safe locking and durable audit logs
- **Frontend**: Vanilla JavaScript SPA (ES6+), HTML5, CSS3, WebSockets
- **Testing**: `pytest` (236 automated unit, regression, and DOM-mocking tests)

---

## Quick Start

### 1. Requirements
- Windows 10/11
- Python 3.10 or higher
- Google Chrome (or Microsoft Edge / Brave)

### 2. Launch Web Dashboard
From the project root, start the local server:
```bash
python web_run.py --no-browser
```
*(Or double-click `start_dashboard.bat`).*

Open your browser and navigate to:
```text
http://127.0.0.1:8000
```

### 3. Connect WhatsApp
1. In the Web Dashboard, click **Start Relay Session**.
2. A dedicated Chrome browser will open to `https://web.whatsapp.com`.
3. Link your phone by scanning the QR code once. The session status will turn green (**Active in Relay**).

### 4. Run Automated Tests
Execute the full test suite from the repository root:
```bash
pytest
```
*Current test status: 236 passed, 0 failed.*

---

## Known Operational Boundaries

1. **Unofficial Automation**: Relay automates the official WhatsApp Web frontend using Selenium WebDriver. It does not use WhatsApp's official Cloud API. Dispatches must adhere to conservative pacing and recipient opt-in rules.
2. **Single Active Web Session**: WhatsApp permits only one active WhatsApp Web browser tab per phone number at any given moment. Opening WhatsApp Web elsewhere will disconnect the automation session.
3. **Desktop Viewport Requirement**: WhatsApp Web collapses into a mobile drawer layout if viewport width falls below 1024px. Relay automatically launches Chrome with `--window-size=1920,1080` to guarantee UI stability.
