# Document 11: Browser Conflict Resolution & Intelligent Session Lifecycle Manager

## 1. Overview & Problem Definition

Previously, Relay could report that a selected Chrome, Edge, or Brave profile was already running and refuse to establish an automated messaging session. This occurred because:
1. Relay treated its own previous automation processes identically to personal user browser windows.
2. Stale process trees or crashed sessions left Chromium lockfiles without an active process.
3. No distinction existed between active visible personal windows, orphaned automation background processes, and Relay-owned sessions.
4. Users were blocked unless they manually terminated processes or switched profiles.

**Delivered Solution:**
Relay now features **Intelligent Automatic Conflict Resolution and Session Lifecycle Management**:
- **Automatic Resolution for Relay Sessions:** When Relay detects a conflicting browser instance that was previously launched and owned by Relay, it automatically terminates that process tree gracefully (`WM_CLOSE` followed by tree termination), waits for the profile to unlock, and restarts cleanly.
- **Strict Protection for Personal Browsers:** If a personal browser window is running the selected profile, Relay **never** force-kills or runs indiscriminate commands like `taskkill /F /IM chrome.exe`. Instead, it displays an accessible confirmation modal (`#modal-confirm-browser-restart`) warning the user that restarting will close open windows and unsaved tabs.
- **Targeted Scope:** If another Chrome profile is running (e.g. personal profile running while Relay is configured to use a work profile), that other profile is left untouched. Relay inspects `--user-data-dir` and profile directories to isolate only the target profile.
- **Healthy Session Reuse:** When `Start Session` or `Test Connection` is clicked while a live, responsive Relay session already exists, Relay reuses that session immediately rather than relaunching.
- **Concurrency Mutex:** Launch/restart mutex prevents race conditions from double-clicks or duplicate requests.
- **Zero-Message Verification:** `Test Connection` strictly tests session connectivity and auth state without queuing or dispatching messages.

---

## 2. Architectural Components

```
┌────────────────────────────────────────────────────────────────────────┐
│                        User Interface (Web UI)                         │
│  - Start Session Button & Test Connection Button                       │
│  - Personal Browser Restart Confirmation Modal (#modal-confirm-...)    │
│  - 6-State Connection Progress Stepper & Live Activity Timeline        │
└─────────────────────────────────┬──────────────────────────────────────┘
                                  │ POST /api/browser-session/start
                                  │ POST /api/browser-session/confirm-restart
                                  │ POST /api/browser-profile/test
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│                 SessionLifecycleManager (Singleton)                    │
│  - Concurrency Lock (threading.Lock mutex)                             │
│  - Metadata Persistence: whatsapp_browser_session/relay_session.json   │
│  - Process Tree Tracking (Driver PID, Browser PID, Child PIDs)         │
│  - Ownership Detection via PID, Creation Time & --relay-session-id     │
│  - Win32 Graceful Window Messaging (ctypes WM_CLOSE = 0x0010)          │
│  - Orphaned Process Recovery on Startup                                │
└───────────────────┬───────────────────────────────┬────────────────────┘
                    │                               │
                    ▼                               ▼
┌───────────────────────────────────┐ ┌──────────────────────────────────┐
│          BrowserManager           │ │        ConnectionMonitor         │
│ - diagnose_profile(..., is_relay) │ │ - 6-State Progression Engine     │
│ - resolve_conflict(...)           │ │ - Real-time QR / Login Observer  │
│ - launch_driver(..., session_id)  │ │ - Dynamic State Actions          │
└───────────────────────────────────┘ └──────────────────────────────────┘
```

---

## 3. The 10-Scenario Verification Matrix

All 10 scenarios required by the system contract have been implemented and verified in `tests/test_browser_conflict_resolution.py`:

| # | Scenario | Expected Behavior | Implementation & Safety Mechanism | Status |
|---|---|---|---|---|
| **1** | **No browser running** | Launches cleanly | `diagnose_profile` finds no conflict (`conflict_type: "none"`). Driver initializes, navigates to WhatsApp Web, and monitors login. | ✅ Verified |
| **2** | **Previous Relay browser running** | Automatically restarts | Detected via `--relay-session-id` and session metadata (`conflict_type: "relay_owned"`). Gracefully terminates previous session tree, releases profile lock, and restarts without prompting. | ✅ Verified |
| **3** | **Existing Relay session healthy** | Reuses without restart | `session_lifecycle.is_session_healthy(driver)` verifies active window handles and URL responsiveness. Reuses live session immediately without relaunching. | ✅ Verified |
| **4** | **Personal profile open** | Obtains confirmation first | Detected as `conflict_type: "personal_browser"`. Returns `prompt_required: True`. Web UI displays `#modal-confirm-browser-restart`. Sends `WM_CLOSE` only after explicit confirmation; never force-kills. | ✅ Verified |
| **5** | **Another profile running** | Leaves untouched | Matches against target `--user-data-dir` and profile name. Processes running other profiles are ignored completely. | ✅ Verified |
| **6** | **Stale profile lock** | Handles safely | Lock file present on disk without running process is flagged as `is_stale_lock: True`. Safely bypassed or cleaned without claiming the profile is in use. | ✅ Verified |
| **7** | **Browser launch failure** | Reports real cause | If binary is missing or launch times out, returns `LAUNCH_FAILED` with structured diagnostic reason and `View details` support. | ✅ Verified |
| **8** | **Relay restart with orphan** | Recovers safely | `recover_orphaned_session()` inspects `relay_session.json` against live PIDs and `--relay-session-id`. Cleanly terminates orphaned tree so new session starts cleanly. | ✅ Verified |
| **9** | **Repeated Start clicks** | No duplicate instances | `acquire_launch_lock(timeout=10.0)` blocks concurrent launches. Double-clicks wait or return current progress safely. | ✅ Verified |
| **10**| **Test Connection** | Never sends messages | Strictly probes launcher and WhatsApp Web DOM authentication; never calls message cleaners, queue dispatchers, or test-send logic. | ✅ Verified |

---

## 4. API Endpoints Reference

### `POST /api/browser-session/start`
Primary entry point for starting or reconnecting a browser session.
- **Request Body (optional):**
  ```json
  {
    "browser": "chrome",
    "profile_dir": "__dedicated__",
    "force_restart": false,
    "headless": false
  }
  ```
- **Response:**
  ```json
  {
    "success": true,
    "message": "Opening https://web.whatsapp.com...",
    "prompt_required": false,
    "connection": {
      "state": "opening_whatsapp",
      "state_label": "Opening WhatsApp Web",
      "mode": "dedicated",
      "is_connected": false,
      "timeline": [...]
    }
  }
  ```

### `POST /api/browser-session/confirm-restart`
Explicit operator confirmation to gracefully close personal browser window(s).
- **Request Body:**
  ```json
  {
    "browser": "chrome",
    "profile_dir": "Default",
    "confirmed": true
  }
  ```
- **Response:**
  ```json
  {
    "success": true,
    "message": "Personal window closed and session started.",
    "connection": { ... }
  }
  ```

### `POST /api/browser-session/resolve-conflict`
Direct probe and resolution endpoint.
- **Parameters:** `browser`, `profile_dir`, `force_personal` (bool).
- **Response:**
  ```json
  {
    "success": true,
    "result": {
      "resolved": true,
      "conflict_type": "relay_owned",
      "message": "Previous Relay session automatically closed and profile released."
    },
    "connection": { ... }
  }
  ```

---

## 5. Visual Artifacts & Proof

Screenshots captured from live Selenium integration test:
- `docs/screenshots/screen_browser_conflict_dashboard_conn.png`: Dashboard unified connection monitor with Start Session and Test Connection controls.
- `docs/screenshots/screen_browser_conflict_settings_models.png`: Interactive connection models in Settings with embedded Start Session buttons.
- `docs/screenshots/screen_modal_confirm_browser_restart.png`: One-time confirmation modal with warning, "Use Dedicated Session" fallback, and "Confirm & Close Window" action.
- `docs/screenshots/screen_browser_conflict_waiting_qr.png`: Real-time QR scan detection with live activity counter.

---

## 6. Verification Results

Full test suite execution results:
```
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\Rift\Documents\Antigravity ide\whatsapp automation
collected 117 items

tests\test_api.py ........................................               [ 34%]
tests\test_browser_conflict_resolution.py ..........                     [ 42%]
tests\test_config_manager.py .....                                       [ 47%]
tests\test_connection_monitoring.py .........                            [ 54%]
tests\test_data_loader.py ........                                       [ 61%]
tests\test_device_manager.py ....                                        [ 64%]
tests\test_engine_sleep.py ..                                            [ 66%]
tests\test_gui_integration.py ..                                         [ 68%]
tests\test_logger.py ...                                                 [ 70%]
tests\test_media_and_contacts.py ...........                             [ 80%]
tests\test_profile_lock_and_launch.py .......                            [ 86%]
tests\test_spintax.py ......                                             [ 91%]
tests\test_updater.py .....                                              [ 95%]
tests\test_validator.py .....                                            [100%]

================= 117 passed, 1 warning in 104.05s (0:01:44) ==================
```

