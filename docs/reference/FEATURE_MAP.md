# Feature Map: Desktop GUI to Web Dashboard

This document provides a comprehensive mapping of all capabilities from the original Python Tkinter desktop application to the modern Web Dashboard architecture.

---

## 1. Feature Status Legend
- **Active / Implemented:** Fully operational in the web dashboard.
- **Refactored:** Core business logic preserved and adapted into REST/WebSocket API endpoints.
- **Enhanced:** Significantly upgraded beyond the capabilities of the desktop GUI.
- **Preserved (Desktop):** Kept in legacy `gui.py` and `run.py` for backward compatibility.

---

## 2. Feature Mapping Matrix

| Feature Area | Desktop Feature (Legacy Tkinter) | Web Dashboard Equivalent | Status | Code Location |
| :--- | :--- | :--- | :--- | :--- |
| **Contact Ingestion** | File picker dialog for single Excel/CSV file | Multi-file upload, drag-and-drop, quick paste text dialog | **Enhanced** | `backend/routers/contacts.py`<br>`data_loader.py` |
| **Column Mapping** | Hardcoded synonym matching | Interactive column mapper modal with auto-detection | **Enhanced** | `backend/routers/contacts.py`<br>`backend/static/app.js` |
| **Phone Sanitization** | Automatic regex stripping during load | Interactive Phone Cleaner with live preview & validation | **Enhanced** | `data_loader.py`<br>`backend/routers/contacts.py` |
| **Deduplication** | None in original desktop (added in CLI) | Deduplication toggle with duplicate count breakdown | **Active** | `validator.py`<br>`backend/routers/campaigns.py` |
| **Contact Groups** | None (ephemeral session memory only) | Persistent SQLite Contact Groups & audience filters | **Enhanced** | `backend/database.py`<br>`backend/routers/contacts.py` |
| **Template Editing** | Single Tkinter `Text` box | Reusable Template Studio with dynamic variables & tags | **Enhanced** | `backend/database.py`<br>`backend/routers/templates.py` |
| **Variable Injection** | `{name}`, `{first_name}`, `{phone}` | Any CSV column as variable pill (`{company}`, `{bill}`, etc.) | **Enhanced** | `data_loader.py`<br>`backend/routers/templates.py` |
| **Spintax Variations** | `{Hi\|Hello}` processed at send time | Real-time Spintax tester with live sample generation | **Enhanced** | `whatsapp_engine.py`<br>`backend/routers/templates.py` |
| **Attachment Handling**| File dialog or attachment column in Excel | Drag-and-drop media upload + media preview badge | **Enhanced** | `backend/routers/campaigns.py` |
| **Safety Presets** | CLI flags (`--preset safe/balanced/fast`) | Visual Preset Cards with one-click activation & custom bounds | **Enhanced** | `config_manager.py`<br>`backend/routers/config.py` |
| **Pacing Controls** | Min/Max delay entry fields | Granular slider & number inputs with jitter preview | **Active** | `config_manager.py`<br>`backend/routers/config.py` |
| **Batch Cooldown** | Batch size & pause fields | Visual cooldown settings with estimated campaign duration | **Active** | `config_manager.py`<br>`backend/routers/config.py` |
| **Pre-Flight Validation** | CLI `--validate` check | Guided Pre-Flight Audit step with warnings and readiness score | **Enhanced** | `validator.py`<br>`backend/routers/campaigns.py` |
| **Dry-Run Simulation** | CLI `--dry-run` flag | Interactive Dry-Run Modal with simulated delivery table | **Enhanced** | `validator.py`<br>`backend/routers/campaigns.py` |
| **Campaign Wizard** | Single-screen overloaded layout | 5-Step Guided Campaign Wizard (Contacts -> Template -> Config -> Validate -> Launch) | **Enhanced** | `backend/static/app.js`<br>`backend/routers/campaigns.py` |
| **Job Execution** | Background daemon thread with Tkinter locks | Asynchronous Job Queue with state machine and persistent records | **Enhanced** | `backend/job_queue.py`<br>`backend/routers/jobs.py` |
| **Live Progress** | Basic percentage progress bar | Animated circular/linear progress, ETA, speed, and status counters | **Enhanced** | `backend/routers/ws.py`<br>`backend/static/app.js` |
| **Pause / Resume** | Pause button in GUI | Responsive Pause, Resume, and Cancel with interruptible sleep | **Active** | `whatsapp_engine.py`<br>`backend/routers/jobs.py` |
| **Execution Reports** | Generated timestamped CSV in project root | Persistent Job History + Downloadable CSV report via API | **Enhanced** | `backend/routers/jobs.py` |
| **Real-time Logs** | Tkinter `ScrolledText` widget | Filterable real-time WebSocket log terminal with level badges | **Enhanced** | `backend/routers/ws.py`<br>`backend/routers/logs.py` |
| **Hardware Telemetry** | Pop-up messagebox (`--device-info`) | Embedded System Telemetry card with CPU, RAM, OS, Device ID | **Enhanced** | `device_manager.py`<br>`backend/routers/browser.py` |
| **Browser Control** | Chrome opens automatically upon send | Manual Browser Session start, QR readiness checker, profile reset | **Enhanced** | `backend/routers/browser.py`<br>`browser_manager.py` |
| **Software Updates** | Tkinter popup on launch | Non-intrusive Update notification banner with release notes | **Refactored**| `updater.py`<br>`backend/routers/config.py` |
| **Theme / Appearance** | Fixed Dark Theme in Tkinter | Responsive Dark / Light mode toggle with persistent preference | **Enhanced** | `backend/static/styles.css` |
| **Legacy Desktop GUI** | Main GUI window (`gui.py`) | Preserved for fallback via `python gui.py` or `run.bat` option 4 | **Preserved** | `gui.py` |
| **Standalone CLI** | `run.py --dry-run / --auto` | Fully functional without launching web server | **Preserved** | `run.py` |

---

## 3. Web Dashboard Navigation Structure

1. **Dashboard Overview (`/`)**
   - KPI metrics: Total Contacts, Campaigns Run, Success Rate, Engine Health.
   - Active Job Banner with live progress.
   - Quick Launch actions (New Campaign, Add Contacts, New Template).
   - Recent Activities feed.
2. **Contacts Hub (`#contacts`)**
   - Contact list table with pagination, search, and tag filters.
   - Ingestion tools: Upload CSV/Excel, Paste Text dialog, Phone Cleaner tool.
   - Column mapping interface.
   - Export contacts to CSV.
3. **Template Studio (`#templates`)**
   - Saved templates grid/list.
   - Template editor with dynamic variable insertion helper.
   - Spintax playground and live generator preview.
4. **Campaign Wizard (`#campaigns`)**
   - Step 1: Select or Upload Audience.
   - Step 2: Choose Template & Media Attachment.
   - Step 3: Choose Anti-Ban Preset & Timing.
   - Step 4: Run Pre-Flight Validation & Dry-Run.
   - Step 5: Review & Dispatch.
5. **Job Monitor (`#jobs`)**
   - Active and historical job cards.
   - Real-time gauge: Sent, Failed, Remaining, Total.
   - Live transmission feed per contact.
   - Controls: Pause, Resume, Abort / Cancel.
   - Export detailed delivery report.
6. **Audit Logs (`#logs`)**
   - Live WebSocket stream terminal.
   - Filter by log level (DEBUG, INFO, WARNING, ERROR).
   - Search log messages.
7. **Settings & Presets (`#settings`)**
   - Built-in Anti-Ban Presets: Safe, Balanced, Fast.
   - Custom delay configurations and bounds.
   - Browser & Profile Manager: Clear cache, check QR status.
   - System Diagnostics: Machine ID, CPU, Memory.
