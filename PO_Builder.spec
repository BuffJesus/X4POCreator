# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

# ── Collect openpyxl (uses dynamic imports and data files PyInstaller misses) ──
openpyxl_datas, openpyxl_binaries, openpyxl_hiddenimports = collect_all('openpyxl')

# ── Optional bundled assets ──
extra_datas = []
for asset in ('loading.gif', 'loading.wav', 'icon.ico'):
    if os.path.exists(asset):
        extra_datas.append((asset, '.'))

a = Analysis(
    ['po_builder.py'],
    pathex=[],
    binaries=openpyxl_binaries,
    datas=extra_datas + openpyxl_datas,
    hiddenimports=openpyxl_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='POBuilder',
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
