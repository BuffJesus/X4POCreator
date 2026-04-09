"""Application bootstrap: dark theme setup and entry point."""

from tkinter import ttk


def _is_ttkbootstrap_active(root):
    """Return True if the root window was created by ttkbootstrap."""
    return hasattr(root, "style") and type(root).__module__.startswith("ttkbootstrap")


def apply_dark_theme(root):
    """Apply custom label styles (and optionally full theme).

    When ttkbootstrap is active, only the custom label styles are
    defined — ttkbootstrap handles all base widget styling.  When
    running on plain tkinter, the full dark theme is applied.
    """
    style = ttk.Style()

    if _is_ttkbootstrap_active(root):
        # ttkbootstrap handles base styling.  Just define the custom
        # label variants that 100+ UI references depend on.
        colors = root.style.colors
        BG = colors.bg
        FG = colors.fg
        FG_DIM = colors.secondary
        ACCENT = colors.primary
        RED = colors.danger

        style.configure("Header.TLabel", font=("Segoe UI", 13, "bold"), foreground=ACCENT, background=BG)
        style.configure("SubHeader.TLabel", font=("Segoe UI", 10), foreground=FG_DIM, background=BG)
        style.configure("Info.TLabel", font=("Segoe UI", 9), foreground=FG_DIM, background=BG)
        style.configure("Warning.TLabel", font=("Segoe UI", 9, "bold"), foreground=RED, background=BG)
        style.configure("Path.TLabel", font=("Segoe UI", 8, "italic"), foreground=FG_DIM, background=BG)
        style.configure("Big.TButton", font=("Segoe UI", 10, "bold"), padding=[16, 7])
        return style

    # ── Full theme for plain tkinter ──
    BG = "#1e1e2e"
    BG_LIGHT = "#2a2a3d"
    BG_WIDGET = "#333348"
    FG = "#e0e0e8"
    FG_DIM = "#9090a8"
    PURPLE = "#b48ead"
    PURPLE_BRIGHT = "#c9a0dc"
    PURPLE_DARK = "#7c5e8a"
    BORDER = "#444460"
    RED = "#f07070"
    TREE_BG = "#252538"
    TREE_ALT = "#2c2c42"
    TREE_SEL = "#5b4670"

    root.configure(bg=BG)
    root.option_add("*TCombobox*Listbox.background", BG_WIDGET)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", PURPLE_DARK)
    root.option_add("*TCombobox*Listbox.selectForeground", FG)

    style.theme_use("clam")

    style.configure(".", background=BG, foreground=FG, fieldbackground=BG_WIDGET,
                     bordercolor=BORDER, troughcolor=BG_LIGHT, font=("Segoe UI", 10),
                     insertcolor=FG, selectbackground=PURPLE_DARK, selectforeground=FG)

    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("TLabelframe", background=BG, foreground=PURPLE, bordercolor=BORDER)
    style.configure("TLabelframe.Label", background=BG, foreground=PURPLE, font=("Segoe UI", 10, "bold"))

    style.configure("TNotebook", background=BG, bordercolor=BORDER)
    style.configure("TNotebook.Tab", background=BG_LIGHT, foreground=FG_DIM,
                     padding=[14, 7], font=("Segoe UI", 10))
    style.map("TNotebook.Tab",
              background=[("selected", BG), ("active", BG_WIDGET)],
              foreground=[("selected", PURPLE_BRIGHT), ("active", FG)])

    style.configure("TButton", background=BG_WIDGET, foreground=FG,
                     bordercolor=BORDER, padding=[10, 5], font=("Segoe UI", 10))
    style.map("TButton",
              background=[("active", PURPLE_DARK), ("pressed", PURPLE)],
              foreground=[("active", FG), ("pressed", FG)])

    style.configure("Big.TButton", background=PURPLE_DARK, foreground=FG,
                     font=("Segoe UI", 10, "bold"), padding=[16, 7], bordercolor=PURPLE)
    style.map("Big.TButton",
              background=[("active", PURPLE), ("pressed", PURPLE_BRIGHT)])

    style.configure("TEntry", fieldbackground=BG_WIDGET, foreground=FG,
                     insertcolor=FG, bordercolor=BORDER)
    style.map("TEntry", fieldbackground=[("focus", "#3a3a52")])

    style.configure("TCombobox", fieldbackground=BG_WIDGET, foreground=FG,
                     background=BG_WIDGET, arrowcolor=PURPLE, bordercolor=BORDER)
    style.map("TCombobox", fieldbackground=[("focus", "#3a3a52")],
              background=[("active", BG_LIGHT)])

    style.configure("TCheckbutton", background=BG, foreground=FG, indicatorcolor=BG_WIDGET)
    style.map("TCheckbutton",
              background=[("active", BG_LIGHT)],
              indicatorcolor=[("selected", PURPLE), ("active", PURPLE_DARK)])

    style.configure("TProgressbar", background=PURPLE, troughcolor=BG_LIGHT, bordercolor=BORDER)

    style.configure("TScrollbar", background=BG_LIGHT, troughcolor=BG,
                     bordercolor=BORDER, arrowcolor=PURPLE)
    style.map("TScrollbar", background=[("active", PURPLE_DARK)])

    style.configure("Treeview", background=TREE_BG, foreground=FG,
                     fieldbackground=TREE_BG, bordercolor=BORDER, font=("Segoe UI", 9))
    style.configure("Treeview.Heading", background=BG_WIDGET, foreground=PURPLE_BRIGHT,
                     bordercolor=BORDER, font=("Segoe UI", 9, "bold"))
    style.map("Treeview",
              background=[("selected", TREE_SEL)],
              foreground=[("selected", FG)])
    style.map("Treeview.Heading",
              background=[("active", PURPLE_DARK)])

    style.configure("Header.TLabel", font=("Segoe UI", 13, "bold"), foreground=PURPLE_BRIGHT, background=BG)
    style.configure("SubHeader.TLabel", font=("Segoe UI", 10), foreground=FG_DIM, background=BG)
    style.configure("Info.TLabel", font=("Segoe UI", 9), foreground=FG_DIM, background=BG)
    style.configure("Warning.TLabel", font=("Segoe UI", 9, "bold"), foreground=RED, background=BG)
    style.configure("Path.TLabel", font=("Segoe UI", 8, "italic"), foreground="#7a7a95", background=BG)

    return style
