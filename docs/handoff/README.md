# WhatsApp Automation Relay — Engineering Handoff Documentation

Welcome to the definitive handoff documentation package for the **WhatsApp Automation Relay** project. This documentation details every engineering decision, architectural overhaul, browser automation subsystem, UI/UX redesign, connection monitoring state machine, and test verification completed to date.

---

## 📚 Document Index & Navigation

This documentation suite is organized into focused, modular chapters:

| Document | Topic & Focus Area | Key Components Covered |
| :--- | :--- | :--- |
| **[00_EXECUTIVE_SUMMARY.md](00_EXECUTIVE_SUMMARY.md)** | **Project Transformation & State** | High-level overview, transition from legacy Tkinter script to modern web stack, verified metrics, and milestone log. |
| **[01_SYSTEM_ARCHITECTURE.md](01_SYSTEM_ARCHITECTURE.md)** | **System Architecture & Data Flow** | FastAPI server design, SQLite schema, modular router hierarchy, async event loop, and data models. |
| **[02_BROWSER_AUTOMATION_AND_PROFILES.md](02_BROWSER_AUTOMATION_AND_PROFILES.md)** | **Browser Management & Locking** | Multi-browser profile discovery, lockfile contention handling, Dedicated Session vs Existing Profile models. |
| **[03_CONNECTION_MONITORING_ENGINE.md](03_CONNECTION_MONITORING_ENGINE.md)** | **Real-Time State Machine** | 10-state connection monitor, non-blocking DOM heuristics, auto-reconnect, and real-time WebSocket telemetry. |
| **[04_CAMPAIGN_QUEUE_AND_EXECUTION.md](04_CAMPAIGN_QUEUE_AND_EXECUTION.md)** | **Queue, Jobs & Anti-Ban Safety** | `BackgroundJobWorker`, pre-flight connection gating, idempotency hashing, rate pacing, auto-resume, and failure recovery. |
| **[05_UI_UX_AND_DESIGN_SYSTEM.md](05_UI_UX_AND_DESIGN_SYSTEM.md)** | **UI/UX & Design Tokens** | Light and Void (Onyx) themes, authentic WhatsApp Web conversation preview, accessible radio cards, and segmented controls. |
| **[06_API_AND_WEBSOCKET_REFERENCE.md](06_API_AND_WEBSOCKET_REFERENCE.md)** | **REST API & Telemetry Contract** | Exhaustive endpoint documentation, Pydantic schemas, error codes, and WebSocket event payloads. |
| **[07_TESTING_AND_VERIFICATION_MATRIX.md](07_TESTING_AND_VERIFICATION_MATRIX.md)** | **Test Suites & Verification Evidence** | 49-test backend test suite, automated Playwright/Selenium test scripts, and UI screenshot evidence across scenarios. |
| **[08_OPERATIONS_AND_RUNBOOK.md](08_OPERATIONS_AND_RUNBOOK.md)** | **Operations, Runbook & Troubleshooting** | Setup instructions, startup scripts (`start_dashboard.bat`), config parameters, database administration, and operational debugging. |
| **[09_CHRONOLOGICAL_CHANGELOG.md](09_CHRONOLOGICAL_CHANGELOG.md)** | **Chronological Engineering Log** | Step-by-step history of every user prompt, diagnosed root cause, surgical fix, and verified milestone. |
| **[10_PERSISTENT_MEDIA_REAL_CONTACTS_AND_CAMPAIGN_ALLOCATION.md](10_PERSISTENT_MEDIA_REAL_CONTACTS_AND_CAMPAIGN_ALLOCATION.md)** | **Media, Contacts & Allocation** | Durable media storage, SHA-256 content hashing, honest missing-file detection, contact editing & bulk actions, group migration, and deterministic allocation. |
| **[11_BROWSER_CONFLICT_RESOLUTION_AND_SESSION_LIFECYCLE.md](11_BROWSER_CONFLICT_RESOLUTION_AND_SESSION_LIFECYCLE.md)** | **Conflict Resolution & Session Lifecycle** | Automatic conflict resolution for Relay sessions, personal browser confirmation modal, orphaned process recovery, concurrency lock, and 10-scenario verification. |
| **[12_REAL_CONTACTS_LIBRARY_AND_CAMPAIGNS.md](12_REAL_CONTACTS_LIBRARY_AND_CAMPAIGNS.md)** | **Real Contacts, Media Library & Campaigns** | Zero-pollution test isolation, multi-select contacts table with Shift+Click and cross-page selection, duplicate merging, safe demo removal, durable media library & collections, single-screen campaign dispatch with pre-send allocation preview, and 15-scenario verification. |

---

## ⚡ Quick Start for New Developers & Operators

To launch the modern web application immediately:

```bash
# 1. Open the project root in terminal
cd "c:\Users\Rift\Documents\Antigravity ide\whatsapp automation"

# 2. Run the automated startup launcher (handles dependencies & server)
.\start_dashboard.bat
```

Or run via Python directly:
```bash
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```
Once started, navigate to `http://127.0.0.1:8000` in any web browser.

---

## 🛡️ Core Architectural Principles

1. **Non-Destructive Browser Operation**: The system never tampers with personal browser profiles, never forcefully kills running browser processes, and never extracts cookies or credentials.
2. **Deterministic State Synchronization**: The UI never guesses connection state. A 10-state background observer interrogates the DOM safely and feeds live updates via WebSockets.
3. **Queue Idempotency & Resiliency**: Campaigns paused due to browser disconnection or phone QR logout are never marked as failed. When connection is re-established, the worker resumes without re-sending duplicate messages.
4. **Accessible, Token-Driven Design**: Every choice card is an accessible `<input type="radio">` control with keyboard focusability, screen reader support, and dual-theme styling (Light & Void).

