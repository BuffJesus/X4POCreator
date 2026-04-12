"""Pure-data definitions for the Load tab.

Separated from ``ui_load.py`` so both the tkinter UI *and* the Qt UI
(``ui_qt/load_tab.py``) can pull the source-of-truth file-section
layout without transitively importing tkinter.  This file must stay
framework-independent — no tkinter, no PySide6, no widget imports.

The v0.10.0 Qt build excludes ``tkinter`` from its PyInstaller spec,
so the Qt entry point crashes at runtime if it imports anything that
reaches tkinter at module-import time.  Keeping the pure data here
means the Qt build imports the constants without paying that cost.
"""


LOAD_FILE_SECTIONS = (
    {
        "title": "Core Files",
        "summary": "Preferred daily workflow. These files should cover the main assignment and reorder path.",
        "rows": (
            {
                "label": "Detailed Part Sales CSV",
                "attr_name": "var_detailed_sales_path",
                "browse_key": "detailedsales",
                "hint": "Preferred sales source. Use with Received Parts Detail.",
            },
            {
                "label": "Received Parts Detail CSV",
                "attr_name": "var_received_parts_path",
                "browse_key": "receivedparts",
                "hint": "Preferred receiving source. Use with Detailed Part Sales.",
            },
            {
                "label": "On Hand Min/Max Sales CSV",
                "attr_name": "var_minmax_path",
                "browse_key": "minmax",
                "hint": "Primary inventory/min-max source for reorder decisions.",
            },
            {
                "label": "Order Multiples / Pack Sizes CSV",
                "attr_name": "var_packsize_path",
                "browse_key": "packsize",
                "hint": "Pack-size source for ordering behavior.",
            },
        ),
    },
    {
        "title": "Optional Support Files",
        "summary": "Useful when available, but not required to load the core workflow.",
        "rows": (
            {
                "label": "On Hand Report CSV",
                "attr_name": "var_onhand_path",
                "browse_key": "onhand",
                "hint": "Adds inventory cost/QOH coverage where needed.",
            },
            {
                "label": "Open PO Listing CSV",
                "attr_name": "var_po_path",
                "browse_key": "po",
                "hint": "Adds open-PO protection and review context.",
            },
            {
                "label": "Suspended Items CSV",
                "attr_name": "var_susp_path",
                "browse_key": "susp",
                "hint": "Adds suspense demand and review context.",
            },
        ),
    },
)


def iter_load_file_rows():
    """Yield every file-picker row across all sections in order."""
    for section in LOAD_FILE_SECTIONS:
        for row in section["rows"]:
            yield row
