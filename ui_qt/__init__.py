"""PySide6 UI package for PO Builder.

This package contains the Qt-based UI.  It imports the same flow modules
(``load_flow``, ``assignment_flow``, ``export_flow``, etc.), reads and
writes the same on-disk JSON files, and calls the same pure-logic packages
(``rules/``, ``parsers/``, ``models/``).

Style tokens come from the framework-independent ``theme.py``; Qt-specific
stylesheet helpers live in ``theme_qt.py`` at the repo root.
"""
