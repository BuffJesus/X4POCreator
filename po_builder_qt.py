"""PySide6 entry point for PO Builder.

Runs alongside the tkinter ``po_builder.py`` entry point during the
v0.10.0 migration.  Build via ``build.bat qt`` → ``dist/POBuilder_Qt.exe``.

This file stays thin — it's the glue that:
  1. Picks up the app version from ``app_version.py``
  2. Creates the ``QApplication``
  3. Applies the global stylesheet from ``theme_qt.app_stylesheet``
  4. Instantiates ``ui_qt.shell.POBuilderShell``
  5. Runs the event loop

All logic lives in flow modules (``load_flow`` etc.) and all UI lives in
``ui_qt/``.  Keep this file to just the bootstrap.
"""

from __future__ import annotations

import sys

from app_version import APP_VERSION


def main() -> int:
    # Import Qt lazily so the import cost is only paid when this entry
    # point is actually invoked (helps tests that just import modules).
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication

    import theme_qt as tq
    from ui_qt.shell import POBuilderShell

    # Enable high-DPI scaling via Qt's modern per-monitor mode.  The
    # AA_EnableHighDpiScaling / AA_UseHighDpiPixmaps attributes are
    # deprecated in Qt 6 because they're enabled by default — setting
    # the rounding policy is the remaining opt-in.
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("PO Builder")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("POBuilder")

    # Apply the app-wide stylesheet so every default Qt widget inherits
    # the dark palette without per-widget styling.
    app.setStyleSheet(tq.app_stylesheet())

    shell = POBuilderShell(app_version=APP_VERSION)
    shell.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
