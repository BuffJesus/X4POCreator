# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the Qt build of PO Builder.
#
# Runs alongside PO_Builder.spec (tkinter) during the v0.10.0 migration —
# both specs produce separate executables in dist/ so the operator can
# run either while the Qt surfaces are being ported to parity.
#
#   build.bat        → PO_Builder.spec → dist/POBuilder.exe        (tk, primary)
#   build.bat qt     → this spec         → dist/POBuilder_Qt.exe   (qt, alpha)
#
# PySide6 ships abi3 wheels that PyInstaller's shipped hooks pick up
# cleanly; collect_all('PySide6') pulls in the plugin directories Qt needs
# at runtime (platforms, styles, imageformats).

import os
from PyInstaller.utils.hooks import collect_all

# ── Collect openpyxl (dynamic imports PyInstaller can miss) ──
openpyxl_datas, openpyxl_binaries, openpyxl_hiddenimports = collect_all('openpyxl')

# ── Collect PySide6 — plugin dirs, QtCore/QtGui/QtWidgets binaries, etc. ──
pyside_datas, pyside_binaries, pyside_hiddenimports = collect_all('PySide6')

# ── Optional bundled assets ──
extra_datas = []
for asset in ('loading.gif', 'loading.wav', 'icon.ico'):
    if os.path.exists(asset):
        extra_datas.append((asset, '.'))

a = Analysis(
    ['po_builder_qt.py'],
    pathex=[],
    binaries=openpyxl_binaries + pyside_binaries,
    datas=extra_datas + openpyxl_datas + pyside_datas,
    hiddenimports=openpyxl_hiddenimports + pyside_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Exclude tkinter-only modules so the Qt build doesn't drag them in
    # accidentally.  PyInstaller's dependency scanner only picks up
    # imports that are actually executed, so this is belt-and-suspenders.
    excludes=[
        'tkinter',
        'tksheet',
        'ttkbootstrap',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# Icon is optional
icon_path = 'icon.ico' if os.path.exists('icon.ico') else None

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='POBuilder_Qt',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)
