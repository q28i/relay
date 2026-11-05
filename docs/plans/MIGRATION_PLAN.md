# Migration Plan: Desktop GUI to Modern Web Dashboard

This document defines the architectural strategy, feature classification, data preservation model, and rollback procedures for transforming the legacy Python Tkinter desktop application into a modern, responsive, and robust web dashboard.

---

## 1. Feature Migration Matrix

Every capability from the original desktop system is classified into one of five migration strategies:
- **Reuse:** Preserved with minimal or no modifications.
- **Refactor:** Business logic adapted to decouple from GUI widgets and fit async web APIs.
- **Replace:** Desktop-specific component completely replaced by web-native equivalents.
- **Extend:** Enhanced with new capabilities enabled by the web architecture.
- **Retire:** Deprecated or eliminated because it is obsolete or inappropriate for a web environment.

| Feature / Subsystem | Desktop Implementation | Web Dashboard Architecture | Strategy | Rationale & Migration Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Phone Sanitization** | `DataLoader.clean_phone_number()` | `DataLoader` + REST `/api/contacts/clean` | **Reuse** | Core regex and E.164 normalization logic is robust and tested. Exposed directly via API. |
| **Spintax Processor** | `process_spintax()` in `whatsapp_engine.py` | `whatsapp_engine.py` + `/api/templates/spintax-test` | **Reuse** | Recursive `{A\|B\|C}` substitution works reliably; exposed to template studio for real-time live preview. |
| **Config & Safety Presets** | `ConfigManager` (`config.json`) | `ConfigManager` + `/api/config` + REST presets | **Reuse** | Typed dataclass schema and JSON storage with bounds checking perfectly map to REST configuration endpoints. |
| **Pre-Flight Validation** | `PreFlightValidator` (`validator.py`) | `validator.py` + `/api/campaigns/validate` | **Reuse** | Pre-flight audit (duplicate detection, duration estimation, missing names) runs server-side before job execution. |
| **Dry-Run Simulation** | `DryRunEngine` (`validator.py`) | `validator.py` + `/api/campaigns/dry-run` | **Reuse** | Safe simulation engine runs in memory without launching Chrome; results streamed to web modal. |
| **Excel / CSV Loader** | `DataLoader.load_contacts()` | `DataLoader` + `/api/contacts/upload` + `/api/contacts/preview` | **Refactor** | Extracted from local file picker dialogs into multipart HTTP file upload with column-mapping preview. |
| **Automation Engine** | `WhatsAppEngine.send_batch()` | `WhatsAppWebAdapter` (`backend/adapter.py`) | **Refactor** | Decoupled from Tkinter `root.after()` and threading queues into an async background task worker with WebSocket callbacks. |
| **Device Identification** | `DeviceManager` (`device_manager.py`) | `/api/browser/device-info` | **Refactor** | Exposed to the web dashboard settings/status card to display CPU, RAM, and hardware ID. |
| **GUI Interface** | `WhatsAppGUI` in `gui.py` (Tkinter) | Responsive Single Page Web Dashboard (`backend/static/`) | **Replace** | Tkinter widgets replaced with responsive HTML5, modern CSS, dynamic cards, modals, and reactive state. |
| **Live Spreadsheets** | `tksheet.Sheet` widget in `gui.py` | Modern HTML5 Contact Table & Column Mapper | **Replace** | Replaced desktop canvas grid with accessible, sortable, filterable web table with inline badge tags. |
| **Desktop Log Console** | `tk.scrolledtext.ScrolledText` | Real-time WebSocket Log Streamer & Audit Table | **Replace** | Desktop text widget replaced with auto-scrolling terminal viewer connected to WebSocket broadcast. |
| **Desktop Dialogs & Alerts**| `messagebox.showwarning()`, `filedialog` | Non-blocking Toast Notifications & Modal Dialogs | **Replace** | Eliminates modal freezes and thread-locking Windows message boxes. |
| **Contact Groups & Lists** | Flat CSV/Excel files on disk | SQLite Relational Contacts Store (`whatsapp_web.db`) | **Extend** | Adds persistent contact groups, tag management, saved audience filters, and export capabilities. |
| **Template Studio** | Single message text entry | Template Library with Variable Pills & Spintax Tester | **Extend** | Stores named reusable templates with dynamic variable insertion (`{name}`, `{phone}`, `{company}`). |
| **Background Job Queue** | Ad-hoc Python daemon threads | State-managed Job Queue with Persistent History | **Extend** | Formalizes job lifecycle (`queued`, `running`, `paused`, `completed`, `cancelled`) with ETA and report export. |
| **Browser Management** | Implicit Chrome launch in thread | `/api/browser/status`, `/api/browser/start`, `/restart` | **Extend** | Allows users to check QR code readiness, restart sessions, and clear user profiles cleanly via UI. |
| **Desktop Auto-Updater** | `updater.py` (Tkinter popup + ZIP extraction)| Background Update Check API + Manual Trigger | **Refactor** | Keeps update checking logic, but surfaces release notes and update readiness via web dashboard banner. |
| **Tkinter Direct Loop** | `root.mainloop()` | Uvicorn ASGI Server (`http://localhost:8000`) | **Retire** | Desktop GUI event loop retired in favor of browser-based HTTP/WebSocket runtime. |

---

## 2. Target Architecture Overview

```
+-------------------------------------------------------------------------+
|                         Web Browser (Client)                            |
|  - Modern Dashboard UI (HTML5, Modern CSS, ES6+)                        |
|  - Tabs: Overview, Contacts, Templates, Campaigns, Jobs, Logs, Settings  |
|  - Real-time updates via WebSocket / SSE                                 |
+-------------------------------------------------------------------------+
                                    |
                            HTTP / WebSockets
                                    |
+-------------------------------------------------------------------------+
|                        FastAPI ASGI Backend                             |
|  - Application Entry: backend/app.py (Uvicorn on 127.0.0.1:8000)        |
|  - Routers:                                                             |
|      /api/contacts    -> Ingestion, phone cleaning, column mapping      |
|      /api/templates   -> Template CRUD, dynamic variables, Spintax      |
|      /api/campaigns   -> Validation, dry-run simulation, staging        |
|      /api/jobs        -> Queue, execution, pause, resume, cancel, report|
|      /api/config      -> Settings, safety presets (Safe, Balanced, Fast)|
|      /api/browser     -> Chrome status, QR readiness, restart           |
|      /api/logs        -> Audit logs, level filtering                    |
|      /ws              -> Live telemetry & log streaming                 |
+-------------------------------------------------------------------------+
       |                                                    |
       v                                                    v
+-----------------------------+             +-----------------------------+
|   SQLite Data Store         |             |  Automation Worker & Adapter|
|   (whatsapp_web.db)         |             |  - Background Job Worker    |
|  - Contacts & Groups        |             |  - MessagingProvider (ABC)  |
|  - Reusable Templates       |             |  - WhatsAppWebAdapter       |
|  - Campaigns & Jobs         |             |    (wraps WhatsAppEngine)   |
|  - Audit Log History        |             |  - MockMessagingProvider    |
+-----------------------------+             +-----------------------------+
                                                            |
                                                            v
                                            +-----------------------------+
                                            | Chrome / Selenium WebDriver |
                                            | (Headless or Visible)       |
                                            +-----------------------------+
```

---

## 3. Data Migration and Backward Compatibility

### 3.1 Existing Contact Files Preservation
- Existing `.xlsx`, `.xls`, and `.csv` files (e.g., `contacts_sample.xlsx`, `contacts_sample.csv`, `Customer bulk email data.xlsx`) remain completely intact on the filesystem.
- The web dashboard allows users to either import them into the internal SQLite database or upload and map any new file dynamically.

### 3.2 Configuration Continuity
- `config.json` and `update_config.json` remain backward compatible with `ConfigManager`.
- When settings are modified in the Web UI, `ConfigManager` persists updates to `config.json`. The CLI and legacy scripts (`run.py`) continue to read the exact same settings.

### 3.3 CLI Tooling Continuity
- The command-line interface (`run.py`) retains its full standalone capability:
  - `python run.py --dry-run`
  - `python run.py --validate`
  - `python run.py --preset safe`
  - `python run.py --device-info`
- The CLI does not require the web server to be running.

---

## 4. Rollback and Fallback Plan

1. **Dual Run Availability:**
   - The desktop GUI (`gui.py`) is preserved intact in the repository during the transition.
   - If an operator requires the desktop interface, running `python gui.py` immediately launches the legacy Tkinter interface.
2. **Dedicated Launcher Scripts:**
   - `web_run.py`: Primary launcher for the modern web dashboard.
   - `run.py`: Primary launcher for automated CLI dispatches.
   - `run.bat`: Interactive menu offering options:
     1. Modern Web Dashboard (`web_run.py`) [Default]
     2. Pre-Flight Validation CLI
     3. Dry-Run Simulation CLI
     4. Legacy Desktop GUI (`gui.py`)
3. **Database Isolation:**
   - The SQLite database file `whatsapp_web.db` is purely additive. Deleting or moving this file has zero negative effect on existing Excel/CSV files.

