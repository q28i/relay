"""
Relay Desktop Installer Build & Packaging Pipeline.

Automates:
1. Cleans previous dist and build artifacts.
2. Compiles application into onedir bundle via PyInstaller (relay.spec).
3. Verifies internal bundle integrity (executables, static assets, libraries).
4. Compiles Inno Setup installer (Relay-Setup.iss) using ISCC.exe.
5. Generates SHA256SUMS.txt for release validation.
"""

import os
import sys
import shutil
import hashlib
import subprocess
from pathlib import Path

VERSION = "2.0.0"
PROJECT_ROOT = Path(__file__).parent.resolve()
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
SETUP_ISS = PROJECT_ROOT / "Relay-Setup.iss"
OUTPUT_INSTALLER = DIST_DIR / f"Relay-Setup-v{VERSION}-Windows-x64.exe"
SHA256_FILE = DIST_DIR / "SHA256SUMS.txt"


def find_iscc() -> Path:
    """Finds the Inno Setup compiler executable (ISCC.exe)."""
    # 1. PATH
    iscc_path = shutil.which("iscc") or shutil.which("ISCC")
    if iscc_path:
        return Path(iscc_path)

    # 2. Known local install locations
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
        Path("C:/Program Files/Inno Setup 6/ISCC.exe"),
    ]
    for c in candidates:
        if c.is_file():
            return c

    raise FileNotFoundError("Inno Setup compiler (ISCC.exe) was not found in PATH or standard install paths.")


def clean():
    print("[1/5] Cleaning previous build artifacts...")
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
    relay_dist = DIST_DIR / "Relay"
    if relay_dist.exists():
        shutil.rmtree(relay_dist, ignore_errors=True)


def build_pyinstaller():
    print("\n[2/5] Compiling PyInstaller onedir distribution...")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "relay.spec",
        "--clean",
        "--noconfirm",
    ]
    print(f"Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if res.returncode != 0:
        raise RuntimeError(f"PyInstaller build failed with exit code {res.returncode}")

    relay_exe = DIST_DIR / "Relay" / "Relay.exe"
    if not relay_exe.is_file():
        raise FileNotFoundError(f"Expected compiled executable not found at {relay_exe}")
    print(f"PASS: PyInstaller successfully generated {relay_exe}")


def verify_bundle():
    print("\n[3/5] Verifying bundle integrity...")
    static_index = DIST_DIR / "Relay" / "_internal" / "backend" / "static" / "index.html"
    if not static_index.is_file():
        # Check without _internal
        static_index = DIST_DIR / "Relay" / "backend" / "static" / "index.html"
    if not static_index.is_file():
        print(f"WARNING: Static index.html not directly at standard path, scanning bundle...")
        found = list((DIST_DIR / "Relay").rglob("index.html"))
        if not found:
            raise FileNotFoundError("Frontend static index.html is missing from the bundle!")
        print(f"PASS: Found static frontend at {found[0]}")
    else:
        print(f"PASS: Found static frontend at {static_index}")


def build_inno_setup(iscc: Path):
    print(f"\n[4/5] Compiling Windows Installer using {iscc}...")
    cmd = [str(iscc), str(SETUP_ISS)]
    print(f"Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if res.returncode != 0:
        raise RuntimeError(f"Inno Setup compilation failed with exit code {res.returncode}")

    if not OUTPUT_INSTALLER.is_file():
        raise FileNotFoundError(f"Expected installer not found at {OUTPUT_INSTALLER}")

    size_mb = OUTPUT_INSTALLER.stat().st_size / (1024 * 1024)
    print(f"PASS: Installer compiled successfully! ({size_mb:.2f} MB)")


def generate_checksums():
    print("\n[5/5] Generating cryptographic SHA-256 checksums...")
    hasher = hashlib.sha256()
    with open(OUTPUT_INSTALLER, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    sha256 = hasher.hexdigest()

    checksum_line = f"{sha256}  {OUTPUT_INSTALLER.name}\n"
    with open(SHA256_FILE, "w", encoding="utf-8") as f:
        f.write(checksum_line)

    print("=" * 65)
    print("  BUILD COMPLETE!")
    print(f"  * Installer: {OUTPUT_INSTALLER}")
    print(f"  * Size     : {OUTPUT_INSTALLER.stat().st_size / (1024 * 1024):.2f} MB")
    print(f"  * SHA-256  : {sha256}")
    print(f"  * Checksums: {SHA256_FILE}")
    print("=" * 65)


def main():
    try:
        iscc = find_iscc()
        clean()
        build_pyinstaller()
        verify_bundle()
        build_inno_setup(iscc)
        generate_checksums()
    except Exception as e:
        print(f"\n[BUILD ERROR] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
