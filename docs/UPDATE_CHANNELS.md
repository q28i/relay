# Relay Update Channels & Developer Distribution Architecture

This document describes Relay's multi-tier update distribution system, semantic versioning model, channel filtering rules, targeted developer rollout mechanisms, and campaign safety controls.

---

## 1. Overview & Channel Definitions

Relay supports three distinct update channels, allowing standard production users, preview testers, and core developers to follow separate release streams from the same GitHub repository (`https://github.com/q28i/relay`).

```
+-------------------------------------------------------------------------+
|                              GITHUB RELEASES                            |
|                                                                         |
|  +--------------------+   +---------------------+   +----------------+  |
|  | v2.0.0 (Stable)    |   | v2.1.0-beta.1 (Beta)|   | v2.1.0-dev.1   |  |
|  +--------------------+   +---------------------+   +----------------+  |
+------------|-------------------------|-----------------------|----------+
             |                         |                       |
             v                         v                       v
     [Stable Channel]           [Beta Channel]          [Dev Channel]
   Only stable releases     Stable + Beta/RC tags     All releases + Dev
```

### Channel Comparison Matrix

| Channel | Intended Audience | Eligible Tags | Prerelease Allowed | Default |
|---|---|---|---|---|
| **Stable** | General production operators | `v2.0.0`, `v2.1.0` | No | Yes |
| **Beta** | Preview testers & power users | `v2.1.0-beta.1`, `v2.1.0-rc.1`, stable releases | Yes (Beta & RC only) | No |
| **Dev** | Core developer workstations | `v2.1.0-dev.20261108`, `v2.1.0-alpha.1`, all tags | Yes (All prereleases) | No |

---

## 2. Semantic Versioning Model (SemVer 2.0.0)

Relay implements strict SemVer 2.0.0 parsing with hierarchical channel precedence:

### 2.1 Release Precedence Ranks

When two releases share the same major, minor, and patch numbers (e.g. `2.1.0`), precedence is resolved using internal channel ranking:

$$\text{dev (1)} < \text{alpha (2)} < \text{beta (3)} < \text{rc (4)} < \text{stable (10)}$$

### 2.2 Version Precedence Rules & Examples

1. **Higher base version always precedes lower base version, regardless of prerelease tag**:
   $$\text{v2.1.0-dev.1} > \text{v2.0.0}$$
   A developer on `v2.0.0` will be prompted to upgrade to `v2.1.0-dev.1` when on the `Dev` channel.
2. **Stable release precedes prerelease of the same base version**:
   $$\text{v2.1.0} > \text{v2.1.0-rc.2} > \text{v2.1.0-beta.1} > \text{v2.1.0-dev.1}$$
   When `v2.1.0` stable is published, all beta and dev users on `2.1.0-xxx` will advance to stable.
3. **Prerelease numeric incrementation**:
   $$\text{v2.1.0-beta.2} > \text{v2.1.0-beta.1}$$
   $$\text{v2.1.0-dev.2} > \text{v2.1.0-dev.1}$$

---

## 3. GitHub Releases Discovery Engine

Rather than querying `/releases/latest` (which GitHub restricts exclusively to published non-prerelease tags), Relay queries:

```http
GET /repos/q28i/relay/releases?per_page=15
Accept: application/vnd.github.v3+json
User-Agent: Relay-Desktop-Updater/2.0.0 (Windows)
```

### 3.1 Channel Filtering Algorithm

For every release returned by GitHub:

1. **Discard Drafts**: Any release where `draft == true` is ignored immediately.
2. **Channel Classification**:
   - `prerelease == false` AND no `-beta`/`-rc`/`-dev`/`-alpha` tag &rarr; Class: `stable`.
   - Tag contains `beta` or `rc` &rarr; Class: `beta`.
   - Tag contains `dev` or `alpha` &rarr; Class: `dev`.
3. **Target Channel Evaluation**:
   - Device on `Stable`: Discards `beta` and `dev` releases.
   - Device on `Beta`: Discards `dev` releases; accepts `beta` and `stable`.
   - Device on `Dev`: Accepts all valid releases.
4. **Asset Validation**:
   - Verifies the release contains a Windows executable installer (`.exe`). Releases lacking Windows binaries are discarded.
5. **Selection**:
   - Sorts remaining eligible releases by `SemVer` descending.
   - Compares the top candidate against `CURRENT_VERSION`.
   - Sets `has_update = (candidate > current)`.

---

## 4. Targeted Developer Rollout Architecture

Developers frequently need to deploy an experimental release to verify a fix on a specific test machine without notifying or disrupting standard users.

Relay supports three coordinated layers of targeted rollout:

### 4.1 Layer 1: Channel Scoping (Public Gating)

- Experimental releases are tagged with `-dev.<timestamp>` or `-alpha.<run>` and flagged as `prerelease: true` in GitHub Releases.
- Standard users on the default `Stable` channel are completely insulated: their update check evaluates only stable releases and will report "You are up to date".

### 4.2 Layer 2: Targeted Device Manifest (Device-Specific Scoping)

For builds intended strictly for one or more specific development machines, the developer can embed a JSON targeting comment in the GitHub Release body:

```markdown
# Relay v2.1.0-dev.20261108 (Targeted Test Build)

This is an experimental build for verifying driver cache improvements.

<!-- target_devices: ["relay-c7dfffe8-8f80-47d8-a4a2-64c03a83224a"] -->

### Changes
- Updated Selenium Manager fallback.
```

#### Evaluation Rules:
1. When Relay checks for updates, it inspects the release body for `<!-- target_devices: [...] -->`.
2. If the tag is present:
   - Relay checks if its own persistent `installation_id` is included in the array.
   - If included: the update is marked eligible.
   - If NOT included: the update is silently skipped, even if the device is on the `Dev` channel.
3. If no targeting comment is present, all devices subscribed to the `Dev` channel are eligible.

### 4.3 Layer 3: Authenticated Private Releases

Because `q28i/relay` is a private repository, update checks automatically discover local GitHub CLI tokens (`gh auth token`) or `GITHUB_TOKEN` environment variables. Devices without valid GitHub credentials receive HTTP 404, preventing unauthorized external access to proprietary release binaries.

---

## 5. Critical Update Safety Controls

Upgrading desktop software while a bulk messaging dispatch is active can lead to dropped connections, corrupted recipient states, or duplicate message sends. Relay implements strict multi-layer dispatch guards:

### 5.1 In-Memory Active Worker Check

`RelayUpdaterService.trigger_update_installer()` inspects `job_worker.get_active_job()`. If an active campaign thread is currently sending messages, the update request is rejected immediately with HTTP 409:

```json
{
  "detail": "Cannot install update while an active WhatsApp campaign is dispatching. Please pause or wait for completion."
}
```

### 5.2 SQLite Durable Queue Inspection

Even if the in-memory worker is idle (for example, immediately after application startup or while an operator investigates a failure), campaigns may be recorded in the SQLite database as `RUNNING`, `PAUSED`, `RECONCILIATION_REQUIRED`, or `QUEUED`.

The updater queries:
```sql
SELECT id, name, status FROM campaign_jobs 
WHERE status IN ('RUNNING', 'PAUSED', 'RECONCILIATION_REQUIRED', 'QUEUED');
```

If any unfinished jobs are found:
- The update installer **will not spawn**.
- An explicit error is returned detailing the pending job ID and status.
- The operator must explicitly complete, cancel, or reconcile the campaign before an upgrade is permitted.

### 5.3 SHA-256 Integrity Verification

During download:
1. Relay streams the installer executable into a temporary file (`Relay-Setup-Update.exe.tmp`).
2. Computes the SHA-256 hash incrementally across all incoming chunks.
3. If `SHA256SUMS.txt` is published alongside the release assets, Relay downloads the manifest and verifies that the computed hash strictly matches the declared checksum.
4. If a mismatch is detected:
   - The temporary file is permanently deleted.
   - The download state is marked as failed.
   - No executable is permitted to run.

### 5.4 Graceful Inno Setup Handover

When triggering an update:
1. Relay spawns the downloaded installer as an independent detached process (`creationflags=DETACHED_PROCESS`).
2. Arguments pass `/CLOSEAPPLICATIONS` and `/RESTARTAPPLICATIONS`.
3. Inno Setup signals Relay's window to shut down cleanly, overwrites the application directory, and launches the updated Relay binary upon completion.
4. Relay initiates a delayed process exit (`os._exit(0)`) to cleanly release locks on the SQLite database and persistent browser profile.
