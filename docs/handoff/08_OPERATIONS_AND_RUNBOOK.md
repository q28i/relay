# 08 — Operations & Troubleshooting Runbook

## 1. System Requirements & Environment Setup

### Minimum Host Requirements
- **Operating System:** Windows 10 or Windows 11 (64-bit).
- **Python Runtime:** Python 3.10 through 3.14 (64-bit).
- **Browser:** At least one supported Chromium browser installed (Google Chrome recommended, Microsoft Edge, or Brave).
- **Hardware:** Minimum 4GB RAM (8GB recommended), 200MB free disk space.

### Initial Installation
From the project root:
```bash
# 1. Create and activate a Python virtual environment (optional but recommended)
python -m venv venv
.\venv\Scripts\activate

# 2. Install required Python packages
pip install -r requirements.txt
```

---

## 2. Starting the Application

### Method 1: One-Click Startup Script (Recommended)
Double-click [`start_dashboard.bat`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/start_dashboard.bat) or execute from PowerShell:
```cmd
.\start_dashboard.bat
```
*This script checks for Python, installs any missing packages, launches the FastAPI server on port 8000, and automatically launches your default web browser to `http://127.0.0.1:8000`.*

### Method 2: Manual Terminal Execution
```bash
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```
To enable auto-reload during development:
```bash
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```

---

## 3. Configuration Management (`config.json`)

All runtime options are stored in [`config.json`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/config.json) in the project root:

```json
{
  "browser": "chrome",
  "profile_dir": "__dedicated__",
  "profile_name": "Dedicated WhatsApp Session",
  "theme": "void",
  "min_delay": 8.0,
  "max_delay": 15.0,
  "batch_size": 20,
  "batch_pause": 60.0,
  "daily_cap": 100,
  "privacy_mode": true
}
```

### Parameter Explanations:
- `browser`: Default browser engine (`chrome`, `edge`, `brave`, `firefox`).
- `profile_dir`: Directory identifier (`__dedicated__` for isolated session, or folder name like `Default`).
- `profile_name`: User-facing label displayed in the header strip.
- `theme`: Active interface theme (`system`, `light`, `void`).
- `min_delay` / `max_delay`: Pacing range in seconds between individual WhatsApp message dispatches.
- `batch_size`: Number of messages sent before pausing for a cooldown period.
- `batch_pause`: Length of batch pause in seconds (anti-ban cooling period).
- `daily_cap`: Maximum recipients permitted across all campaigns per calendar day.
- `privacy_mode`: Masks phone numbers in activity tables and telemetry feeds (`+1 415 ••• ••71`).

---

## 4. Database Maintenance & Backups

The primary database is stored at [`whatsapp_web.db`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/whatsapp_web.db).

### Creating a Hot Backup:
```bash
# SQLite supports hot copying while the application is active
copy whatsapp_web.db whatsapp_web_backup_%date%.db
```

### Database Self-Healing:
If `whatsapp_web.db` is deleted or corrupted, [`DatabaseManager`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/backend/database.py) will automatically re-create all required tables, indexes, and default groups upon server startup.

---

## 5. Dedicated Browser Session Management

Dedicated profile data is stored in the local directory:
`whatsapp_browser_session/`

- **Preserving Authentication:** Keep this directory intact to avoid having to re-scan the WhatsApp QR code.
- **Resetting Authentication:** To completely wipe the dedicated session and generate a fresh QR login, either:
  1. Click **Reset dedicated session** in **Settings → Messaging Connection**.
  2. Or stop the server and delete the `whatsapp_browser_session/` directory.

---

## 6. Operational Incident Troubleshooting

### Incident 1: "Profile is currently open in Chrome" (`PROFILE_LOCKED`)
- **Cause:** You selected an existing Chrome profile (`Default`), but a normal Google Chrome window is open on your desktop. Chromium enforces single-process exclusive locks.
- **Resolution:**
  1. Click the primary button **"Use dedicated session"** to switch to the isolated app profile without closing your personal Chrome.
  2. Or close all open Chrome windows and click **"I closed Chrome — try again"**.

---

### Incident 2: Port 8000 Conflict (`WinError 10048`)
- **Cause:** Another process or a previous orphaned uvicorn instance is holding port 8000.
- **Resolution:**
  In PowerShell:
  ```powershell
  # Find PID using port 8000
  netstat -ano | findstr :8000
  # Terminate the process (replace PID with actual number, e.g. 23976)
  taskkill /F /PID 23976
  ```

---

### Incident 3: Campaign Shows "Waiting for QR scan" and Does Not Send
- **Cause:** This is the designed **Pre-Flight Connection Gate**. The system intentionally refuses to burn contacts while WhatsApp Web is unauthenticated.
- **Resolution:**
  1. In the connection card, click **Open WhatsApp Web**.
  2. Point your mobile phone camera at the QR code in WhatsApp → Linked Devices.
  3. Once scanned, the system will detect the login, transition to `Connected`, and **automatically begin sending without restarting the campaign**.

---

### Incident 4: Browser Driver Incompatibility
- **Cause:** Chrome updated on Windows, but the local chromedriver executable is older.
- **Resolution:**
  Selenium 4.x includes built-in Selenium Manager that automatically retrieves the matching driver for your installed Chrome version. Ensure internet connectivity on first run, or delete any stale `chromedriver.exe` in the root folder so Selenium Manager handles driver resolution.

