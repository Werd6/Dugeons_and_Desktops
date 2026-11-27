# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Dungeons & Desktops desktop pet."""

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"
ICONS = ROOT / "packaging" / "icons"
APP_ICNS = ICONS / "app.icns"
APP_ICO = ICONS / "app.ico"

datas: list = []
binaries: list = []
hiddenimports: list[str] = [
    *collect_submodules("dungeons_desktops"),
]

# Bundle PySide6 Qt plugins (platforms, imageformats, etc.).
# Drop Qt tool .app bundles — they break Developer ID deep codesign.
_SKIP_BUNDLE_NAMES = {
    "Assistant.app",
    "Assistant__dot__app",
    "Designer.app",
    "Designer__dot__app",
    "Linguist.app",
    "Linguist__dot__app",
}


def _without_qt_tools(entries: list) -> list:
    kept = []
    for entry in entries:
        src = Path(entry[0])
        if src.name in _SKIP_BUNDLE_NAMES:
            continue
        if any(part in _SKIP_BUNDLE_NAMES for part in src.parts):
            continue
        kept.append(entry)
    return kept


pyside_datas, pyside_binaries, pyside_hidden = collect_all("PySide6")
datas += _without_qt_tools(pyside_datas)
binaries += _without_qt_tools(pyside_binaries)
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

# Prefer signing via packaging/macos/sign_and_notarize.sh after the build
# (deep + hardened runtime + notarization). Leave PyInstaller's identity empty.
_exe_icon = str(APP_ICNS) if sys.platform == "darwin" and APP_ICNS.exists() else (
    str(APP_ICO) if APP_ICO.exists() else None
)
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
    icon=_exe_icon,
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
        icon=str(APP_ICNS) if APP_ICNS.exists() else None,
        bundle_identifier="com.werd6.dungeons-and-desktops",
        info_plist={
            "CFBundleName": "Dungeons & Desktops",
            "CFBundleDisplayName": "Dungeons & Desktops",
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleIconFile": "app.icns",
            "NSHighResolutionCapable": True,
            "LSUIElement": True,
        },
    )
