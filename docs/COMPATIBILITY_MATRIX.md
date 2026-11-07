# Relay Desktop — Environmental Compatibility Matrix

## Evaluation Methodology

This matrix evaluates Relay v2.0.0 across varied Windows environments, hardware configurations, permissions, and browser setups.

**Evaluation Ratings**:
- **PASS**: Verified and demonstrated to work without failure.
- **FAIL**: Confirmed to encounter a fatal error or blocking defect based on reproducible evidence.
- **NOT TESTED**: Requires an isolated, clean Windows Virtual Machine or physical hardware configuration that was not physically tested in this session.
- **NOT SUPPORTED**: Architectural constraint where the environment is explicitly outside Relay's target specifications.

---

## Compatibility Matrix

| Environment / Configuration | Status | Evidence & Operational Notes |
|---|---|---|
| **Windows 11 x64 (Developer Workstation)** | **PASS** | Verified in active session. All 247 tests passing; UI, backend, and driver functional. |
| **Windows 11 x64 (Clean User Account)** | **NOT TESTED** | Tested in local dev session, but physical clean-room Windows VM validation is required for true zero-state proof. |
| **Windows 10 x64 (Clean User Account)** | **NOT TESTED** | Target architecture matches x64 Windows 10, but dedicated Win 10 VM verification was not conducted. |
| **Windows 11 without Chrome (Edge Only)** | **FAIL** | Confirmed: Default config sets `browser="chrome"`. If Chrome executable is missing on a clean PC, Relay raises `BrowserExecutableNotFoundError` instead of auto-selecting Edge. |
| **Windows 11 with Edge Only (User selects Edge in UI)** | **NOT TESTED** | Code contains EdgeOptions and EdgeService, but full fresh-install Edge-only lifecycle not tested end-to-end in clean VM. |
| **Windows 11 with Chrome Installed** | **PASS** | Default configuration and browser detection are tuned for Chromium / Chrome 136+. |
| **Windows 11 with Restricted User Permissions (Non-Admin)** | **PASS** | Inno Setup uses `PrivilegesRequired=lowest`, and runtime writes exclusively to `%LOCALAPPDATA%`. Mutex falls back from Global to Local. |
| **Windows Account Name with Spaces (`C:\Users\John Doe`)** | **PASS** | Verified via test suite `tmp_path` with spaces and `subprocess.list2cmdline` argument escaping. |
| **Windows Account Name with Non-ASCII (`C:\Users\José`)** | **NOT TESTED** | Python 3 and SQLite use UTF-8 on Windows, but full end-to-end driver initialization in a non-ASCII user home path requires clean VM testing. |
| **Offline Startup (Server & Dashboard UI)** | **PASS** | Server binds to `127.0.0.1:8000`, frontend static assets are bundled locally, SQLite runs entirely local. |
| **Offline Browser Automation (First Launch)** | **FAIL** | Confirmed: On a clean computer without pre-cached drivers, Selenium Manager requires an active internet connection to download `chromedriver.exe`. |
| **Restricted / Corporate Proxy Network** | **FAIL** | GitHub API update checks and `selenium-manager.exe` driver downloads fail if Windows proxy credentials are required and unconfigured. |
| **Clean First Installation (Empty AppData)** | **PASS** | `backend/paths.py:ensure_data_dirs()` initializes `%LOCALAPPDATA%\Relay`, creates empty SQLite DB tables, and sets default config. |
| **Upgrade Over Existing Installation (Data Preservation)** | **PASS** | Inno Setup overwrites `%LOCALAPPDATA%\Programs\Relay\` binaries while leaving `%LOCALAPPDATA%\Relay\` user data untouched. |
| **Multiple Concurrent Windows Accounts (Fast User Switching)** | **FAIL** | Confirmed: Unauthenticated `127.0.0.1:8000` port conflict allows a second local user to connect to the first user's active session without authentication. |
| **Locked Browser Profile (Personal Chrome Running)** | **PASS** | Relay uses dedicated profile (`whatsapp_browser_session/`) with process detection (`diagnose_profile`), avoiding personal Chrome profile locks. |
| **Windows on ARM64 (Surface Pro X, Snapdragon X)** | **NOT SUPPORTED** | Installer is built with `ArchitecturesInstallIn64BitMode=x64compatible` and bundles x64 AMD64 binaries. Native ARM64 is not compiled. Emulation (Prism) may run, but is untested and unsupported. |
| **32-bit Windows (x86)** | **NOT SUPPORTED** | 64-bit Python 3.14 runtime and 64-bit Inno Setup script reject 32-bit operating systems. |

---

## Summary of Blocking Gaps for Fresh PCs

1. **Default Browser**: Relay must auto-detect Microsoft Edge on fresh Windows installations if Google Chrome is absent.
2. **Initial Driver Provisioning**: Offline or restricted machines cannot fetch `chromedriver.exe` via `selenium-manager.exe` on first launch.
3. **Repository Privacy**: Private repository `q28i/relay` prevents fresh PCs from checking for updates without an authenticated token.
