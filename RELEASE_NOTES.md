# Relay v2.0.0 — Production Windows Desktop Release

Relay v2.0.0 transitions Relay from an internal developer script into a production-grade, standalone Windows desktop application with zero configuration.

### 🌟 Key Highlights

- **1-Click Windows Desktop Installer**: Download `Relay-Setup-v2.0.0-Windows-x64.exe` and install directly into `%LOCALAPPDATA%\Programs\Relay\`. No Python, pip, Node.js, Git, or terminal commands needed.
- **Modern Per-User Installation**: Zero Administrator / UAC prompts required. Works seamlessly on managed or non-privileged user accounts.
- **Isolated User Data Architecture**: Strict separation of read-only program binaries from personal user state (`%LOCALAPPDATA%\Relay\`). Your WhatsApp authentication tokens, SQLite database, contacts, templates, and media library are never overwritten or deleted during updates.
- **Built-In Self-Update Engine**: Checks for new versions directly via GitHub Releases API (`github.com/q28i/relay`). Features background downloading, SHA-256 integrity verification, and active-campaign dispatch guards that prevent accidental restarts while sending messages.
- **Smart Desktop Launcher**: Named Windows mutex (`Global\RelayWhatsAppAutomationMutex`) prevents duplicate running instances. Automatic port conflict resolution checks port 8000 and fails over to 8001–8010 if occupied.
- **Reliable WhatsApp Media Dispatch Engine**: Preserves the verified authentic photographic media upload pipeline (`image_with_caption`), sticker workflow rejection, and modal-scoped caption insertion.
- **100% Test Coverage**: Full suite of 247 automated unit, regression, and DOM verification tests passing.

---

### 📦 Assets

- `Relay-Setup-v2.0.0-Windows-x64.exe` (31.75 MB)
- `SHA256SUMS.txt`

### 🔒 Cryptographic Checksums
```
fdebe40d0b5afa612b800a39420ec1a91401ed90806c4710c8e85ca80bb6938b  Relay-Setup-v2.0.0-Windows-x64.exe
```
