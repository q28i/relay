# System Architecture: Modern WhatsApp Automation Web Dashboard

This document details the architectural design, component boundaries, data pipelines, state management, and security models of the transformed WhatsApp Automation platform.

---

## 1. Architectural Philosophy & Principles

The application is structured as a decoupled, local-first web architecture:
1. **Decoupled Presentation & Execution:** The legacy Tkinter GUI is retired in favor of an independent browser-based Single Page Application (SPA) communicating over REST and WebSockets with a high-performance Python ASGI backend.
2. **Deterministic Background Workers:** Automation tasks that control Selenium browser automation run asynchronously in thread-safe background workers with observable lifecycle states (`queued`, `running`, `paused`, `completed`, `failed`, `cancelled`).
3. **Pluggable Automation Adapters:** The automation interface is abstracted via a `MessagingProvider` interface, decoupling the web API from Selenium and enabling easy testing via mock providers or future official Cloud APIs.
4. **Resilient Local Persistence:** Contacts, templates, campaigns, and execution records are stored in an embedded SQLite database (`whatsapp_web.db`), eliminating race conditions in flat files while maintaining zero external server requirements.

---

## 2. Component Architecture Diagram

```
+---------------------------------------------------------------------------------------+
|                                    PRESENTATION LAYER                                 |
|                                                                                       |
|   Modern Responsive Single Page Web Dashboard (HTML5, Modern CSS, ES6+)              |
|   +-------------------------------------------------------------------------------+   |
|   | Navigation Bar & Live Engine Status (Status Badges, WS Connection Pulse)      |   |
|   +-------------------------------------------------------------------------------+   |
|   | Dashboard Views:                                                              |   |
|   |  1. Overview: System KPIs, Active Tasks, Recent Activities, Engine Status     |   |
|   |  2. Contacts Hub: File Ingestion, Phone Cleaner, Column Mapper, Groups Table   |   |
|   |  3. Template Studio: Multi-variable Editor, Spintax Tester, Live Previews     |   |
|   |  4. Campaign Wizard: 5-Step Guided Staging, Pre-flight Auditing, Dry-Run      |   |
|   |  5. Job Monitor: Real-time Gauges, Pause/Resume/Cancel, Contact Live Log      |   |
|   |  6. System Logs: Filterable Audit Log Viewer, WebSocket Real-time Feed        |   |
|   |  7. Settings & Presets: Safe / Balanced / Fast Profiles, Hardware Info       |   |
|   +-------------------------------------------------------------------------------+   |
+---------------------------------------------------------------------------------------+
                                           |
                                    HTTP / WebSockets
                                           |
+---------------------------------------------------------------------------------------+
|                                      API GATEWAY                                      |
|                                                                                       |
|   FastAPI ASGI Application (Uvicorn on 127.0.0.1:8000)                                |
|   - CORS Middleware (Restricted to Localhost Origins)                                 |
|   - Static File Mounting (`/` -> Single Page Application)                             |
|   - Global Exception Handler (Structured JSON Error Envelopes)                        |
|                                                                                       |
|   REST Routers:                                                                       |
|   - /api/contacts     : File upload, column auto-detection, normalization, CRUD       |
|   - /api/templates    : Template storage, dynamic variables, Spintax evaluator        |
|   - /api/campaigns    : Campaign builder, pre-flight audit, dry-run simulation        |
|   - /api/jobs         : Queue management, execution lifecycle, CSV report generation  |
|   - /api/config       : Typed configuration, safety presets, profile export/import    |
|   - /api/browser      : Chrome session monitoring, QR readiness, driver control       |
|   - /api/logs         : Audit log querying, level filtering                           |
|   - /ws               : WebSocket live telemetry & log broadcast endpoint             |
+---------------------------------------------------------------------------------------+
         |                                                 |
         v                                                 v
+-----------------------------+               +-----------------------------------------+
|      DATA & DOMAIN LAYER    |               |          AUTOMATION & WORKER LAYER      |
|                             |               |                                         |
| - SQLite Database           |               | - BackgroundJobWorker                   |
|   (`whatsapp_web.db`)       |               |   Thread-safe queue with cancellation   |
| - Pydantic Data Models      |               | - MessagingProvider (Abstract Interface)|
| - DataLoader                |               | - WhatsAppWebAdapter                    |
|   Excel / CSV ingestion     |               |   Wraps WhatsAppEngine & BrowserManager |
| - PreFlightValidator        |               | - MockMessagingProvider                 |
|   Duplicate & safety audits |               |   In-memory testing & simulation        |
| - ConfigManager             |               | - DryRunEngine                          |
|   Preset & bounds validator |               |   Zero-browser safety simulation        |
+-----------------------------+               +-----------------------------------------+
                                                                   |
                                                                   v
                                              +-----------------------------------------+
                                              |       SELENIUM CHROME WEBDRIVER         |
                                              | - Profile Directory Persistence         |
                                              | - Anti-detection Flags & User Agent     |
                                              | - Real WhatsApp Web Session             |
                                              +-----------------------------------------+
```

---

## 3. Subsystem Breakdown & Responsibilities

### 3.1 Backend Application (`backend/app.py`)
- Initializes FastAPI with lifespan context.
- Configures CORS middleware for `http://127.0.0.1:8000` and `http://localhost:8000`.
- Mounts static assets (`backend/static/`) for unified zero-build serving.
- Registers modular routers under `/api/*`.
- Manages global WebSocket connections and telemetry event dispatches.

### 3.2 Database Manager (`backend/database.py`)
- Provides thread-safe SQLite connection handling.
- Automatically initializes relational tables on startup:
  - `contacts`: Individual recipient records with normalized phone numbers, names, and custom attributes.
  - `contact_groups`: Named collections of contacts.
  - `templates`: Reusable message templates with variable extraction metadata.
  - `campaigns`: Staged campaign configurations with selected group, template, and delays.
  - `jobs`: Background execution records containing progress counters, timestamps, and status.
  - `job_results`: Detailed per-contact delivery records with timestamps and error codes.
  - `audit_logs`: Application event logs with severity levels.

### 3.3 Background Job Worker (`backend/job_queue.py`)
- Maintains an in-memory job state machine:
  - `QUEUED` -> `RUNNING` -> `PAUSED` -> `COMPLETED` / `FAILED` / `CANCELLED`.
- Executes tasks in background threads to avoid blocking the ASGI event loop.
- Supports instant pause and cancellation via thread-safe atomic flags (`threading.Event`).
- Periodically pushes progress events (percentage, sent count, failed count, current contact) over WebSockets.

### 3.4 Messaging Provider Interface & Adapter (`backend/adapter.py`)
- Defines `MessagingProvider` abstract base class with methods:
  - `initialize_browser()` -> bool
  - `check_session_status()` -> Dict[str, Any]
  - `send_message(phone, message, attachment)` -> Dict[str, Any]
  - `send_batch(contacts, config, progress_cb, log_cb)` -> List[Dict[str, Any]]
  - `pause()`, `resume()`, `stop()`, `close()`
- Implements `WhatsAppWebAdapter`: encapsulates `WhatsAppEngine` and `BrowserManager`.
- Implements `MockMessagingProvider`: simulates realistic message delivery with customizable delays and failure rates for automated testing and demo environments.

---

## 4. Real-time Communication Architecture

The Web Dashboard uses WebSockets (`/ws`) for bidirectional real-time telemetry:
1. **Connection Handshake:** Client connects to `ws://localhost:8000/ws`.
2. **Heartbeat / Ping:** Regular ping-pong keeps the socket alive.
3. **Telemetry Messages:**
   - `job_progress`: `{ type: "job_progress", job_id: "...", current: 15, total: 50, sent: 14, failed: 1, contact: {...} }`
   - `log_event`: `{ type: "log_event", timestamp: "...", level: "INFO", message: "..." }`
   - `browser_status`: `{ type: "browser_status", ready: true, logged_in: true }`
4. **Fallback Mechanism:** The frontend automatically falls back to HTTP polling (`GET /api/jobs/{id}`) every 2 seconds if WebSockets are interrupted.

---

## 5. Security & Boundary Architecture

- **Host Boundary:** Server listens exclusively on `127.0.0.1`.
- **Upload Boundary:** Contact files and media attachments are checked against whitelist extensions and size ceilings (15MB).
- **Profile Isolation:** Chrome profile is stored locally in the user's OS directory; credentials are never transmitted over the HTTP interface.
- **Privacy Masking:** Phone numbers are masked in all log outputs and real-time stream messages.
