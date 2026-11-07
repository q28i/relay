# Relay Desktop — Packaging Architecture & Build Specification

## Overview

Relay packages as a high-performance Windows desktop application using:
1. **PyInstaller 6.x (`onedir` mode)** — Extracts python binaries, FastAPI ASGI server, Selenium, dependencies, and frontend static assets into an optimized folder bundle.
2. **Inno Setup 6.x (LZMA2 Ultra64)** — Compiles the `onedir` folder bundle into a single self-contained installer (`Relay-Setup-v2.0.0-Windows-x64.exe`).

---

## 1. Storage Isolation Architecture (`backend/paths.py`)

A fundamental requirement for commercial-grade desktop applications is the strict separation between read-only application code and writable user state:

```
%LOCALAPPDATA%\Programs\Relay\          <-- READ-ONLY (Application binaries & assets)
  ├── Relay.exe
  ├── _internal/
  │   ├── python314.dll
  │   ├── backend/static/ (HTML, JS, CSS)
  │   └── libraries...
  └── unins000.exe

%LOCALAPPDATA%\Relay\                   <-- PERSISTENT USER DATA (Never wiped on updates)
  ├── whatsapp_web.db                   (SQLite database: contacts, templates, jobs)
  ├── whatsapp_browser_session\         (Chromium persistent WhatsApp Web cookies)
  ├── uploads\media\                    (User approved media assets)
  ├── config.json                       (User throttles, country code, options)
  ├── relay_runtime.json                (Active port & process tracking)
  └── logs\                             (System & dispatch logs)
```

### Dynamic Path Resolution:
- `is_frozen()`: Checks `getattr(sys, 'frozen', False)`.
- In development/testing: Paths point to the repository root for developer convenience and test backwards compatibility.
- When packaged: Resolves paths dynamically against `%LOCALAPPDATA%\Relay`. Can be overridden with `RELAY_USER_DATA_DIR`.

---

## 2. Desktop Launcher (`relay_launcher.py`)

The desktop launcher is the primary entry point for `Relay.exe`:
- **Single-Instance Mutex**: Acquires `Global\RelayWhatsAppAutomationMutex` (or `Local\RelayWhatsAppAutomationMutex`). If another instance is running, it opens the existing browser dashboard and terminates immediately.
- **Dynamic Port Selection**: Tests `127.0.0.1:8000`. If occupied by another program, automatically finds the next available port in `8001–8010`.
- **Healthcheck Polling**: Polls `/api/health` before opening the user's default browser.
- **Clean Teardown**: Intercepts SIGINT/SIGTERM, removes runtime lockfiles, and releases the mutex.

---

## 3. PyInstaller Spec (`relay.spec`)

Key optimizations:
- `console=False`: Suppresses the black terminal window.
- `upx=False`: Prevents false-positive antivirus triggers from UPX decompression heuristics.
- Selective pruning: Excludes unneeded packages (`pytest`, `unittest`, `tkinter`, `matplotlib`, `scipy`, `pandas`) to reduce footprint.
- Bundles `backend/static/` and `assets/relay.ico`.

---

## 4. Inno Setup Compiler (`Relay-Setup.iss`)

Key features:
- `PrivilegesRequired=lowest`: Per-user non-admin installation into `{localappdata}\Programs\Relay`. Users do not need Administrator credentials.
- `Compression=lzma2/ultra64`: Maximum solid compression producing a lightweight ~31 MB installer.
- `CloseApplications=yes`: Automatically closes older Relay instances during upgrade and restarts them after installation.
- Preserves User Data: The installer and uninstaller exclusively modify `{app}` and never delete `{localappdata}\Relay`.

---

## 5. Automated Build Pipeline (`build_installer.py`)

Run:
```powershell
python build_installer.py
```
Outputs:
- `dist/Relay-Setup-v2.0.0-Windows-x64.exe`
- `dist/SHA256SUMS.txt`
