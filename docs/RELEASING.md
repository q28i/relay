# Relay Desktop — Release & Publishing Guide

## Release Overview

Relay uses GitHub Releases (`q28i/relay`) as its primary distribution channel for Windows binaries and self-updates.

---

## 1. Automated Release (GitHub Actions)

The repository provides a GitHub Actions workflow template at [`ci/release.yml`](../ci/release.yml) that builds, tests, and publishes the installer whenever a semantic version tag is pushed:

```bash
git tag v2.0.0
git push q28i v2.0.0
```

*(Note: To activate on GitHub Actions, ensure `ci/release.yml` is linked into `.github/workflows/release.yml` on a repository with the `workflow` token scope enabled).*

The workflow:
1. Checks out the code.
2. Installs Python 3.11+ and Inno Setup.
3. Runs the test suite to ensure 100% green tests.
4. Executes `python build_installer.py`.
5. Computes `SHA256SUMS.txt`.
6. Publishes a draft or public release with `Relay-Setup-vX.Y.Z-Windows-x64.exe` and `SHA256SUMS.txt`.

---

## 2. Manual Release Compilation

To build the installer locally on a Windows developer workstation:

### Prerequisites:
- Python 3.10+ (64-bit)
- PyInstaller (`pip install pyinstaller`)
- Inno Setup 6 (`winget install JRSoftware.InnoSetup`)
- Dependencies (`pip install -r requirements.txt`)

### Build Command:
```powershell
python build_installer.py
```

This single command:
1. Cleans old `dist/Relay` and `build` folders.
2. Runs PyInstaller with `relay.spec`.
3. Verifies static assets and bundle integrity.
4. Compiles `Relay-Setup.iss` with Inno Setup.
5. Computes SHA-256 and writes `dist/SHA256SUMS.txt`.

Output:
- `dist/Relay-Setup-v2.0.0-Windows-x64.exe`
- `dist/SHA256SUMS.txt`

---

## 3. Publishing to GitHub via GitHub CLI (`gh`)

```powershell
gh release create v2.0.0 `
  dist/Relay-Setup-v2.0.0-Windows-x64.exe `
  dist/SHA256SUMS.txt `
  --title "Relay v2.0.0 - Windows Desktop Installer" `
  --notes-file RELEASE_NOTES.md
```

---

## 4. Verification Check

Verify that the published release is discoverable by Relay's updater:
```powershell
curl -s https://api.github.com/repos/q28i/relay/releases/latest | jq '{tag_name, assets: [.assets[].name]}'
```
