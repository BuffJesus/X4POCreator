"""Qt stylesheet helpers — Tuner-style composed patterns.

Ported line-for-line from the Tuner app's ``cpp/app/theme.hpp``.  Every
helper here consumes tokens from ``theme.py`` and returns a Qt stylesheet
string that can be passed to ``widget.setStyleSheet(...)``.

Design rules (copied from the Tuner's guidance):

- **Three composed helpers carry the grammar**: ``card_style``,
  ``header_strip_style``, ``chip_style``.  Don't grow this API — everything
  else should compose tokens inline at the call site.
- **Semantic accent dispatch** lives in ``theme.zone_accent`` so the mapping
  from intent ("danger") to hue ("#d65a5a") happens exactly once.
- **Reserve ``accent_special``** (purple) for derived/computed surfaces.
  Keeping it scarce is what makes it visually distinctive.

This module is safe to import under a headless test (no QApplication
required).  It returns strings only.
"""

from __future__ import annotations

import theme as t


# ─── Core composed styles ──────────────────────────────────────────────────

def card_style(accent: str | None = None) -> str:
    """Panel card — optionally with a 3px left-accent bar.

    The left-accent bar is the single most recognizable element of the
    visual system: it means "attention here" on content cards and
    "selected" on navigation items.  Pass one of ``theme.ACCENT_*`` or
    ``None`` for the plain (neutral) variant.
    """
    if accent:
        border_left = f"border-left: 3px solid {accent}; "
    else:
        border_left = ""
    return (
        f"background-color: {t.BG_PANEL}; "
        f"border: 1px solid {t.BORDER}; "
        f"{border_left}"
        f"border-radius: {t.RADIUS_MD}px;"
    )


def header_strip_style() -> str:
    """Elevated bg strip used for tab headers and section banners."""
    return (
        f"background-color: {t.BG_ELEVATED}; "
        f"border: 1px solid {t.BORDER}; "
        f"border-radius: {t.RADIUS_MD}px; "
        f"padding: {t.SPACE_XS}px {t.SPACE_MD}px;"
    )


def tab_header_style() -> str:
    """Panel background for the title + breadcrumb row at the top of a tab.

    Slightly less elevated than ``header_strip_style`` — used on page
    content rather than as a standalone banner.
    """
    return (
        f"background-color: {t.BG_PANEL}; "
        f"border: 1px solid {t.BORDER}; "
        f"border-radius: {t.RADIUS_SM}px; "
        f"padding: {t.SPACE_SM}px {t.SPACE_MD}px;"
    )


def chip_style(accent: str | None = None) -> str:
    """Inset chip — small inline value display."""
    border_color = accent or t.BORDER
    return (
        f"background-color: {t.BG_INSET}; "
        f"border: 1px solid {border_color}; "
        f"border-radius: {t.RADIUS_SM}px; "
        f"padding: 2px 8px;"
    )


# ─── Tab header HTML helper ────────────────────────────────────────────────
#
# Ported from theme.hpp::format_tab_header_html.  Produces the
# "title · breadcrumb" label used at the top of every tab:
#
#   [ Bulk Grid   ·   Assign vendors and review draft quantities ]
#
# Progressive disclosure in nav form — title lands loudest, breadcrumb sits
# quietly below.  Intended to set QLabel rich text via setText().

def tab_header_html(title: str, breadcrumb: str) -> str:
    return (
        f"<span style='font-size: {t.FONT_LABEL}px; font-weight: bold; "
        f"color: {t.TEXT_PRIMARY};'>{title}</span>"
        f"<span style='color: {t.TEXT_DIM}; font-size: {t.FONT_SMALL}px;'>"
        f"  \u00b7  {breadcrumb}</span>"
    )


# ─── Number card ───────────────────────────────────────────────────────────
#
# A dashboard readout with a colored top bar.  Used on the Tuner LIVE tab;
# in PO Builder the analogous surface is the bulk grid status strip —
# "38 items · $2,585.58" as a hero number card with a color that tracks
# zone state (ok if all priced, warning if some unknown, danger if mostly
# unknown).

def number_card_style(accent: str, top_border_px: int = 2) -> str:
    return (
        f"background-color: {t.BG_PANEL}; "
        f"border: 1px solid {t.BORDER}; "
        f"border-top: {top_border_px}px solid {accent}; "
        f"border-radius: {t.RADIUS_MD}px; "
        f"padding: {t.SPACE_XS + 2}px {t.SPACE_SM}px;"
    )


def number_card_html(
    value: str,
    units: str,
    title: str,
    accent: str,
    *,
    value_font_size: int = None,
) -> str:
    if value_font_size is None:
        value_font_size = t.FONT_HERO
    return (
        "<div style='text-align: center;'>"
        f"<span style='font-size: {value_font_size}px; font-weight: bold; "
        f"color: {accent};'>{value}</span>"
        f"<span style='color: {t.TEXT_MUTED}; font-size: {t.FONT_SMALL}px;'>"
        f" {units}</span><br>"
        f"<span style='color: {t.TEXT_DIM}; font-size: {t.FONT_MICRO}px;'>"
        f"{title}</span>"
        "</div>"
    )


# ─── Sidebar stylesheet ────────────────────────────────────────────────────
#
# One stylesheet for the whole QListWidget sidebar.  Mirrors the Tuner
# main.cpp pattern exactly: 3px accent_primary left bar on selection, bold
# muted-text items, hover tint, full-width item padding.

def sidebar_style() -> str:
    return (
        # Container
        f"QListWidget {{ background: {t.BG_DEEP}; border: none; "
        f"  border-right: 1px solid {t.BORDER}; outline: none; "
        f"  font-size: {t.FONT_BODY}px; font-weight: bold; }}"
        # Default item state
        f"QListWidget::item {{ padding: {t.SPACE_MD}px {t.SPACE_LG}px; "
        f"  color: {t.TEXT_MUTED}; border: none; }}"
        # Selected (active) item — accent left bar + panel background
        f"QListWidget::item:selected {{ background: {t.BG_PANEL}; "
        f"  color: {t.TEXT_PRIMARY}; "
        f"  border-left: 3px solid {t.ACCENT_PRIMARY}; }}"
        # Hover over non-selected item
        f"QListWidget::item:hover:!selected {{ background: {t.BG_BASE}; "
        f"  color: {t.TEXT_SECONDARY}; }}"
    )


# ─── Scalar editor (three-state) ───────────────────────────────────────────
#
# Ported from theme.hpp::scalar_editor_style.  An input field that tints
# its border based on edit state — default (neutral), ok (after a valid
# stage), warning (after a cross-parameter rule fires).  Used by the
# bulk grid's inline qty editor.

def scalar_editor_style(state: str = "default") -> str:
    state = state.lower().strip()
    if state == "ok":
        accent = t.ACCENT_PRIMARY
        text = t.ACCENT_PRIMARY
        weight = "bold"
    elif state == "warning":
        accent = t.ACCENT_WARNING
        text = t.ACCENT_WARNING
        weight = "bold"
    else:
        accent = t.BORDER
        text = t.TEXT_PRIMARY
        weight = "normal"
    return (
        f"background: {t.BG_ELEVATED}; "
        f"border: 1px solid {accent}; "
        f"border-radius: 3px; padding: 3px 6px; "
        f"color: {text}; "
        f"font-size: {t.FONT_SMALL}px; "
        f"font-weight: {weight};"
    )


# ─── Section header (inside a form) ────────────────────────────────────────

def section_header_style() -> str:
    return (
        f"color: {t.TEXT_SECONDARY}; "
        f"margin-top: {t.SPACE_SM}px; "
        f"padding-top: {t.SPACE_XS + 2}px; "
        f"border-top: 1px solid {t.BORDER};"
    )


def field_label_style() -> str:
    """Muted label in the left column of a form row."""
    return f"color: {t.TEXT_MUTED}; font-size: {t.FONT_SMALL}px;"


def units_label_style() -> str:
    """Dim trailing units label."""
    return f"color: {t.TEXT_DIM}; font-size: {t.FONT_MICRO}px;"


# ─── App-wide baseline stylesheet ──────────────────────────────────────────
#
# Applied at QApplication level so the default Qt widgets (QWidget,
# QLabel, QPushButton, QLineEdit, QComboBox, QTableView, QHeaderView,
# QMenu, QMessageBox) inherit the dark palette without per-widget styling.
# Matches the Tuner's visual baseline.

def app_stylesheet() -> str:
    return f"""
QWidget {{
    background-color: {t.BG_BASE};
    color: {t.TEXT_SECONDARY};
    font-size: {t.FONT_BODY}px;
}}

QMainWindow {{
    background-color: {t.BG_BASE};
}}

QLabel {{
    background: transparent;
    color: {t.TEXT_SECONDARY};
}}

QPushButton {{
    background-color: {t.BG_ELEVATED};
    color: {t.TEXT_PRIMARY};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_SM}px;
    padding: 5px 12px;
    font-size: {t.FONT_BODY}px;
}}
QPushButton:hover {{
    background-color: {t.BG_INSET};
    border-color: {t.BORDER_ACCENT};
}}
QPushButton:pressed {{
    background-color: {t.BG_PANEL};
}}
QPushButton:disabled {{
    color: {t.TEXT_DIM};
    background-color: {t.BG_PANEL};
    border-color: {t.BORDER_SOFT};
}}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {t.BG_INSET};
    color: {t.TEXT_PRIMARY};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_SM}px;
    padding: 3px 6px;
    selection-background-color: {t.FILL_PRIMARY_SOFT};
    selection-color: {t.TEXT_PRIMARY};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {t.BORDER_ACCENT};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QMenu {{
    background-color: {t.BG_PANEL};
    color: {t.TEXT_PRIMARY};
    border: 1px solid {t.BORDER};
}}
QMenu::item:selected {{
    background-color: {t.FILL_PRIMARY_SOFT};
}}

QScrollBar:vertical {{
    background: {t.BG_BASE};
    width: 12px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {t.BORDER};
    border-radius: 6px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: #404652;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: {t.BG_BASE};
    height: 12px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {t.BORDER};
    border-radius: 6px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #404652;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QHeaderView::section {{
    background-color: {t.BG_ELEVATED};
    color: {t.TEXT_PRIMARY};
    padding: 4px 8px;
    border: none;
    border-right: 1px solid {t.BORDER};
    border-bottom: 1px solid {t.BORDER};
    font-weight: bold;
}}

QTableView, QTreeView, QListView {{
    background-color: {t.BG_PANEL};
    color: {t.TEXT_SECONDARY};
    alternate-background-color: {t.BG_BASE};
    border: 1px solid {t.BORDER};
    gridline-color: {t.BORDER_SOFT};
    selection-background-color: {t.FILL_PRIMARY_SOFT};
    selection-color: {t.TEXT_PRIMARY};
}}

QToolTip {{
    background-color: {t.BG_ELEVATED};
    color: {t.TEXT_PRIMARY};
    border: 1px solid {t.BORDER_ACCENT};
    padding: 4px 8px;
}}

QStatusBar {{
    background-color: {t.BG_DEEP};
    color: {t.TEXT_MUTED};
    border-top: 1px solid {t.BORDER};
}}
QStatusBar::item {{
    border: none;
}}

QMessageBox {{
    background-color: {t.BG_PANEL};
}}
"""
