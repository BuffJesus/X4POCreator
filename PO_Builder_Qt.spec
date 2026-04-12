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

# ── PySide6 surgical collection ──
#
# collect_all('PySide6') pulls in ~250 MB of Qt modules we don't use
# (QtWebEngine, Qt3D, QtMultimedia, QtNetwork, QtQml, QtQuick, QtPdf,
# QtCharts, QtDataVisualization, QtPositioning, QtRemoteObjects,
# QtScxml, QtSensors, QtSerialBus, QtSerialPort, QtSql, QtSvg, QtTest,
# QtWebChannel, QtWebSockets, QtXml, ...).
#
# PO Builder only imports QtCore, QtGui, and QtWidgets.  Collect just
# those three submodules explicitly so the resulting exe lands at
# ~90-100 MB instead of ~260 MB.  Re-add any module here (plus its
# hiddenimport alongside the import in the Python source) if a future
# alpha phase needs it.

_pyside_binaries = []
_pyside_datas = []
_pyside_hiddenimports = []
for _submod in ('PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets'):
    d, b, h = collect_all(_submod)
    _pyside_datas += d
    _pyside_binaries += b
    _pyside_hiddenimports += h

# Explicitly pull in the `shiboken6` runtime that every PySide6 module
# depends on, plus the Qt plugin directories (platforms, styles,
# imageformats) under PySide6 itself without dragging in the addon
# modules.
shiboken_datas, shiboken_binaries, shiboken_hiddenimports = collect_all('shiboken6')

# ── Optional bundled assets ──
extra_datas = []
for asset in ('loading.gif', 'loading.wav', 'icon.ico'):
    if os.path.exists(asset):
        extra_datas.append((asset, '.'))

a = Analysis(
    ['po_builder_qt.py'],
    pathex=[],
    binaries=openpyxl_binaries + _pyside_binaries + shiboken_binaries,
    datas=extra_datas + openpyxl_datas + _pyside_datas + shiboken_datas,
    hiddenimports=(
        openpyxl_hiddenimports
        + _pyside_hiddenimports
        + shiboken_hiddenimports
        + ['PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets']
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Exclude tkinter and every unused Qt module so the Qt build doesn't
    # drag them in accidentally.  PyInstaller's dependency scanner only
    # picks up imports that are actually executed, so these excludes are
    # belt-and-suspenders — they also prevent any stray `from PySide6
    # import *` elsewhere in the repo from ballooning the build.
    excludes=[
        'tkinter',
        'tksheet',
        'ttkbootstrap',
        # Heavy PySide6 submodules we definitely don't use
        'PySide6.Qt3DAnimation', 'PySide6.Qt3DCore', 'PySide6.Qt3DExtras',
        'PySide6.Qt3DInput', 'PySide6.Qt3DLogic', 'PySide6.Qt3DRender',
        'PySide6.QtBluetooth', 'PySide6.QtCharts', 'PySide6.QtDataVisualization',
        'PySide6.QtDBus', 'PySide6.QtDesigner', 'PySide6.QtHelp',
        'PySide6.QtHttpServer', 'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets', 'PySide6.QtNetwork',
        'PySide6.QtNetworkAuth', 'PySide6.QtNfc', 'PySide6.QtOpenGL',
        'PySide6.QtOpenGLWidgets', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
        'PySide6.QtPositioning', 'PySide6.QtPrintSupport',
        'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuick3D',
        'PySide6.QtQuickControls2', 'PySide6.QtQuickWidgets',
        'PySide6.QtRemoteObjects', 'PySide6.QtScxml', 'PySide6.QtSensors',
        'PySide6.QtSerialBus', 'PySide6.QtSerialPort', 'PySide6.QtSpatialAudio',
        'PySide6.QtSql', 'PySide6.QtStateMachine', 'PySide6.QtSvg',
        'PySide6.QtSvgWidgets', 'PySide6.QtTest', 'PySide6.QtTextToSpeech',
        'PySide6.QtUiTools', 'PySide6.QtWebChannel', 'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineQuick', 'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebSockets', 'PySide6.QtWebView', 'PySide6.QtXml',
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
