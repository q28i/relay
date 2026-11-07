# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Specification for Relay WhatsApp Bulk Messenger Pro.
Builds a fast-starting, standalone Windows folder bundle (onedir).
"""

import os
import sys

block_cipher = None

project_dir = os.path.abspath(SPECPATH)

datas = [
    (os.path.join(project_dir, 'backend', 'static'), os.path.join('backend', 'static')),
    (os.path.join(project_dir, 'assets'), 'assets'),
]

excludes = [
    'pytest',
    '_pytest',
    'unittest',
    'test',
    'tests',
    'pdb',
    'pdbpp',
    'doctest',
    'tkinter',
    'Tkinter',
    'matplotlib',
    'scipy',
    'pandas',
    'numpy',
    'IPython',
    'jupyter',
]

hiddenimports = [
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespans',
    'uvicorn.lifespans.on',
    'engineio.async_drivers.asgi',
    'sqlite3',
    'openpyxl',
    'selenium',
    'selenium.webdriver',
    'selenium.webdriver.chrome.options',
    'selenium.webdriver.edge.options',
    'selenium.webdriver.common.by',
    'backend.paths',
    'backend.updater_service',
    'backend.routers.updater',
    'backend.routers.contacts',
    'backend.routers.templates',
    'backend.routers.campaigns',
    'backend.routers.jobs',
    'backend.routers.config',
    'backend.routers.browser',
    'backend.routers.logs',
    'backend.routers.ws',
    'backend.routers.media',
    'backend.routers.collections',
    'backend.routers.sets',
]

a = Analysis(
    ['relay_launcher.py'],
    pathex=[project_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Relay',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_dir, 'assets', 'relay.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Relay',
)
