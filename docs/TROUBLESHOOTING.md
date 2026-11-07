# Relay Desktop — Troubleshooting Guide

## 1. Windows SmartScreen Warning ("Windows protected your PC")

### Why does this happen?
When an open-source or newly released application is downloaded, Windows SmartScreen checks its reputation. Until the release builds up installation volume or is signed with an EV Code Signing Certificate, Windows displays an informational advisory:
`Windows protected your PC: Microsoft Defender SmartScreen prevented an unrecognized app from starting.`

### Resolution:
1. On the SmartScreen prompt, click **"More info"**.
2. Click the **"Run anyway"** button that appears.
3. The Relay installer will proceed with installation normally.
4. Relay runs completely offline and locally on `127.0.0.1` with zero cloud tracking.

---

## 2. Port Conflicts (e.g. "Port 8000 already in use")

### How Relay handles this automatically:
Relay features dynamic port conflict resolution:
- If port 8000 is occupied by an existing Relay process, it automatically brings your browser to that window and exits.
- If port 8000 is occupied by a different program (e.g. another local web server), Relay automatically binds to the next available port in the range 8001–8010.
- Relay writes the active port and URL to `%LOCALAPPDATA%\Relay\relay_runtime.json`.

---

## 3. WhatsApp Web Browser Session Conflicts

### Symptoms:
- Error message: `Profile is currently in use by an active browser window`.
- WhatsApp asks for QR scan again.

### Why this happens:
WhatsApp Web strictly allows one browser window per user data directory. If your personal Chrome is already running with the same profile directory, Chromium places a lock file on disk (`lockfile` / `SingletonLock`).

### Resolution:
1. Always use **Relay Automation Session (Dedicated Profile)** in **Settings**.
2. Relay isolates its session under `%LOCALAPPDATA%\Relay\whatsapp_browser_session`.
3. This allows your personal Chrome browser and Relay's automated browser to run side-by-side simultaneously without interfering with each other.

---

## 4. Where are Relay logs located?

When diagnosing issues or contacting support:
- Application logs: `%LOCALAPPDATA%\Relay\logs\`
- Runtime state: `%LOCALAPPDATA%\Relay\relay_runtime.json`
- Database: `%LOCALAPPDATA%\Relay\whatsapp_web.db`
- Browser Session: `%LOCALAPPDATA%\Relay\whatsapp_browser_session\`
