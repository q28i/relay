# Security, Privacy & Operational Safety Policy

This document describes Relay's security posture, privacy safeguards, credential isolation rules, and operational boundaries.

---

## 1. Authentication & Session Credential Isolation

Relay manages persistent WhatsApp Web sessions using a dedicated Chromium user-data directory:
- **Storage Location**: `whatsapp_browser_session/`
- **Contents**: Chromium IndexedDB, LocalStorage, cookies, service workers, and session caches.
- **Security Boundary**:
  - The `whatsapp_browser_session/` directory is strictly ignored in `.gitignore`.
  - Session files are never tracked, committed, or pushed to any Git remote.
  - No remote server, cloud API, or third-party service receives session tokens or authentication state. All authentication remains purely local to the operator's machine.

---

## 2. Contact Privacy & Privacy Masking

Customer contact records imported into Relay are stored in local SQLite databases (`relay_app.db` or `whatsapp_automation.db`):
- **Phone Number Redaction in Logs**:
  All system audit logs, console outputs, and WebSocket messages apply privacy masking:
  ```text
  +91 98765 43210  -->  +91 ***** *3210
  ```
- **Local Isolation**:
  Contact spreadsheets (`.csv`, `.xlsx`) and SQLite database files are excluded from version control via `.gitignore`.
- **Opt-Out & Suppression Lists**:
  Relay maintains a permanent `suppression_list` table. When a contact opts out, their number is recorded. The dispatch worker queries this table before every send, unconditionally skipping suppressed recipients to respect customer consent.

---

## 3. Media Storage & Data Integrity

- **Upload Directory**: Stored under `uploads/media/` and tracked via `media_assets` table.
- **Hash-Based Deduplication**: When an asset is uploaded, Relay computes its `SHA256` content hash. If an identical file exists, Relay reuses the existing asset record to prevent duplicate storage.
- **MIME Validation**: Uploaded files are verified using extension checks and header inspection. Non-media files (e.g., executables, scripts) are rejected.
- **Version Control Exclusion**: `uploads/` is excluded in `.gitignore` to prevent leaking private business media.

---

## 4. Operational Safety & Anti-Ban Controls

Automating WhatsApp Web entails operational risks regarding WhatsApp's Terms of Service and spam detection algorithms. Relay incorporates explicit defensive engineering:

1. **Human Pacing Jitter**: Enforces randomized delays between consecutive messages (8.0 to 15.0 seconds).
2. **Batch Cooldown Pauses**: Halts dispatch after batches of 20 messages for 60 to 90 seconds.
3. **Daily Volume Limits**: Restricts overall daily volume to manageable thresholds.
4. **Zero-Duplicate Protection (`RECONCILIATION_REQUIRED`)**:
   - If an outgoing message's delivery receipt cannot be confirmed, Relay marks the item `UNCERTAIN` and halts the campaign immediately.
   - Uncertain sends are never auto-retried.
   - This prevents accidental spam loops or double-messaging customers.

---

## 5. Repository Hygiene Checklist

Developers and operators working on Relay must ensure:
- [x] Never commit `whatsapp_browser_session/`, `*.db`, `*.session`, or `auth_config.json`.
- [x] Never commit customer `.csv` or `.xlsx` files.
- [x] Never commit test media containing personal or private information.
- [x] Never log unmasked phone numbers or message contents in public repositories.
- [x] Always verify `git status` before pushing to ensure only documentation and sanitized source code are tracked.
