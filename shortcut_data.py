"""Keyboard shortcut groups — pure data, no UI dependencies."""

SHORTCUT_GROUPS = [
    ("Navigation", [
        ("Enter", "View item details"),
        ("F2 / Double-click", "Edit cell"),
        ("Tab / Shift+Tab", "Next / prev editable column"),
        ("Home / End", "Jump to first / last column"),
        ("Ctrl+Arrow", "Jump to edge"),
        ("Shift+Arrow", "Extend selection"),
    ]),
    ("Editing", [
        ("Ctrl+Z / Ctrl+Y", "Undo / Redo"),
        ("Ctrl+D", "Fill down from top cell"),
        ("Ctrl+R", "Fill right"),
        ("Ctrl+Enter", "Apply value to selection"),
        ("Delete / Backspace", "Remove selected rows"),
    ]),
    ("Selection", [
        ("Ctrl+A", "Select all cells"),
        ("Ctrl+Shift+A", "Select all rows"),
        ("Shift+Space", "Select current row"),
        ("Ctrl+Space", "Select current column"),
        ("Escape", "Clear selection"),
    ]),
    ("Grid", [
        ("Click header", "Sort by column"),
        ("Double-click header", "Auto-size columns"),
        ("Right-click header", "Show/hide columns"),
        ("Ctrl+F", "Focus search box"),
        ("Ctrl+C / Ctrl+V", "Copy / Paste"),
    ]),
    ("Quick Filters", [
        ("Quick buttons above filters", "One-click filter presets"),
        ("More Actions", "Toggle advanced actions"),
    ]),
]
