# 06 — REST API & WebSocket Telemetry Reference

## 1. Overview & Protocol Architecture

The backend exposes a REST API at base URL `http://127.0.0.1:8000/api` alongside a full-duplex WebSocket hub at `ws://127.0.0.1:8000/ws`.

- **Transport:** HTTP/1.1 (JSON payloads) & WebSockets.
- **Content-Type:** `application/json` (with multipart/form-data for media & file uploads).
- **Error Format:** Consistent structured JSON errors:
  ```json
  {
    "code": "PROFILE_LOCKED",
    "message": "Selected profile is currently open in another Chrome window.",
    "action": "Close Chrome or use dedicated session",
    "detail": "lockfile is locked by process 14028"
  }
  ```

---

## 2. Browser & Connection Endpoints

### 1. `GET /api/browser-profiles`
Discovers installed local browsers and scans for profile folders.
- **Query Parameters:** `force_rescan` (boolean, optional)
- **Response (200 OK):**
  ```json
  {
    "browsers": [
      {
        "key": "chrome",
        "name": "Google Chrome",
        "installed": true,
        "exe_path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "profiles": [
          {
            "dir": "__dedicated__",
            "name": "Dedicated WhatsApp Session",
            "display_name": "Dedicated WhatsApp Session (Isolated)",
            "path": "C:\\...\\whatsapp_browser_session",
            "short_path": "whatsapp_browser_session",
            "availability": "available",
            "is_dedicated": true
          },
          {
            "dir": "Default",
            "name": "Personal Profile (Default)",
            "display_name": "Personal Profile",
            "path": "C:\\...\\User Data\\Default",
            "short_path": "~/AppData/Local/Google/Chrome/User Data/Default",
            "availability": "available",
            "is_dedicated": false
          }
        ]
      }
    ],
    "count": 1
  }
  ```

### 2. `GET /api/browser-connection/live`
Fetches a real-time snapshot of browser state from [`ConnectionMonitor`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/backend/connection_monitor.py).
- **Response (200 OK):**
  ```json
  {
    "state": "waiting_for_qr",
    "label": "Waiting for QR scan",
    "is_connected": false,
    "current_activity": "Waiting for QR scan — checking again in 2 seconds (Timeout: 172s)",
    "browser_key": "chrome",
    "browser_name": "Google Chrome",
    "profile_dir": "__dedicated__",
    "profile_name": "Dedicated WhatsApp Session",
    "is_dedicated": true,
    "last_checked_at": "2026-11-02T17:28:10.124510",
    "error_detail": "",
    "timeline": [
      {"id": "browser_launched", "label": "Browser launched", "status": "completed", "timestamp": "17:28:02"},
      {"id": "whatsapp_opened", "label": "WhatsApp Web opened", "status": "completed", "timestamp": "17:28:05"},
      {"id": "qr_detected", "label": "QR detected", "status": "completed", "timestamp": "17:28:09"},
      {"id": "login_confirmed", "label": "Login confirmed", "status": "pending", "timestamp": null},
      {"id": "connection_ready", "label": "Connection ready", "status": "pending", "timestamp": null}
    ],
    "actions": [
      {"id": "open_session", "label": "Open WhatsApp Web", "primary": true},
      {"id": "cancel", "label": "Cancel", "danger": true},
      {"id": "change_profile", "label": "Change profile"}
    ]
  }
  ```

### 3. `POST /api/browser-profile/dedicated`
Resets the messaging connection to the isolated, app-managed dedicated profile.
- **Response (200 OK):**
  ```json
  {
    "status": "success",
    "message": "Switched to dedicated WhatsApp session",
    "is_dedicated": true,
    "profile_name": "Dedicated WhatsApp Session"
  }
  ```

### 4. `POST /api/browser-profile/open`
Launches the browser with the currently configured profile and navigates to WhatsApp Web.
- **Request Body:**
  ```json
  {
    "browser": "chrome",
    "profile_dir": "__dedicated__",
    "headless": false
  }
  ```

### 5. `POST /api/browser-profile/test`
Non-destructively tests whether the selected profile directory is locked or accessible.
- **Request Body:** `{"browser": "chrome", "profile_dir": "Default"}`
- **Response (200 OK):**
  ```json
  {
    "is_locked": false,
    "status": "available",
    "message": "Profile directory is ready"
  }
  ```

---

## 3. Campaigns & Queue Execution Endpoints

### 1. `POST /api/campaigns/{id}/run`
Initiates campaign execution. If WhatsApp Web is not authenticated, places the job into `WAITING_FOR_CONNECTION`.
- **Response (200 OK):**
  ```json
  {
    "status": "queued",
    "job_id": "c4b91a2e",
    "campaign_name": "VIP Product Launch",
    "job_status": "WAITING_FOR_CONNECTION",
    "total_recipients": 50,
    "message": "Campaign queued. Waiting for WhatsApp Web connection..."
  }
  ```

### 2. `GET /api/jobs/active`
Retrieves live execution statistics for the currently active or waiting campaign.
- **Response (200 OK):**
  ```json
  {
    "active": true,
    "job": {
      "id": "c4b91a2e",
      "campaign_name": "VIP Product Launch",
      "status": "RUNNING",
      "total_count": 50,
      "sent_count": 14,
      "failed_count": 0,
      "suppressed_count": 1,
      "progress_percentage": 28.0,
      "current_recipient": "+1 415 ••• ••71",
      "last_action": "Dispatched message to +1 415 ••• ••71",
      "started_at": "2026-11-02T17:35:00"
    }
  }
  ```

### 3. `GET /api/jobs/{id}/queue`
Returns recipient-level detail records for the inspector drawer modal (`#modal-job-drawer`).
- **Response (200 OK):**
  ```json
  {
    "job_id": "c4b91a2e",
    "items": [
      {
        "id": 101,
        "recipient_name": "Alex Rivera",
        "recipient_phone": "+14155552671",
        "masked_phone": "+1 415 ••• ••71",
        "variant_purpose": "Executive Offer",
        "status": "SENT",
        "retry_count": 0,
        "error_message": "",
        "dispatched_at": "2026-11-02T17:35:12"
      }
    ]
  }
  ```

### 4. `POST /api/jobs/{id}/pause` & `POST /api/jobs/{id}/resume`
Controls active campaign execution safely without dropping or repeating recipients.

---

## 4. WebSocket Telemetry Hub (`/ws`)

### Connection Handshake
Clients connect to `ws://127.0.0.1:8000/ws`. The server accepts the socket and registers it with the centralized [`ConnectionManager`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/backend/routers/ws.py).

### Outbound Event Specifications

#### 1. `connection_status_change`
Broadcast whenever [`ConnectionMonitor`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/backend/connection_monitor.py) transitions state:
```json
{
  "event": "connection_status_change",
  "data": {
    "state": "connected",
    "label": "Connected",
    "is_connected": true,
    "current_activity": "WhatsApp Web session active and ready for messaging."
  }
}
```

#### 2. `job_progress`
Broadcast after each recipient dispatch attempt:
```json
{
  "event": "job_progress",
  "data": {
    "job_id": "c4b91a2e",
    "sent_count": 15,
    "total_count": 50,
    "failed_count": 0,
    "progress_percentage": 30.0,
    "current_recipient": "+1 415 ••• ••88"
  }
}
```

#### 3. `job_status_change`
Broadcast when a campaign starts, pauses, resumes, completes, or halts:
```json
{
  "event": "job_status_change",
  "data": {
    "job_id": "c4b91a2e",
    "status": "COMPLETED",
    "completed_at": "2026-11-02T17:42:15"
  }
}
```

