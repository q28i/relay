# Relay Desktop — Self-Update & Release Guide

## Automatic Update System

Relay features a built-in, non-intrusive self-update engine that distributes verified updates directly from GitHub Releases (`github.com/q28i/relay`).

---

## How It Works

1. **GitHub Releases API Polling**:
   Relay queries `GET https://api.github.com/repos/q28i/relay/releases/latest` to check for newer published semver releases (`tag_name > current_version`).
2. **Background Streaming**:
   When the user clicks **Download Update**, Relay downloads the setup package to `%LOCALAPPDATA%\Relay\updates\` in chunks while calculating the SHA-256 hash.
3. **Dispatch Protection (Campaign Safety Guard)**:
   Relay strictly forbids initiating updates or restarts while an active WhatsApp dispatch campaign is running (`job_worker.get_active_job()`).
   Users are alerted to pause or wait for the campaign to finish.
4. **Seamless Inno Setup Handover**:
   When **Install & Restart** is clicked:
   - Relay spawns the update installer with `/CLOSEAPPLICATIONS /RESTARTAPPLICATIONS`.
   - Relay cleanly shuts down its background processes.
   - Inno Setup upgrades the program files in `%LOCALAPPDATA%\Programs\Relay\`.
   - Inno Setup relaunches Relay automatically upon completion.

---

## Performing an Update via UI

1. Navigate to the **Settings** tab in Relay.
2. Scroll to the **Application Updates** card.
3. Click **Check for Updates**.
4. If an update is available:
   - Review the **What's New** release notes directly in the card.
   - Click **Download Update**.
   - Monitor the live download progress bar.
5. Once downloaded, click **Install & Restart**.
6. Follow the brief installer prompt. Relay will reopen with your latest version!

---

## Data Preservation Guarantee

Relay enforces total separation between application code and user data:
- Application binaries: `%LOCALAPPDATA%\Programs\Relay\`
- User database, cookies, sessions, media, and contacts: `%LOCALAPPDATA%\Relay\`

**Updates never overwrite, reset, or delete your user data directory.**
Your WhatsApp connection and existing contact records will remain ready to send immediately after updating.

---

## Manual Update Procedure

If you prefer to update manually:
1. Download the latest `Relay-Setup-vX.Y.Z-Windows-x64.exe` from GitHub Releases.
2. Close any running Relay browser tabs or background processes.
3. Run the installer. It will automatically detect your existing installation and update the application files in `%LOCALAPPDATA%\Programs\Relay\` without touching your data.
