"""Main application shell — sidebar navigation + stacked content pages.

Ported from the Tuner's ``cpp/app/main.cpp`` MainWindow pattern:

    [ sidebar ][      stacked content page      ]
    [ Load    ][                                 ]
    [ Filter  ][    current page fills available]
    [ Bulk    ][    space                        ]
    [ Review  ][                                 ]
    [ Help    ][                                 ]
    [---------][                                 ]
    [ v0.10.0 ][                                 ]

The sidebar is a ``QListWidget`` styled via ``theme_qt.sidebar_style()`` so
the 3px ``accent_primary`` left bar on the selected item matches the same
"attention here" grammar used by ``card_style(accent=...)`` on content
cards.

Pages are placeholder ``QWidget`` instances in alpha1.  Each alpha phase
replaces one placeholder with the real surface:

    alpha1  (this)  — empty shell, all placeholders
    alpha2          — Load + Help
    alpha3          — Bulk grid
    alpha4          — Review, Export, dialogs
    beta1           — Command palette, shortcuts, polish
    release         — Delete tk, rename qt → primary

This module does not import any flow modules directly — pages hook into
them themselves.  Keep the shell UI-only so it's trivial to test.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

import theme as t
import theme_qt as tq


# Sidebar nav items — matches the confirmed tkinter tab order for v0.10.0
# alpha1: Load → Filter → Bulk → Review → Help.  The filter tab in tk is a
# pair (line-code exclusion + customer exclusion); for now the Qt port
# keeps them as a single "Filter" entry — we'll decide whether to split or
# combine when alpha2 lands.
NAV_ITEMS = [
    ("Load",   "Load CSV source reports"),
    ("Filter", "Exclude line codes and customers"),
    ("Bulk",   "Assign vendors and review draft quantities"),
    ("Review", "Review exceptions and export POs"),
    ("Help",   "Documentation, shortcuts, and release notes"),
]


def _placeholder_page(title: str, breadcrumb: str, phase: str) -> QWidget:
    """Build a placeholder page for a surface not yet ported.

    Each placeholder shows the tab's title + breadcrumb banner (using the
    shared ``tab_header_html`` helper so every page's header reads the
    same way) and a dim message explaining which alpha will port it.
    """
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
    layout.setSpacing(t.SPACE_MD)

    header = QLabel()
    header.setTextFormat(Qt.RichText)
    header.setText(tq.tab_header_html(title, breadcrumb))
    header.setStyleSheet(tq.tab_header_style())
    layout.addWidget(header)

    body = QLabel(f"This surface is migrating in {phase}.\n\n"
                  f"Until then, use the tkinter build (POBuilder.exe) for this workflow.")
    body.setAlignment(Qt.AlignCenter)
    body.setWordWrap(True)
    body.setStyleSheet(
        f"color: {t.TEXT_DIM}; "
        f"font-size: {t.FONT_BODY}px; "
        f"background-color: {t.BG_PANEL}; "
        f"border: 1px solid {t.BORDER_SOFT}; "
        f"border-radius: {t.RADIUS_MD}px; "
        f"padding: {t.SPACE_XL}px;"
    )
    layout.addWidget(body, stretch=1)

    return page


class POBuilderShell(QMainWindow):
    """Top-level window: sidebar + stacked content + status bar."""

    def __init__(self, app_version: str = "", parent=None):
        super().__init__(parent)
        self.app_version = app_version
        self.setWindowTitle(f"PO Builder (Qt) — v{app_version}" if app_version else "PO Builder (Qt)")
        self.resize(1280, 800)
        self.setMinimumSize(QSize(960, 600))

        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # ─── Sidebar ──────────────────────────────────────────────────
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(160)
        self.sidebar.setStyleSheet(tq.sidebar_style())
        self.sidebar.setFocusPolicy(Qt.NoFocus)  # keyboard focus goes to content
        for label, _tooltip in NAV_ITEMS:
            item = QListWidgetItem(label)
            item.setSizeHint(QSize(160, 44))
            self.sidebar.addItem(item)
        h.addWidget(self.sidebar)

        # ─── Stacked content ──────────────────────────────────────────
        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background-color: {t.BG_BASE};")
        for label, tooltip in NAV_ITEMS:
            phase_map = {
                "Load":   "alpha2",
                "Filter": "alpha2",
                "Bulk":   "alpha3",
                "Review": "alpha4",
                "Help":   "alpha2",
            }
            phase = phase_map.get(label, "a later alpha")
            self.stack.addWidget(_placeholder_page(label, tooltip, phase))
        h.addWidget(self.stack, stretch=1)

        self.setCentralWidget(central)

        # Navigate on sidebar selection
        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sidebar.setCurrentRow(0)

        # ─── Status bar ───────────────────────────────────────────────
        self.status = QStatusBar()
        self.status.setSizeGripEnabled(False)
        version_label = QLabel(f"v{app_version} — Qt alpha" if app_version else "Qt alpha")
        version_label.setStyleSheet(f"color: {t.TEXT_DIM}; padding: 0 {t.SPACE_MD}px;")
        self.status.addPermanentWidget(version_label)
        self.setStatusBar(self.status)

        # Ctrl+K placeholder — wired in beta1 with the Qt command palette.
        # Register the shortcut now so the keystroke is a known no-op
        # rather than a random keypress dropping through to whatever has
        # focus.
        self._ctrl_k_action = QAction("Command Palette", self)
        self._ctrl_k_action.setShortcut(QKeySequence("Ctrl+K"))
        self._ctrl_k_action.triggered.connect(self._on_ctrl_k)
        self.addAction(self._ctrl_k_action)

    def _on_ctrl_k(self):
        self.status.showMessage(
            "Command palette lands in beta1 — use the sidebar for now.",
            4000,
        )
