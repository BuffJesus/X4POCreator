"""Keyboard shortcut overlay — press ? to show, Escape to dismiss."""

import tkinter as tk


# Shortcut definitions grouped by category
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
        ("▸ More Actions", "Toggle advanced actions"),
    ]),
]


def show_shortcut_overlay(app):
    """Show a semi-transparent overlay listing all keyboard shortcuts."""
    root = getattr(app, "root", None)
    if root is None:
        return

    overlay = tk.Toplevel(root)
    overlay.title("Keyboard Shortcuts")
    overlay.configure(bg="#1a1a2e")
    overlay.transient(root)
    overlay.grab_set()

    # Center on parent
    overlay.update_idletasks()
    w, h = 520, 480
    x = root.winfo_x() + (root.winfo_width() - w) // 2
    y = root.winfo_y() + (root.winfo_height() - h) // 2
    overlay.geometry(f"{w}x{h}+{x}+{y}")
    overlay.resizable(False, False)

    # Title
    tk.Label(
        overlay, text="Keyboard Shortcuts", font=("Segoe UI", 14, "bold"),
        bg="#1a1a2e", fg="#8098b0",
    ).pack(pady=(16, 8))

    # Scrollable content
    canvas = tk.Canvas(overlay, bg="#1a1a2e", highlightthickness=0)
    scrollbar = tk.Scrollbar(overlay, orient="vertical", command=canvas.yview)
    content = tk.Frame(canvas, bg="#1a1a2e")

    content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=content, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=16)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    for group_name, shortcuts in SHORTCUT_GROUPS:
        # Group header
        tk.Label(
            content, text=group_name, font=("Segoe UI", 10, "bold"),
            bg="#1a1a2e", fg="#6090b0", anchor="w",
        ).pack(fill=tk.X, pady=(12, 4))

        for key, desc in shortcuts:
            row = tk.Frame(content, bg="#1a1a2e")
            row.pack(fill=tk.X, pady=1)
            tk.Label(
                row, text=key, font=("Consolas", 9),
                bg="#252540", fg="#c0d0e0", width=24, anchor="w",
                padx=8, pady=2,
            ).pack(side=tk.LEFT)
            tk.Label(
                row, text=desc, font=("Segoe UI", 9),
                bg="#1a1a2e", fg="#a0a8b0", anchor="w",
                padx=8, pady=2,
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)

    # Dismiss hint
    tk.Label(
        overlay, text="Press Escape or ? to close",
        font=("Segoe UI", 8), bg="#1a1a2e", fg="#505868",
    ).pack(pady=(8, 12))

    def _dismiss(event=None):
        try:
            overlay.destroy()
        except Exception:
            pass

    overlay.bind("<Escape>", _dismiss)
    overlay.bind("?", _dismiss)
    overlay.bind("<question>", _dismiss)
    overlay.focus_set()
