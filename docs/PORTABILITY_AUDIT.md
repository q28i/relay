# Relay Desktop — Portability & Fresh-PC Audit Risk Register

## Executive Audit Summary

This document records the forensic portability and fresh-computer audit of **Relay v2.0.0** (`https://github.com/q28i/relay`).

The audit evaluated every dependency, runtime assumption, hardcoded path, security constraint, and Windows-specific behavior that functions on the developer's workstation but could degrade or fail on a clean Windows machine.

In strict compliance with audit instructions, **no code fixes have been applied during this audit**. All findings are recorded with verifiable evidence, severity classification, reproduction steps, and architectural recommendations.

---

## 1. Release Baseline Audit

- **Repository**: `https://github.com/q28i/relay.git`
- **Current HEAD Branch**: `main`
- **Release Tag**: `v2.0.0`
- **Tagged Release Commit**: `5a4ccfc` (`feat(release): standalone Windows installer, release pipeline, and self-update system`)
- **Published Release Assets**:
  - `Relay-Setup-v2.0.0-Windows-x64.exe` (31.75 MB, SHA-256: `fdebe40d0b5afa612b800a39420ec1a91401ed90806c4710c8e85ca80bb6938b`)
  - `SHA256SUMS.txt`
- **Discrepancy Note**: Commit `8d99ffe` (`feat(updater): auto-discover gh cli credentials for private repo updates`) was pushed to `main` **after** release `v2.0.0` was tagged and compiled. The executable distributed on GitHub Releases does not contain commit `8d99ffe`.

---

## 2. Portability Risk Register

| ID | Component | Assumption | Evidence | Local Behavior | Fresh-PC Risk | Severity | Reproduction | Recommendation | Status |
|---|---|---|---|---|---|---|---|---|---|
| **PORT-01** | CI / CD Pipeline | Release workflow runs automatically via GitHub Actions on tag push | File located at `ci/release.yml` instead of `.github/workflows/release.yml` | Developer ran `python build_installer.py` locally and published via `gh release create` | GitHub Actions strictly ignores workflows outside `.github/workflows/`. Pushing tag `v2.0.0` will never trigger a CI build or publish | **Critical** | Inspect repo root; `.github/workflows/` does not exist. Push any tag to a fork; Actions tab remains inactive | Move `ci/release.yml` to `.github/workflows/release.yml` using a GitHub PAT with `workflow` scope | **Confirmed** |
| **PORT-02** | Auto-Updater | Unauthenticated GitHub API requests can discover releases | `backend/updater_service.py:114` queries `https://api.github.com/repos/q28i/relay/releases/latest` | Developer workstation has `gh` CLI logged into `q28i` | `q28i/relay` is a **Private** repository. Unauthenticated requests to private repos return `HTTP 404: Not Found`. Ordinary users receive "HTTP Error 404" | **Critical** | Run `curl.exe -s https://api.github.com/repos/q28i/relay/releases/latest` without Authorization header; returns 404 | Either make repository public before broad distribution, or configure private release distribution / authenticated proxy | **Confirmed** |
| **PORT-03** | Release Packaging | Distributed installer contains all recent updater fixes | Git history: tag `v2.0.0` on `5a4ccfc`; commit `8d99ffe` is subsequent commit | Local developer runs latest `main` commit `8d99ffe` | Users downloading `Relay-Setup-v2.0.0-Windows-x64.exe` receive commit `5a4ccfc`, which lacks the `gh` token auto-discovery logic | **High** | Decompile or inspect `backend/updater_service.py` in `dist/Relay/_internal/`; token discovery absent | Prepare and tag a clean `v2.0.1` release incorporating all updater and packaging enhancements | **Confirmed** |
| **PORT-04** | Runtime DLLs | Visual C++ 2015–2022 runtime libraries are universally present | `dist/Relay/_internal/` contains `VCRUNTIME140.dll` but lacks `msvcp140.dll` | Developer machine has Visual Studio / VC++ 2015-2022 redistributable installed | Clean Windows machines without VC++ redistributable may fail to load Python C-extensions requiring C++ runtime symbols | **High** | Remove VC++ redistributable on a test VM and launch `Relay.exe`; C-extension import failure | Bundle `msvcp140.dll` or include silent `vc_redist.x64.exe` runner in Inno Setup `[Run]` | **Confirmed** |
| **PORT-05** | Browser Automation | WebDriver binary is pre-cached on disk | `browser_manager.py:682`: `~/.cache/selenium/chromedriver/win64/*/chromedriver.exe` | Dev PC has pre-existing Selenium cache (`156.0.8078.80`) populated during dev tests | On a fresh PC, cache is empty. `selenium-manager.exe` must fetch driver over internet. If machine is offline or behind proxy, launch fails | **High** | Delete `~/.cache/selenium`, disconnect network, and attempt to start session; `BrowserLaunchFailedError` occurs | Bundle a matched stable `chromedriver.exe` directly in the installer or gracefully inform user about driver download requirements | **Confirmed** |
| **PORT-06** | Browser Selection | Google Chrome is installed on the user's computer | `config_manager.py:57`: default `browser = "chrome"`. `backend/app.py:56`: defaults to `"chrome"` | Developer PC has Google Chrome installed | Clean Windows 10/11 installs only have **Microsoft Edge**. If user launches Relay without installing Chrome, it raises `BrowserExecutableNotFoundError` | **High** | Uninstall Chrome on a test PC and click "Start Session"; launch fails immediately with missing executable | Automatically detect installed browsers on first launch and default to Edge if Chrome is not detected | **Confirmed** |
| **PORT-07** | Localhost Security | Port 8000 is accessible only by the current Windows user | `relay_launcher.py:168`: binds to `127.0.0.1:8000` with no auth tokens | Single user logged into developer workstation | On multi-user or shared PCs (Fast User Switching), any other local user or process can interact with `/api/` endpoints without credentials | **High** | Start Relay as User A; switch to User B and curl `http://127.0.0.1:8000/api/contacts`; exposes contacts | Generate an ephemeral session secret / CSRF token in AppData and require it on API requests | **Confirmed** |
| **PORT-08** | Code Signing | Windows SmartScreen permits unhindered installer execution | `Relay-Setup-v2.0.0-Windows-x64.exe` has no Authenticode digital signature | Developer compiled executable locally, so SmartScreen bypasses local binaries | Downloading from GitHub on a clean PC triggers `Windows protected your PC` (SmartScreen unrecognized app banner) | **Medium** | Download installer in Edge from GitHub; SmartScreen warning requires clicking "More info" -> "Run anyway" | Obtain an Authenticode / EV Code Signing certificate to sign installer and executables | **Confirmed** |
| **PORT-09** | Update Integrity | Checksum verification validates publisher authenticity | `backend/updater_service.py:231`: calculates hash, but does not enforce against `SHA256SUMS.txt` | Developer verified hash manually via PowerShell | Both installer and `SHA256SUMS.txt` live in same GitHub release. An attacker compromising repo compromises both. Also, code does not reject mismatched hash | **Medium** | Modify download URL in updater to an arbitrary .exe; updater logs hash but does not abort | Download `SHA256SUMS.txt`, parse matching hash, and abort if computed hash doesn't match; support signed manifests | **Confirmed** |
| **PORT-10** | Safe Update Guard | `job_worker.get_active_job()` covers all unsafe update states | `backend/updater_service.py:255` checks only in-memory `job_worker.get_active_job()` | Developer tests ran on active, in-memory jobs | If Relay is restarted or paused, `get_active_job()` is `None` while SQLite may have `RECONCILIATION_REQUIRED` or incomplete campaigns | **Medium** | Set a job to `PAUSED` in DB, restart server, trigger `/api/updates/apply`; update proceeds despite unfinished campaign | Check `db.get_unreconciled_jobs()` and SQLite database status in addition to in-memory worker | **Confirmed** |
| **PORT-11** | Mutex Isolation | `Global\` mutex namespace is writable by non-admin users | `relay_launcher.py:58`: tests `Global\RelayWhatsAppAutomationMutex` before `Local\` | Developer ran as user with desktop session 1 | On Windows, creating a mutex in `Global\` requires `SeCreateGlobalPrivilege`. Standard user accounts receive `ERROR_ACCESS_DENIED` (code 5) | **Low** | Run as restricted guest user; `Global\` mutex creation fails (gracefully falls back to `Local\`) | Retain fallback or default directly to `Local\` namespace for non-admin per-user desktop apps | **Confirmed** |
| **PORT-12** | GitHub Rate Limit | Unauthenticated GitHub API calls are sufficient for updates | `backend/updater_service.py:114`: calls API without token for standard users | Developer has `gh` CLI token | GitHub rate limits unauthenticated calls to 60/hr per public IP. In corporate/university NAT networks, limit can be exhausted | **Low** | Make 61 requests to GitHub API; returns HTTP 403 `API rate limit exceeded` | Cache update checks for at least 15–30 minutes, or use a lightweight static version mirror | **Confirmed** |
| **PORT-13** | PyInstaller Spec | All declared hidden imports exist in environment | `relay.spec:48-50`: lists `uvicorn.lifespans`, `engineio.async_drivers.asgi` | PyInstaller logs warning and ignores missing hidden imports | Non-fatal build warnings, but indicates legacy or unused packages in spec | **Low** | Run `pyinstaller relay.spec`; logs `ERROR: Hidden import '...' not found` | Clean up unused hidden imports in `relay.spec` | **Confirmed** |

---

## 3. Detailed Subsystem Analysis

### 3.1 Python and Runtime Environment
- **Packaging Mode**: PyInstaller `onedir` mode bundling Python 3.14.7 runtime.
- **Portability Assessment**: The packaged application does **not** require Python to be installed on the host computer. All standard library modules, SQLite bindings, and packages (`fastapi`, `uvicorn`, `selenium`, `pydantic`, `openpyxl`) are self-contained in `dist/Relay/_internal`.
- **Finding**: VC++ runtime (`msvcp140.dll`) is not included. It is present on systems with MSVC installed, but pure clean Windows installations might require it.

### 3.2 File System & Storage Isolation
- **Path Resolution**: `backend/paths.py` cleanly separates `%LOCALAPPDATA%\Programs\Relay\` (binaries) from `%LOCALAPPDATA%\Relay\` (writable user data).
- **Spaces & Unicode**: Usernames containing spaces (e.g. `C:\Users\John Doe`) are properly handled by `os.path.join` and SQLite. Selenium command-line arguments are passed as list elements, which Python's `subprocess.list2cmdline` automatically escapes.
- **Backward Compatibility**: Development environments and pytest sessions cleanly fallback to repository root when `sys.frozen` is False and `RELAY_USER_DATA_DIR` is unset.

### 3.3 Windows Integration
- **Privileges**: Inno Setup script specifies `PrivilegesRequired=lowest`, ensuring seamless installation in user-writable `%LOCALAPPDATA%` without UAC administrator prompts.
- **Single Instance**: Handled via Named Mutex with graceful fallback from `Global\` to `Local\`. Dynamic port selection prevents startup failure when port 8000 is occupied.
- **Uninstaller**: Inno Setup uninstaller cleanly removes program files while strictly preserving the `%LOCALAPPDATA%\Relay` directory.

### 3.4 Browser Automation & Selenium
- **Browser Requirement**: Relay depends on an external Chromium browser. If neither Chrome, Edge, nor Brave is installed, Relay cannot automate WhatsApp Web.
- **Driver Resolution**: Relay's `_find_cached_service()` looks in `~/.cache/selenium/`. On a fresh computer, `selenium-manager.exe` handles initial download, which requires outbound internet access to Google/Microsoft driver CDNs.

### 3.5 Network & GitHub Releases
- **Repository Visibility**: `q28i/relay` is private. Unauthenticated clients receive HTTP 404 from GitHub's Releases API.
- **CI Workflow**: `ci/release.yml` is not active because GitHub Actions requires workflow files in `.github/workflows/`.
