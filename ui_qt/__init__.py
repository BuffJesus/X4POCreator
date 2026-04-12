"""PySide6 UI package for PO Builder (v0.10.0 migration in progress).

This package contains the Qt-based rewrite of the PO Builder UI.  During
the migration it runs **alongside** the tkinter UI — both import the same
flow modules (``load_flow``, ``assignment_flow``, ``export_flow``, etc.),
both read and write the same on-disk JSON files, and both call the same
pure-logic packages (``rules/``, ``parsers/``, ``models/``).

Surfaces are migrated one phase at a time.  The tkinter entry point
``po_builder.py`` stays the default build target until the Qt version
(``po_builder_qt.py``) reaches feature parity.

Style tokens come from the framework-independent ``theme.py``; Qt-specific
stylesheet helpers live in ``theme_qt.py`` at the repo root.
"""
