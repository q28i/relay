# Relay Desktop — Installation Guide

## Overview

Relay is a modern, privacy-first desktop automation platform for WhatsApp bulk messaging, contact management, and multimedia campaigns.

With Relay v2.0, no manual Python, pip, Node.js, virtual environment, or terminal commands are required for end users. The application ships as a standalone Windows installer.

---

## System Requirements

- **Operating System**: Windows 10 (64-bit) or Windows 11 (64-bit)
- **Browser**: Google Chrome, Microsoft Edge, or Brave Browser installed
- **Disk Space**: ~250 MB free space
- **Permissions**: Standard user account (no Administrator / UAC rights required)

---

## Installation Steps

### 1. Download Installer
Download the latest `Relay-Setup-vX.Y.Z-Windows-x64.exe` installer from the official repository:
👉 [https://github.com/q28i/relay/releases/latest](https://github.com/q28i/relay/releases/latest)

### 2. Run the Installer
Double-click `Relay-Setup-vX.Y.Z-Windows-x64.exe`.
- The installer installs into your personal user directory:
  `%LOCALAPPDATA%\Programs\Relay\`
- Because it installs per-user, no Administrator prompt or system-wide modifications occur.

*(Note: If Windows SmartScreen appears because this is a newly released build, click **"More info"** and then **"Run anyway"**.)*

### 3. Launch Relay
At the end of installation:
- Keep **"Launch Relay"** checked and click **Finish**, OR
- Launch **Relay** anytime from your Start Menu or Desktop shortcut.

### 4. First-Time Setup & WhatsApp Pairing
1. Relay starts its local background engine and automatically opens your default web browser at `http://127.0.0.1:8000`.
2. Go to the **Settings** tab.
3. Select your installed browser (e.g. Chrome) and ensure **"Relay Automation Session"** is selected.
4. Scan the WhatsApp Web QR code once with your phone.
5. Once connected, your session is saved permanently in `%LOCALAPPDATA%\Relay\whatsapp_browser_session`. You will not need to scan the QR code again.

---

## Directory Architecture

| Directory | Location | Purpose |
|---|---|---|
| **Program Files** | `%LOCALAPPDATA%\Programs\Relay\` | Application binaries, libraries, frontend assets. Read-only. Updated during releases. |
| **User Data** | `%LOCALAPPDATA%\Relay\` | Database (`whatsapp_web.db`), uploaded media (`uploads/`), browser authentication session (`whatsapp_browser_session/`), and logs. **Never deleted or overwritten during updates.** |

---

## Uninstallation

To uninstall Relay:
1. Open Windows **Settings** &rarr; **Apps** &rarr; **Installed apps**.
2. Find **Relay** and click **Uninstall**.
3. All program binaries in `%LOCALAPPDATA%\Programs\Relay\` will be cleanly removed. Your personal contacts and WhatsApp database in `%LOCALAPPDATA%\Relay\` remain preserved unless you choose to delete them manually.
