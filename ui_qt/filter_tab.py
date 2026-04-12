"""Qt Filter tab — line code and customer exclusion.

Mirrors the tkinter ``ui_filters.py`` surface: two scrollable checkbox
grids (line codes and customers) with Select All / Deselect All
buttons and a Continue button that emits the exclusion sets.

The tab is populated after a successful load — line codes come from
``session.all_line_codes`` and customers from ``session.suspended_items``.
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import theme as t
import theme_qt as tq


class FilterTab(QWidget):
    """Line code + customer exclusion filter surface.

    Signals:
        filters_applied(set, set)  — (excluded_line_codes, excluded_customers)
    """

    filters_applied = Signal(set, set)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lc_checks: dict[str, QCheckBox] = {}
        self._cust_checks: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        layout.setSpacing(t.SPACE_MD)

        # ── Header ────────────────────────────────────────────────
        header = QLabel()
        header.setTextFormat(Qt.RichText)
        header.setText(tq.tab_header_html(
            "Filter",
            "Exclude line codes and customers before assignment",
        ))
        header.setStyleSheet(tq.tab_header_style())
        layout.addWidget(header)

        # ── Line Codes section ────────────────────────────────────
        lc_card = QFrame()
        lc_card.setStyleSheet(tq.card_style(t.ACCENT_PRIMARY))
        lc_layout = QVBoxLayout(lc_card)
        lc_layout.setContentsMargins(t.SPACE_MD, t.SPACE_MD, t.SPACE_MD, t.SPACE_MD)
        lc_layout.setSpacing(t.SPACE_SM)

        lc_header_row = QHBoxLayout()
        lc_title = QLabel("Line Codes")
        lc_title.setStyleSheet(
            f"color: {t.TEXT_PRIMARY}; font-size: {t.FONT_LABEL}px; font-weight: bold;"
        )
        lc_header_row.addWidget(lc_title)
        lc_header_row.addStretch(1)
        btn_lc_all = QPushButton("Select All")
        btn_lc_all.setFixedHeight(26)
        btn_lc_all.clicked.connect(lambda: self._toggle_all_lc(True))
        lc_header_row.addWidget(btn_lc_all)
        btn_lc_none = QPushButton("Deselect All")
        btn_lc_none.setFixedHeight(26)
        btn_lc_none.clicked.connect(lambda: self._toggle_all_lc(False))
        lc_header_row.addWidget(btn_lc_none)
        lc_layout.addLayout(lc_header_row)

        lc_count_row = QHBoxLayout()
        self._lc_included_card = QLabel()
        self._lc_included_card.setTextFormat(Qt.RichText)
        self._lc_included_card.setAlignment(Qt.AlignCenter)
        self._lc_included_card.setFixedHeight(44)
        self._lc_included_card.setMinimumWidth(100)
        self._lc_included_card.setStyleSheet(tq.number_card_style(t.ACCENT_OK))
        lc_count_row.addWidget(self._lc_included_card)
        self._lc_excluded_card = QLabel()
        self._lc_excluded_card.setTextFormat(Qt.RichText)
        self._lc_excluded_card.setAlignment(Qt.AlignCenter)
        self._lc_excluded_card.setFixedHeight(44)
        self._lc_excluded_card.setMinimumWidth(100)
        self._lc_excluded_card.setStyleSheet(tq.number_card_style(t.ACCENT_WARNING))
        lc_count_row.addWidget(self._lc_excluded_card)
        lc_count_row.addStretch(1)
        lc_layout.addLayout(lc_count_row)

        lc_scroll = QScrollArea()
        lc_scroll.setWidgetResizable(True)
        lc_scroll.setFrameShape(QFrame.NoFrame)
        self._lc_grid_widget = QWidget()
        self._lc_grid = QGridLayout(self._lc_grid_widget)
        self._lc_grid.setSpacing(4)
        lc_scroll.setWidget(self._lc_grid_widget)
        lc_layout.addWidget(lc_scroll, stretch=1)

        layout.addWidget(lc_card, stretch=1)

        # ── Customers section ─────────────────────────────────────
        cust_card = QFrame()
        cust_card.setStyleSheet(tq.card_style(t.ACCENT_WARNING))
        cust_layout = QVBoxLayout(cust_card)
        cust_layout.setContentsMargins(t.SPACE_MD, t.SPACE_MD, t.SPACE_MD, t.SPACE_MD)
        cust_layout.setSpacing(t.SPACE_SM)

        cust_header_row = QHBoxLayout()
        cust_title = QLabel("Customers (from Suspended Items)")
        cust_title.setStyleSheet(
            f"color: {t.TEXT_PRIMARY}; font-size: {t.FONT_LABEL}px; font-weight: bold;"
        )
        cust_header_row.addWidget(cust_title)
        cust_header_row.addStretch(1)
        btn_cust_all = QPushButton("Select All")
        btn_cust_all.setFixedHeight(26)
        btn_cust_all.clicked.connect(lambda: self._toggle_all_cust(True))
        cust_header_row.addWidget(btn_cust_all)
        btn_cust_none = QPushButton("Deselect All")
        btn_cust_none.setFixedHeight(26)
        btn_cust_none.clicked.connect(lambda: self._toggle_all_cust(False))
        cust_header_row.addWidget(btn_cust_none)
        cust_layout.addLayout(cust_header_row)

        cust_count_row = QHBoxLayout()
        self._cust_included_card = QLabel()
        self._cust_included_card.setTextFormat(Qt.RichText)
        self._cust_included_card.setAlignment(Qt.AlignCenter)
        self._cust_included_card.setFixedHeight(44)
        self._cust_included_card.setMinimumWidth(100)
        self._cust_included_card.setStyleSheet(tq.number_card_style(t.ACCENT_OK))
        cust_count_row.addWidget(self._cust_included_card)
        self._cust_excluded_card = QLabel()
        self._cust_excluded_card.setTextFormat(Qt.RichText)
        self._cust_excluded_card.setAlignment(Qt.AlignCenter)
        self._cust_excluded_card.setFixedHeight(44)
        self._cust_excluded_card.setMinimumWidth(100)
        self._cust_excluded_card.setStyleSheet(tq.number_card_style(t.ACCENT_WARNING))
        cust_count_row.addWidget(self._cust_excluded_card)
        cust_count_row.addStretch(1)
        cust_layout.addLayout(cust_count_row)

        cust_scroll = QScrollArea()
        cust_scroll.setWidgetResizable(True)
        cust_scroll.setFrameShape(QFrame.NoFrame)
        self._cust_grid_widget = QWidget()
        self._cust_grid = QGridLayout(self._cust_grid_widget)
        self._cust_grid.setSpacing(4)
        cust_scroll.setWidget(self._cust_grid_widget)
        cust_layout.addWidget(cust_scroll, stretch=1)

        layout.addWidget(cust_card, stretch=1)

        # ── Footer ────────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.addStretch(1)
        self._apply_btn = QPushButton("Apply Filters & Continue \u2192")
        self._apply_btn.setFixedHeight(36)
        self._apply_btn.setMinimumWidth(220)
        self._apply_btn.setStyleSheet(
            f"QPushButton {{ background: {t.ACCENT_PRIMARY}; "
            f"  color: {t.TEXT_INVERSE}; border: none; "
            f"  border-radius: {t.RADIUS_SM}px; font-weight: bold; "
            f"  font-size: {t.FONT_MEDIUM}px; padding: 6px 18px; }}"
            f"QPushButton:hover {{ background: #6bb0ea; }}"
            f"QPushButton:disabled {{ background: {t.BG_INSET}; "
            f"  color: {t.TEXT_DIM}; }}"
        )
        self._apply_btn.clicked.connect(self._on_apply)
        self._apply_btn.setEnabled(False)
        footer.addWidget(self._apply_btn)
        layout.addLayout(footer)

    # ── Public API ────────────────────────────────────────────────

    def populate(self, line_codes: list[str], lc_counts: dict[str, int],
                 customers: list[tuple[str, str, int]]):
        """Fill the checkbox grids.

        Args:
            line_codes: sorted list of line code strings
            lc_counts: {line_code: item_count}
            customers: list of (code, name, suspended_count) tuples
        """
        self._populate_lc(line_codes, lc_counts)
        self._populate_cust(customers)
        self._apply_btn.setEnabled(bool(line_codes))

    def excluded_line_codes(self) -> set[str]:
        return {lc for lc, cb in self._lc_checks.items() if not cb.isChecked()}

    def excluded_customers(self) -> set[str]:
        return {code for code, cb in self._cust_checks.items() if not cb.isChecked()}

    # ── Internal ──────────────────────────────────────────────────

    def _populate_lc(self, line_codes: list[str], counts: dict[str, int]):
        # Clear old
        for cb in self._lc_checks.values():
            cb.deleteLater()
        self._lc_checks.clear()

        cols = max(4, len(line_codes) // 18 + 1)
        for i, lc in enumerate(line_codes):
            count = counts.get(lc, 0)
            cb = QCheckBox(f"{lc}  ({count})")
            cb.setChecked(True)
            cb.setStyleSheet(f"color: {t.TEXT_SECONDARY}; font-size: {t.FONT_BODY}px;")
            cb.stateChanged.connect(self._update_lc_count)
            self._lc_grid.addWidget(cb, i // cols, i % cols)
            self._lc_checks[lc] = cb
        self._update_lc_count()

    def _populate_cust(self, customers: list[tuple[str, str, int]]):
        for cb in self._cust_checks.values():
            cb.deleteLater()
        self._cust_checks.clear()

        cols = min(2, max(1, len(customers) // 14 + 1))
        for i, (code, name, count) in enumerate(customers):
            display = f"{code}  -  {name}  ({count})" if name else f"{code}  ({count})"
            cb = QCheckBox(display)
            cb.setChecked(True)
            cb.setStyleSheet(f"color: {t.TEXT_SECONDARY}; font-size: {t.FONT_BODY}px;")
            cb.stateChanged.connect(self._update_cust_count)
            self._cust_grid.addWidget(cb, i // cols, i % cols)
            self._cust_checks[code] = cb
        self._update_cust_count()

    def _toggle_all_lc(self, state: bool):
        for cb in self._lc_checks.values():
            cb.setChecked(state)

    def _toggle_all_cust(self, state: bool):
        for cb in self._cust_checks.values():
            cb.setChecked(state)

    def _update_lc_count(self, _=None):
        included = sum(1 for cb in self._lc_checks.values() if cb.isChecked())
        total = len(self._lc_checks)
        excluded = total - included
        self._lc_included_card.setText(tq.number_card_html(
            str(included), f"of {total}", "Included",
            t.ACCENT_OK, value_font_size=t.FONT_LABEL,
        ))
        self._lc_excluded_card.setText(tq.number_card_html(
            str(excluded), "excluded", "Excluded",
            t.ACCENT_WARNING if excluded > 0 else t.TEXT_DIM,
            value_font_size=t.FONT_LABEL,
        ))

    def _update_cust_count(self, _=None):
        included = sum(1 for cb in self._cust_checks.values() if cb.isChecked())
        total = len(self._cust_checks)
        excluded = total - included
        self._cust_included_card.setText(tq.number_card_html(
            str(included), f"of {total}", "Included",
            t.ACCENT_OK, value_font_size=t.FONT_LABEL,
        ))
        self._cust_excluded_card.setText(tq.number_card_html(
            str(excluded), "excluded", "Excluded",
            t.ACCENT_WARNING if excluded > 0 else t.TEXT_DIM,
            value_font_size=t.FONT_LABEL,
        ))

    def _on_apply(self):
        self.filters_applied.emit(
            self.excluded_line_codes(),
            self.excluded_customers(),
        )
