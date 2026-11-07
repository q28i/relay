# Relay Device Identity & Installation Diagnostics

This document outlines the architecture, data structures, privacy guarantees, and developer enrollment workflows for the Relay Device Identity and System Diagnostics subsystem.

---

## 1. Persistent Installation ID Architecture

Each installation of Relay generates and persists a unique, non-spoofed **Relay Installation ID**.

### 1.1 Format Specification

The installation ID adheres strictly to the canonical UUIDv4 representation prefixed with `relay-`:

```
relay-xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
```

Where:
- `xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx` is a randomly generated Version-4 UUID (RFC 4122).
- The 13th character is strictly `4` (UUID Version 4: randomly generated).
- The 17th character is one of `8`, `9`, `a`, or `b` (variant 1).
- Total string length: 42 characters.

Example:
```
relay-c7dfffe8-8f80-47d8-a4a2-64c03a83224a
```

### 1.2 Storage Location & Isolation

The installation ID is decoupled from transient application components (such as browser sessions, message databases, or temporary caches) and stored in:

- **Packaged Desktop Application (Frozen Mode)**:
  ```
  %LOCALAPPDATA%\Relay\device_identity.json
  ```
- **Development / Source Execution**:
  ```
  <repository-root>\device_identity.json
  ```
- **Custom Environment Override**:
  Honors `RELAY_USER_DATA_DIR` if set.

### 1.3 Atomic Persistence Guarantees

To prevent half-written, zero-byte, or corrupted identity records during abrupt system shutdowns, power failures, or OS crashes, `DeviceIdentityManager` uses atomic file replacement:

1. Serializes identity payload to a temporary file: `device_identity.json.tmp`.
2. Flushes the user-space buffer (`f.flush()`).
3. Calls low-level OS file sync (`os.fsync(fileno)`) to ensure bits are written to physical disk.
4. Atomically swaps the temporary file into place using `os.replace()` (which is atomic on Windows NTFS and POSIX filesystems).

### 1.4 Independence from Hardware Signatures

Relay intentionally **does not derive** installation IDs from hardware serial numbers, MAC addresses, CPU IDs, or motherboard UUIDs for four critical engineering and privacy reasons:

1. **MAC Address Randomization**: Modern Windows 10/11 Wi-Fi adapters frequently randomize MAC addresses, causing hardware-derived IDs to change unpredictably across network transitions.
2. **Virtual Machine & Container Cloning**: Hardware hashing creates identical identifiers across cloned virtualized machines or developer sandboxes.
3. **Motherboard & Hardware Replacement**: Upgrading a network card or swapping a motherboard would silently invalidate user preferences and channel subscriptions.
4. **Zero Telemetry Fingerprinting**: Preventing persistent hardware fingerprinting ensures strict privacy compliance (GDPR/ePrivacy).

### 1.5 Lifecycle & Recovery

- **Survives Updates**: Inno Setup installers overwrite executable bundles in `Program Files` or local directories, but never touch `%LOCALAPPDATA%\Relay\device_identity.json`.
- **Survives Restarts**: Read once on backend startup and cached in memory.
- **Corrupt File Recovery**: If `device_identity.json` contains malformed JSON or an invalid ID format, a warning is logged and a fresh UUIDv4 is generated atomically without crashing the application.
- **Explicit Reset**: Users can reset the Installation ID via Settings &rarr; *Reset ID*. This requires explicit confirmation.

---

## 2. Identity JSON Schema

```json
{
  "schema_version": 1,
  "installation_id": "relay-c7dfffe8-8f80-47d8-a4a2-64c03a83224a",
  "device_label": "Primary Development Workstation",
  "device_role": "developer",
  "update_channel": "dev",
  "created_at": "2026-11-08T01:26:57.123456+00:00",
  "last_startup_at": "2026-11-08T01:28:30.654321+00:00",
  "developer_enrolled_at": "2026-11-08T01:30:00.000000+00:00",
  "developer_token": null,
  "update_feed_override": null,
  "verbose_updater_logging": false
}
```

### Schema Fields

| Field | Type | Description |
|---|---|---|
| `schema_version` | integer | Data format version (currently `1`). |
| `installation_id` | string | Persistent `relay-<uuid4>` identifier. |
| `device_label` | string | Friendly name assigned by the operator (max 64 chars). |
| `device_role` | string | Operational role: `"standard"` or `"developer"`. |
| `update_channel` | string | Active release channel: `"stable"`, `"beta"`, or `"dev"`. |
| `created_at` | string (ISO-8601) | Timestamp when this installation ID was first generated. |
| `last_startup_at` | string (ISO-8601) | Timestamp of the most recent Relay backend launch. |
| `developer_enrolled_at` | string (ISO-8601) / null | Timestamp when workstation was enrolled as developer. |
| `developer_token` | string / null | Optional enrollment authentication token or secret. |
| `update_feed_override` | string / null | Custom GitHub repository or release manifest URL. |
| `verbose_updater_logging`| boolean | Enables detailed HTTP and verification logs. |

---

## 3. Local Hardware & System Diagnostics

Relay exposes comprehensive system metrics on `GET /api/device/info` and within Settings &rarr; *Device & Installation*:

### 3.1 Collected Categories

- **Identity**: Installation ID, friendly label, local hostname, local OS username, device role, update channel.
- **System Specifications**:
  - Operating System name, display version, build number.
  - CPU architecture (e.g. `AMD64`, `x86_64`), model name, logical core count.
  - Physical RAM: Total RAM (GB) and Available RAM (GB) queried via Win32 `GlobalMemoryStatusEx`.
  - Storage: Total space (GB) and Free space (GB) on the persistent data volume (`shutil.disk_usage`).
  - System locale (e.g. `en-US`, `en-IN`) and local timezone.
- **Application Runtime**:
  - Relay version (`2.0.0`).
  - Git commit SHA (retrieved from repository or release metadata).
  - Execution mode (`"Frozen Desktop Package"` or `"Development Source"`).
  - Absolute directories for Bundle (`_MEIPASS`), User Data, and Logs.
  - Process ID (PID) and process elevation (`"Administrator"` vs `"Standard User"`).
  - Application startup timestamp and running uptime in seconds.
- **Browser Environment**:
  - Installed browsers detected from Windows Registry and standard Program Files locations (Google Chrome, Microsoft Edge, Mozilla Firefox, Brave).
  - Configured persistent session profile path.
  - Active browser session status (is WebDriver running and attached).

---

## 4. Privacy Guarantees & Redaction

Relay is built with an **offline-first, zero-unauthorized-telemetry** architecture.

### 4.1 Strict Local Boundary

- Device identity and diagnostic details remain **strictly local**.
- Relay **never automatically transmits** device identity or hardware metrics to external servers or GitHub APIs.
- GitHub Release queries send only standard HTTP `User-Agent` and `Accept` headers without transmitting the installation ID or local host parameters.

### 4.2 Diagnostic Export Redaction

When operators choose to export a diagnostic report via Settings &rarr; *Export Diagnostics*:

1. **Interactive Preview**: The UI displays an exact JSON preview of the report before download.
2. **Redaction Toggle**: Enabled by default (`redact=true`):
   - Local OS username is replaced with `"[REDACTED_USER]"`.
   - Hostname/Machine name is replaced with `"[REDACTED_HOST]"`.
   - All directory paths containing the user's home folder or username are sanitized (e.g. `C:\Users\JohnDoe\AppData` &rarr; `C:\Users\[REDACTED_USER]\AppData`).
   - Developer tokens or secrets are replaced with `"[REDACTED]"`.
3. **Strict Exclusion of Sensitive Data**:
   The diagnostics engine **never includes**:
   - Contact phone numbers, names, or audience groups.
   - Campaign history, delivery statuses, or timestamps.
   - Message templates or message bodies.
   - Uploaded media images, videos, or documents.
   - WhatsApp Web cookies, tokens, or encryption session keys.

---

## 5. Developer Device Registration Workflow

To designate a computer as an authorized development workstation:

1. Open Relay &rarr; **Settings** &rarr; **Device & Installation**.
2. Click **Register as Developer**.
3. Enter a descriptive workstation label (e.g. `"Primary Development Workstation"`).
4. Relay:
   - Updates `device_role` to `"developer"`.
   - Sets `update_channel` to `"dev"`.
   - Records `developer_enrolled_at`.
   - Saves `device_identity.json` atomically.
   - Displays the purple **Developer Workstation** badge.
5. To revert to a standard user installation, click **Revert to Standard Role**. The device role resets to `"standard"` and the update channel reverts to `"stable"`.
