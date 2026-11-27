# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Dungeons & Desktops desktop pet."""

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"

datas: list = []
binaries: list = []
hiddenimports: list[str] = [
    *collect_submodules("dungeons_desktops"),
]

# Bundle PySide6 Qt plugins (platforms, imageformats, etc.).
pyside_datas, pyside_binaries, pyside_hidden = collect_all("PySide6")
datas += pyside_datas
binaries += pyside_binaries
hiddenimports += pyside_hidden

if sys.platform == "darwin":
    hiddenimports += [
        "Quartz",
        "AppKit",
        "objc",
        "Foundation",
        "CoreFoundation",
    ]

excludes = [
    "pytest",
    "ruff",
    "tkinter",
    "unittest",
]

a = Analysis(
    [str(ROOT / "packaging" / "run_desktop.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Dungeons and Desktops",
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Dungeons and Desktops",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Dungeons and Desktops.app",
        icon=None,
        bundle_identifier="com.werd6.dungeons-and-desktops",
        info_plist={
            "CFBundleName": "Dungeons & Desktops",
            "CFBundleDisplayName": "Dungeons & Desktops",
            "CFBundleShortVersionString": "0.1.0",
            "NSHighResolutionCapable": True,
            "LSUIElement": True,
        },
    )
