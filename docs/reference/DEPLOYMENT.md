# Deployment and Operations Guide: WhatsApp Bulk Messenger Pro

This guide covers installation, environment configuration, startup procedures, dual-mode operation, and maintenance workflows for the WhatsApp Automation Web Dashboard.

---

## 1. System Requirements

- **Operating System:** Windows 10, Windows 11, or Windows Server 2019+.
- **Python Runtime:** Python 3.10, 3.11, 3.12, 3.13, or 3.14 (64-bit).
- **Web Browser:** Google Chrome (latest stable release recommended).
- **Memory & Storage:** 4 GB RAM minimum (8 GB recommended); 500 MB free disk space.
- **Network:** Outbound HTTPS access to `web.whatsapp.com` and PyPI for package installation.

---

## 2. Quick-Start (1-Click Launch)

### Option A: Interactive Batch Launcher (`run.bat`)
Double-click `run.bat` from Windows File Explorer or execute from PowerShell/CMD:
```cmd
run.bat
```
The batch script will:
1. Verify Python installation (or offer silent automated installation).
2. Check and install missing dependencies from `requirements.txt`.
3. Present the interactive launch menu:
   - `[1] Modern Web Dashboard (Default - Recommended)`
   - `[2] CLI Dry-Run Simulation`
   - `[3] CLI Pre-Flight Validation`
   - `[4] Legacy Desktop GUI (Tkinter)`
4. Launch the web server on `http://127.0.0.1:8000` and automatically open your default browser.

### Option B: Direct Python Execution
```cmd
python web_run.py
```

---

## 3. Command-Line Options & Flags

### 3.1 Web Launcher (`web_run.py`)
| Argument | Default | Description |
| :--- | :--- | :--- |
| `--host` | `127.0.0.1` | Network interface to bind. Defaults strictly to localhost for security. |
| `--port` | `8000` | HTTP port to listen on. |
| `--no-browser` | `False` | Disables automatic browser opening upon server start. |
| `--reload` | `False` | Enables auto-reload for frontend and backend development. |

Example:
```cmd
python web_run.py --port 8080 --no-browser
```

### 3.2 Standalone CLI Operations (`run.py`)
The platform retains standalone command-line capabilities that execute in seconds without launching the web server:

```cmd
# 1. Pre-flight sanity audit
python run.py --validate

# 2. Dry-run simulation (no browser opened)
python run.py --dry-run

# 3. Automatic dispatch with specific anti-ban preset
python run.py --auto --preset safe

# 4. Automatic dispatch with deduplication enabled
python run.py --auto --dedupe

# 5. Display hardware diagnostics & device fingerprint
python run.py --device-info
```

### 3.3 Fallback to Legacy Desktop GUI
To access the original Tkinter desktop interface:
```cmd
python gui.py
```

---

## 4. Storage & Persistence Architecture

### 4.1 SQLite Database (`whatsapp_web.db`)
- Created automatically in the project root on first launch.
- Stores all contacts, audience groups, reusable templates, campaign configurations, and historical delivery logs.
- Thread-safe and resilient against application termination.
- **Backup:** Simply copy `whatsapp_web.db` to a backup location.

### 4.2 Chrome Profile Directory (`whatsapp_user_data/`)
- Stores WhatsApp Web session cookies, local storage, and service worker caches.
- Ensures operators do not need to scan the QR code on every launch.
- Located in `%LOCALAPPDATA%\whatsapp_automation_user_data` or project directory.

### 4.3 Log Files (`whatsapp_automation.log`)
- Managed by `logger.py` using `RotatingFileHandler`.
- Rotates automatically at 5 MB with a maximum of 3 backup generations.
- Contains PII-masked logs protecting phone numbers and recipient names.

---

## 5. Troubleshooting & Maintenance

### 5.1 Port 8000 Already in Use
If another local service is using port 8000:
```cmd
python web_run.py --port 8080
```
Then navigate to `http://127.0.0.1:8080`.

### 5.2 Google Chrome / ChromeDriver Version Mismatches
Selenium 4.50+ features automatic driver management (`Selenium Manager`) which downloads and caches the matching ChromeDriver automatically. If Chrome does not start:
1. Ensure Google Chrome is installed in its standard path (`C:\Program Files\Google\Chrome\Application\chrome.exe`).
2. Delete the local `chromedriver.exe` in the project root to allow Selenium Manager to fetch the latest driver matching your Chrome version.

### 5.3 Resetting WhatsApp Web Session
If WhatsApp Web fails to load or becomes disconnected:
1. Open the Web Dashboard -> **Settings** tab.
2. Under **WhatsApp Browser Session**, click **Restart Browser**.
3. Scan the QR code using WhatsApp on your phone (Linked Devices -> Link a Device).

### 5.4 Database Reset / Fresh Start
To reset the database to factory seed data:
1. Stop the web server (Ctrl+C).
2. Delete or rename `whatsapp_web.db`.
3. Restart `web_run.py`. The database and default templates will regenerate automatically.

