# WhatsApp Automation Relay

> **Documentation & Engineering Handoff:**  
> All documentation, architecture specifications, phase reports, and runbooks are organized inside the **[`docs/`](docs/README.md)** directory.  
> The comprehensive 11-part handoff suite is located at **[`docs/handoff/`](docs/handoff/README.md)**.  
> **Launch Web Dashboard:** Double-click [`start_dashboard.bat`](start_dashboard.bat) or execute `python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000`.

---

# WhatsApp Bulk Messenger Pro

[![Release](https://img.shields.io/github/v/release/ainttyug/whatsapp-bulk-messenger?color=green)](https://github.com/ainttyug/whatsapp-bulk-messenger/releases)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)](https://www.microsoft.com/windows)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)]()

A modern, high-performance desktop application for sending bulk personalized WhatsApp messages, images, videos, and PDF brochures directly from your browser sessions. Includes an in-app spreadsheet editor, hardware device licensing, anti-ban cooldown engine, and automated remote updates.

---

## Key Highlights

- **Dual-Mode Desktop Interface**:
  - **Simplified Mode (Default)**: A clean 3-step dashboard for non-technical users (`Select Contacts` -> `Type Message` -> `Send`).
  - **🛠️ Developer Mode**: 6 advanced tabs with live data tables, browser profile selection, Spintax variation, anti-ban sliders, daily automation scheduler, and release publishing.
- **Built-in Excel & Spreadsheet Editor**:
  - View, type, and edit `.xlsx`, `.xls`, and `.csv` files directly inside the application powered by `tksheet`.
  - **Quick Paste**: Paste raw lists of phone numbers copied from WhatsApp or text files directly into the grid.
- **Reddit & Industry Anti-Ban Protection**:
  - Randomized delay jitter (8–16s) to emulate human typing speed.
  - Automatic batch cooldown pauses (60–90s after every 20 messages).
  - Spintax variation engine (`{Hi|Hello|Hey}`) ensuring every dispatched message is textually unique.
  - Daily sending volume caps.
- **Hardware Device ID & Developer Whitelist**:
  - Generates immutable Windows hardware fingerprints (`MachineGuid` + MAC node hash).
  - Whitelists developer devices with master release publishing privileges.
- **Remote Auto-Updater**:
  - Automatic update checks on startup via GitHub Releases or Cloudflare Workers.
  - 1-click update installation that preserves client logins, spreadsheets, and settings.
- **1-Click 0-Setup Runner (`run.bat`)**:
  - Automatically installs Python via `winget` or `curl` if missing.
  - Automatically installs dependencies (`selenium`, `openpyxl`, `tksheet`).

---

## Quick Start

### 1-Click Launch (Recommended)
Double-click **`run.bat`**:
1. Checks for Python and installs it automatically if missing.
2. Checks and installs required dependencies.
3. Launches the Desktop application.

### CLI, Headless & Dry-Run Dispatch
```bash
# Display hardware Device ID & licensing role:
python run.py --device-info

# Check for updates from GitHub or Cloudflare:
python run.py --check-update

# Pre-flight audit & validate contacts without opening browser:
python run.py --validate

# Simulate full campaign with Spintax & timing preview (Dry Run):
python run.py --dry-run

# Run automated batch headlessly with safety preset:
python run.py --auto --headless --preset safe --dedupe

# Schedule daily dispatch at 09:30 AM:
python run.py --schedule 09:30

# Run automated unit & integration test suite:
pytest

# Package a release for distribution (Whitelisted Developer only):
python run.py --package-release 1.2.1
```

---

## Architecture & Engineering Documentation

For in-depth technical documentation, specifications, and architecture blueprints:
- **[PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md)**: Master technical documentation (25 comprehensive sections).
- **[ARCHITECTURE.md](ARCHITECTURE.md)**: System architecture, component boundaries, and Mermaid diagrams.
- **[FEATURE_MAP.md](FEATURE_MAP.md)**: Complete feature inventory and execution traceability matrix.
- **[TECHNICAL_DEBT.md](TECHNICAL_DEBT.md)**: Prioritized technical debt register and defect analysis.
- **[REFACTORING_PLAN.md](REFACTORING_PLAN.md)**: Step-by-step modernization and refactoring strategy.
- **[DOCUMENTATION.md](DOCUMENTATION.md)**: Legacy audit notes, anti-ban research, and selector reference.
