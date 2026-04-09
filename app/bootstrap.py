"""Application bootstrap: dark theme setup and entry point."""

from tkinter import ttk


def apply_dark_theme(root):
    """Apply a dark mode theme with purple accents."""
    # Color palette
    BG = "#1e1e2e"           # main background
    BG_LIGHT = "#2a2a3d"     # slightly lighter panels
    BG_WIDGET = "#333348"    # entry/combo backgrounds
    FG = "#e0e0e8"           # main text
    FG_DIM = "#9090a8"       # secondary text
    PURPLE = "#b48ead"       # primary accent
    PURPLE_BRIGHT = "#c9a0dc" # hover / highlight
    PURPLE_DARK = "#7c5e8a"  # pressed / selection
    BORDER = "#444460"       # subtle borders
    RED = "#f07070"          # warnings
    TREE_BG = "#252538"      # treeview background
    TREE_ALT = "#2c2c42"     # alternate row
    TREE_SEL = "#5b4670"     # selected row

    root.configure(bg=BG)
    root.option_add("*TCombobox*Listbox.background", BG_WIDGET)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", PURPLE_DARK)
    root.option_add("*TCombobox*Listbox.selectForeground", FG)

    style = ttk.Style()
    style.theme_use("clam")

    # ── Global defaults ──
    style.configure(".", background=BG, foreground=FG, fieldbackground=BG_WIDGET,
                     bordercolor=BORDER, troughcolor=BG_LIGHT, font=("Segoe UI", 10),
                     insertcolor=FG, selectbackground=PURPLE_DARK, selectforeground=FG)

    # ── Frames & Labels ──
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("TLabelframe", background=BG, foreground=PURPLE, bordercolor=BORDER)
    style.configure("TLabelframe.Label", background=BG, foreground=PURPLE, font=("Segoe UI", 10, "bold"))

    # ── Notebook ──
    style.configure("TNotebook", background=BG, bordercolor=BORDER)
    style.configure("TNotebook.Tab", background=BG_LIGHT, foreground=FG_DIM,
                     padding=[14, 7], font=("Segoe UI", 10))
    style.map("TNotebook.Tab",
              background=[("selected", BG), ("active", BG_WIDGET)],
              foreground=[("selected", PURPLE_BRIGHT), ("active", FG)])

    # ── Buttons ──
    style.configure("TButton", background=BG_WIDGET, foreground=FG,
                     bordercolor=BORDER, padding=[10, 5], font=("Segoe UI", 10))
    style.map("TButton",
              background=[("active", PURPLE_DARK), ("pressed", PURPLE)],
              foreground=[("active", FG), ("pressed", FG)])

    style.configure("Big.TButton", background=PURPLE_DARK, foreground=FG,
                     font=("Segoe UI", 10, "bold"), padding=[16, 7], bordercolor=PURPLE)
    style.map("Big.TButton",
              background=[("active", PURPLE), ("pressed", PURPLE_BRIGHT)])

    # ── Entries & Combos ──
    style.configure("TEntry", fieldbackground=BG_WIDGET, foreground=FG,
                     insertcolor=FG, bordercolor=BORDER)
    style.map("TEntry", fieldbackground=[("focus", "#3a3a52")])

    style.configure("TCombobox", fieldbackground=BG_WIDGET, foreground=FG,
                     background=BG_WIDGET, arrowcolor=PURPLE, bordercolor=BORDER)
    style.map("TCombobox", fieldbackground=[("focus", "#3a3a52")],
              background=[("active", BG_LIGHT)])

    # ── Checkbuttons ──
    style.configure("TCheckbutton", background=BG, foreground=FG, indicatorcolor=BG_WIDGET)
    style.map("TCheckbutton",
              background=[("active", BG_LIGHT)],
              indicatorcolor=[("selected", PURPLE), ("active", PURPLE_DARK)])

    # ── Progressbar ──
    style.configure("TProgressbar", background=PURPLE, troughcolor=BG_LIGHT, bordercolor=BORDER)

    # ── Scrollbar ──
    style.configure("TScrollbar", background=BG_LIGHT, troughcolor=BG,
                     bordercolor=BORDER, arrowcolor=PURPLE)
    style.map("TScrollbar", background=[("active", PURPLE_DARK)])

    # ── Treeview ──
    style.configure("Treeview", background=TREE_BG, foreground=FG,
                     fieldbackground=TREE_BG, bordercolor=BORDER, font=("Segoe UI", 9))
    style.configure("Treeview.Heading", background=BG_WIDGET, foreground=PURPLE_BRIGHT,
                     bordercolor=BORDER, font=("Segoe UI", 9, "bold"))
    style.map("Treeview",
              background=[("selected", TREE_SEL)],
              foreground=[("selected", FG)])
    style.map("Treeview.Heading",
              background=[("active", PURPLE_DARK)])

    # ── Custom label styles ──
    style.configure("Header.TLabel", font=("Segoe UI", 13, "bold"), foreground=PURPLE_BRIGHT, background=BG)
    style.configure("SubHeader.TLabel", font=("Segoe UI", 10), foreground=FG_DIM, background=BG)
    style.configure("Info.TLabel", font=("Segoe UI", 9), foreground=FG_DIM, background=BG)
    style.configure("Warning.TLabel", font=("Segoe UI", 9, "bold"), foreground=RED, background=BG)
    style.configure("Path.TLabel", font=("Segoe UI", 8, "italic"), foreground="#7a7a95", background=BG)

    return style
