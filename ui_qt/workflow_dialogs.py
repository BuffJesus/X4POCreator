"""Qt workflow dialogs — Remove Not Needed, Stock Warnings, Vendor Review,
Session Diff, Supplier Map, QOH Review, Skip Cleanup.

All dialogs use theme.py tokens and theme_qt.py helpers for the Tuner
visual grammar.  Design rules: intuitive, non-intimidating, beautiful,
modern.  Lead with the action, not the data.  Number cards for summary
stats.  Generous spacing.  Clear primary action with accent color.
"""

from __future__ import annotations

import copy
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import theme as t
import theme_qt as tq


# ── Shared helpers ────────────────────────────────────────────────────────

def _primary_btn(text: str, parent=None) -> QPushButton:
    """Create an accent-colored primary action button."""
    btn = QPushButton(text, parent)
    btn.setStyleSheet(
        f"QPushButton {{ background: {t.ACCENT_PRIMARY}; color: {t.TEXT_INVERSE}; "
        f"border: none; border-radius: {t.RADIUS_SM}px; padding: 7px 18px; "
        f"font-weight: bold; }}"
        f"QPushButton:hover {{ background: {t.BORDER_ACCENT}; }}"
    )
    return btn


def _danger_btn(text: str, parent=None) -> QPushButton:
    """Create a danger-colored action button."""
    btn = QPushButton(text, parent)
    btn.setStyleSheet(
        f"QPushButton {{ background: {t.ACCENT_DANGER}; color: {t.TEXT_INVERSE}; "
        f"border: none; border-radius: {t.RADIUS_SM}px; padding: 7px 18px; "
        f"font-weight: bold; }}"
        f"QPushButton:hover {{ background: #c04040; }}"
    )
    return btn


def _ghost_btn(text: str, parent=None) -> QPushButton:
    """Create a subdued secondary button."""
    btn = QPushButton(text, parent)
    btn.setStyleSheet(
        f"QPushButton {{ background: transparent; color: {t.TEXT_MUTED}; "
        f"border: 1px solid {t.BORDER_SOFT}; border-radius: {t.RADIUS_SM}px; "
        f"padding: 6px 14px; }}"
        f"QPushButton:hover {{ color: {t.TEXT_PRIMARY}; border-color: {t.BORDER}; }}"
    )
    return btn


def _summary_card(value: str, units: str, title: str, accent: str) -> QLabel:
    """Build a number-card QLabel."""
    label = QLabel()
    label.setTextFormat(Qt.RichText)
    label.setAlignment(Qt.AlignCenter)
    label.setMinimumHeight(70)
    label.setStyleSheet(tq.number_card_style(accent))
    label.setText(tq.number_card_html(
        value, units, title, accent, value_font_size=t.FONT_HEADING,
    ))
    return label


def _header_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(
        f"color: {t.TEXT_PRIMARY}; font-size: {t.FONT_LABEL}px; font-weight: bold;"
    )
    return lbl


def _subheader_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: {t.FONT_SMALL}px;")
    return lbl


def _setup_table(table: QTableWidget, headers: list[str], stretches: list[int] | None = None):
    """Configure a QTableWidget with dark theme and standard settings."""
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setSelectionMode(QAbstractItemView.ExtendedSelection)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setFocusPolicy(Qt.StrongFocus)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setStyleSheet(
        f"QTableWidget {{ background: {t.BG_PANEL}; border: 1px solid {t.BORDER}; "
        f"border-radius: {t.RADIUS_MD}px; gridline-color: {t.BORDER_SOFT}; }}"
        f"QHeaderView::section {{ background: {t.BG_ELEVATED}; color: {t.TEXT_MUTED}; "
        f"border: none; border-bottom: 1px solid {t.BORDER}; "
        f"padding: {t.SPACE_SM}px; font-size: {t.FONT_SMALL}px; font-weight: bold; }}"
    )
    if stretches:
        h = table.horizontalHeader()
        for idx, stretch in enumerate(stretches):
            if stretch:
                h.setSectionResizeMode(idx, QHeaderView.Stretch)


def _dialog_base_style() -> str:
    return f"background-color: {t.BG_BASE}; color: {t.TEXT_SECONDARY};"


# ═════════════════════════════════════════════════════════════════════════
# 1. Remove Not Needed dialog
# ═════════════════════════════════════════════════════════════════════════

class RemoveNotNeededDialog(QDialog):
    """Interactive review of items flagged as not needing ordering.

    Uses QTableWidgetItem check states instead of QCheckBox widgets —
    no per-row widget allocation, so 55K rows build in <1s instead of 90s.
    """

    def __init__(
        self,
        candidates: list[dict],
        *,
        excluded_assigned_count: int = 0,
        scope_label: str = "filtered",
        parent=None,
    ):
        super().__init__(parent)
        self._candidates = candidates
        self._removed_indices: list[int] = []
        self.setWindowTitle("Remove Not Needed Items")
        self.resize(820, 580)
        self.setStyleSheet(_dialog_base_style())

        auto_count = sum(1 for c in candidates if c.get("auto_remove"))
        manual_count = len(candidates) - auto_count

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        root.setSpacing(t.SPACE_MD)

        # Header
        root.addWidget(_header_label(
            f"{len(candidates):,} {scope_label} item(s) flagged as likely not needed"
        ))
        sub = "Click the \u2611 column to toggle. Checked items will be removed."
        if excluded_assigned_count > 0:
            sub += (
                f"  ({excluded_assigned_count} additional item(s) already have a "
                "vendor and were skipped.)"
            )
        root.addWidget(_subheader_label(sub))

        # Summary cards
        cards = QWidget()
        cards_layout = QGridLayout(cards)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setHorizontalSpacing(t.SPACE_SM)
        cards_layout.addWidget(
            _summary_card(f"{len(candidates):,}", "items", "Flagged", t.ACCENT_WARNING), 0, 0,
        )
        cards_layout.addWidget(
            _summary_card(f"{auto_count:,}", "auto", "Auto-remove", t.ACCENT_DANGER), 0, 1,
        )
        cards_layout.addWidget(
            _summary_card(f"{manual_count:,}", "review", "Needs Review", t.ACCENT_PRIMARY), 0, 2,
        )
        root.addWidget(cards)

        # Table — uses item check states, not widget checkboxes
        self._table = QTableWidget()
        _setup_table(self._table, [
            "\u2611", "Item", "Description", "Qty", "Reason",
        ], stretches=[0, 0, 0, 0, 1])
        self._table.setColumnWidth(0, 36)
        self._table.setColumnWidth(1, 120)
        self._table.setColumnWidth(2, 220)
        self._table.setColumnWidth(3, 60)
        self._populate_table()
        root.addWidget(self._table, stretch=1)

        # Footer
        footer = QHBoxLayout()
        footer.setSpacing(t.SPACE_SM)

        self._lbl_count = QLabel()
        self._lbl_count.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: {t.FONT_SMALL}px;")
        footer.addWidget(self._lbl_count)
        footer.addStretch(1)

        btn_all = _ghost_btn("Select All")
        btn_all.clicked.connect(lambda: self._set_all(True))
        footer.addWidget(btn_all)

        btn_none = _ghost_btn("Deselect All")
        btn_none.clicked.connect(lambda: self._set_all(False))
        footer.addWidget(btn_none)

        cancel_btn = _ghost_btn("Cancel")
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)

        confirm_btn = _danger_btn("Remove Checked")
        confirm_btn.clicked.connect(self._on_confirm)
        footer.addWidget(confirm_btn)

        root.addLayout(footer)
        self._update_count()

        # Update count when any cell changes (check toggle)
        self._table.itemChanged.connect(lambda item: self._update_count()
                                         if item.column() == 0 else None)

    @property
    def removed_indices(self) -> list[int]:
        """Original candidate indices of items the user chose to remove."""
        return list(self._removed_indices)

    def _populate_table(self):
        cands = self._candidates
        self._table.blockSignals(True)
        self._table.setRowCount(len(cands))
        for row, c in enumerate(cands):
            # Checkbox column — uses item check state, zero widget overhead
            check_item = QTableWidgetItem()
            check_item.setFlags(
                Qt.ItemIsUserCheckable | Qt.ItemIsEnabled
            )
            check_item.setCheckState(
                Qt.Checked if c.get("auto_remove") else Qt.Unchecked
            )
            self._table.setItem(row, 0, check_item)

            item_id = f"{c.get('line_code', '')} {c.get('item_code', '')}".strip()
            values = [
                item_id,
                str(c.get("description", ""))[:80],
                str(c.get("final_qty", 0)),
                c.get("reason", ""),
            ]
            for col, val in enumerate(values, 1):
                cell = QTableWidgetItem(str(val) if val not in (None, "") else "\u2014")
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                if col == 4:  # reason
                    cell.setForeground(Qt.GlobalColor.yellow)
                self._table.setItem(row, col, cell)
        self._table.blockSignals(False)

    def _update_count(self):
        n = sum(
            1 for row in range(self._table.rowCount())
            if self._table.item(row, 0)
            and self._table.item(row, 0).checkState() == Qt.Checked
        )
        self._lbl_count.setText(f"{n:,} of {len(self._candidates):,} selected for removal")

    def _set_all(self, state: bool):
        check = Qt.Checked if state else Qt.Unchecked
        self._table.blockSignals(True)
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item:
                item.setCheckState(check)
        self._table.blockSignals(False)
        self._update_count()

    def _on_confirm(self):
        self._removed_indices = [
            row for row in range(self._table.rowCount())
            if self._table.item(row, 0)
            and self._table.item(row, 0).checkState() == Qt.Checked
        ]
        self.accept()


# ═════════════════════════════════════════════════════════════════════════
# 2. Stock Warnings / Review Flagged Items dialog
# ═════════════════════════════════════════════════════════════════════════

class StockWarningsDialog(QDialog):
    """Review items that may not need ordering before export.

    Items start checked (keep).  Uncheck to remove from PO.
    """

    def __init__(self, flagged: list[dict], *, parent=None):
        super().__init__(parent)
        self._flagged = flagged
        self._proceed = False
        self._keep_flags: list[bool] = [True] * len(flagged)
        self.setWindowTitle("Review Flagged Items")
        self.resize(780, 540)
        self.setStyleSheet(_dialog_base_style())

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        root.setSpacing(t.SPACE_MD)

        root.addWidget(_header_label(
            f"{len(flagged)} item(s) may not need ordering"
        ))
        root.addWidget(_subheader_label(
            "Uncheck items you want to remove. Checked items stay on the PO."
        ))

        # Summary cards
        cards = QWidget()
        cards_layout = QGridLayout(cards)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setHorizontalSpacing(t.SPACE_SM)
        cards_layout.addWidget(
            _summary_card(str(len(flagged)), "items", "Flagged for Review", t.ACCENT_WARNING), 0, 0,
        )
        root.addWidget(cards)

        # Table — clean: keep checkbox, identity, qty, reason
        self._table = QTableWidget()
        _setup_table(self._table, [
            "Keep", "Item", "Description", "Qty", "Reason",
        ], stretches=[0, 0, 0, 0, 1])
        self._table.setColumnWidth(0, 40)
        self._table.setColumnWidth(1, 120)
        self._table.setColumnWidth(2, 220)
        self._table.setColumnWidth(3, 60)
        self._checks: list[QCheckBox] = []
        self._populate()
        root.addWidget(self._table, stretch=1)

        # Footer
        footer = QHBoxLayout()
        footer.setSpacing(t.SPACE_SM)
        footer.addStretch(1)

        back_btn = _ghost_btn("\u2190 Go Back")
        back_btn.clicked.connect(self.reject)
        footer.addWidget(back_btn)

        confirm_btn = _primary_btn(f"Confirm ({len(flagged)} flagged)")
        confirm_btn.clicked.connect(self._on_confirm)
        footer.addWidget(confirm_btn)

        root.addLayout(footer)

    @property
    def proceed(self) -> bool:
        return self._proceed

    @property
    def items_to_unassign(self) -> list[dict]:
        """Items the user unchecked (should have vendor cleared)."""
        return [
            self._flagged[i] for i, kept in enumerate(self._keep_flags) if not kept
        ]

    def _populate(self):
        flagged = self._flagged
        self._table.setRowCount(len(flagged))
        for row, f in enumerate(flagged):
            cb = QCheckBox()
            cb.setChecked(True)
            idx = row
            cb.stateChanged.connect(lambda state, i=idx: self._on_check(i, state))
            self._checks.append(cb)

            cb_widget = QWidget()
            cb_layout = QHBoxLayout(cb_widget)
            cb_layout.setAlignment(Qt.AlignCenter)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            cb_layout.addWidget(cb)
            self._table.setCellWidget(row, 0, cb_widget)

            item = f.get("item", f)
            item_id = f"{item.get('line_code', '')} {item.get('item_code', '')}".strip()
            reasons = f.get("reasons", [])
            reason_str = ("; ".join(reasons) if isinstance(reasons, list)
                          else str(reasons or ""))
            values = [
                item_id,
                str(item.get("description", ""))[:80],
                str(item.get("order_qty", item.get("final_qty", 0))),
                reason_str,
            ]
            for col, val in enumerate(values, 1):
                cell = QTableWidgetItem(str(val) if val not in (None, "") else "\u2014")
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                if col == 4:  # reason
                    cell.setForeground(Qt.GlobalColor.yellow)
                self._table.setItem(row, col, cell)

    def _on_check(self, index: int, state: int):
        self._keep_flags[index] = (state == Qt.Checked.value)

    def _on_confirm(self):
        self._proceed = True
        self.accept()


class TooManyFlaggedDialog(QDialog):
    """Summary confirm when too many items are flagged (>50)."""

    def __init__(self, count: int, *, parent=None):
        super().__init__(parent)
        self._proceed = False
        self.setWindowTitle("Many Items Flagged")
        self.setFixedSize(560, 260)
        self.setStyleSheet(_dialog_base_style())

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_XL, t.SPACE_XL, t.SPACE_XL, t.SPACE_XL)
        root.setSpacing(t.SPACE_MD)

        # Number card
        card = _summary_card(str(count), "items", "May Not Need Ordering", t.ACCENT_WARNING)
        root.addWidget(card)

        body = QLabel(
            "Too many to review individually. Use Remove Not Needed from the "
            "bulk tab first to narrow the list, or proceed to export as-is."
        )
        body.setWordWrap(True)
        body.setStyleSheet(f"color: {t.TEXT_SECONDARY}; font-size: {t.FONT_BODY}px;")
        root.addWidget(body)

        root.addStretch(1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        back_btn = _ghost_btn("\u2190 Go Back")
        back_btn.clicked.connect(self.reject)
        footer.addWidget(back_btn)
        proceed_btn = _primary_btn("Proceed Anyway")
        proceed_btn.clicked.connect(self._on_proceed)
        footer.addWidget(proceed_btn)
        root.addLayout(footer)

    @property
    def proceed(self) -> bool:
        return self._proceed

    def _on_proceed(self):
        self._proceed = True
        self.accept()


# ═════════════════════════════════════════════════════════════════════════
# 3. Vendor Review dialog
# ═════════════════════════════════════════════════════════════════════════

class VendorReviewDialog(QDialog):
    """Per-vendor activity summary from session snapshots."""

    def __init__(self, summaries: list[dict], *, focus_vendor: str | None = None, parent=None):
        super().__init__(parent)
        self._summaries = summaries
        self.setWindowTitle("Vendor Review")
        self.resize(900, 620)
        self.setStyleSheet(_dialog_base_style())

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        root.setSpacing(t.SPACE_MD)

        # Header
        root.addWidget(_header_label(f"{len(summaries)} vendor(s) \u2014 most-active first"))
        root.addWidget(_subheader_label(
            "Lead times inferred from snapshot pairs. "
            "Click a vendor to see top items."
        ))

        if not summaries:
            empty = QLabel(
                "No vendor activity found in sessions/. Run an export first."
            )
            empty.setStyleSheet(f"color: {t.TEXT_DIM}; font-size: {t.FONT_BODY}px;")
            empty.setAlignment(Qt.AlignCenter)
            root.addWidget(empty, stretch=1)
            close_btn = _primary_btn("Close")
            close_btn.clicked.connect(self.accept)
            footer = QHBoxLayout()
            footer.addStretch(1)
            footer.addWidget(close_btn)
            root.addLayout(footer)
            return

        # Splitter: vendor table top, item table bottom
        splitter = QSplitter(Qt.Vertical)

        # Top: vendor table
        self._vendor_table = QTableWidget()
        _setup_table(self._vendor_table, [
            "Vendor", "Orders", "Qty Ordered", "Qty Received", "Last Session", "Lead Time",
        ], stretches=[1, 0, 0, 0, 0, 0])
        self._vendor_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._vendor_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._populate_vendors()
        self._vendor_table.itemSelectionChanged.connect(self._on_vendor_selected)
        splitter.addWidget(self._vendor_table)

        # Bottom: top items panel
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, t.SPACE_SM, 0, 0)
        bottom_layout.setSpacing(t.SPACE_XS)
        bottom_layout.addWidget(_subheader_label("Top items for selected vendor:"))

        self._item_table = QTableWidget()
        _setup_table(self._item_table, [
            "LC", "Item Code", "Description", "Qty",
        ], stretches=[0, 0, 1, 0])
        self._item_table.setSelectionMode(QAbstractItemView.NoSelection)
        bottom_layout.addWidget(self._item_table)
        splitter.addWidget(bottom)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, stretch=1)

        # Select initial vendor
        focus_row = 0
        if focus_vendor:
            target = focus_vendor.strip().upper()
            for i, s in enumerate(summaries):
                if str(s.get("vendor_code", "")).strip().upper() == target:
                    focus_row = i
                    break
        if summaries:
            self._vendor_table.selectRow(focus_row)

        # Footer
        footer = QHBoxLayout()
        footer.addStretch(1)
        close_btn = _primary_btn("Close")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        root.addLayout(footer)

    def _format_lead(self, days) -> str:
        if days is None:
            return "\u2014"
        try:
            import vendor_summary_flow
            label = vendor_summary_flow.format_lead_time_label(days)
            return label or "\u2014"
        except Exception:
            return str(days)

    def _populate_vendors(self):
        self._vendor_table.setRowCount(len(self._summaries))
        for row, s in enumerate(self._summaries):
            values = [
                s.get("vendor_code", ""),
                str(s.get("order_count", 0)),
                str(s.get("total_qty_ordered", 0)),
                str(s.get("total_qty_received", 0)),
                str(s.get("last_session_date", "")).split("T", 1)[0],
                self._format_lead(s.get("inferred_lead_days")),
            ]
            for col, val in enumerate(values):
                cell = QTableWidgetItem(str(val))
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                if col == 0:
                    cell.setForeground(Qt.GlobalColor.white)
                elif col in (1, 2, 3):
                    cell.setTextAlignment(Qt.AlignCenter)
                self._vendor_table.setItem(row, col, cell)

    def _on_vendor_selected(self):
        self._item_table.setRowCount(0)
        rows = self._vendor_table.selectionModel().selectedRows()
        if not rows:
            return
        idx = rows[0].row()
        if idx < 0 or idx >= len(self._summaries):
            return
        top_items = self._summaries[idx].get("top_items", []) or []
        self._item_table.setRowCount(len(top_items))
        for row, item in enumerate(top_items):
            values = [
                item.get("line_code", ""),
                item.get("item_code", ""),
                item.get("description", ""),
                str(item.get("qty", 0)),
            ]
            for col, val in enumerate(values):
                cell = QTableWidgetItem(str(val))
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                if col == 3:
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._item_table.setItem(row, col, cell)


# ═════════════════════════════════════════════════════════════════════════
# 4. Session Diff dialog
# ═════════════════════════════════════════════════════════════════════════

_DIFF_TABS = (
    ("new_items",      "New",            ("LC", "Item Code", "Description", "Qty", "Vendor")),
    ("removed_items",  "Removed",        ("LC", "Item Code", "Description", "Qty", "Vendor")),
    ("qty_increased",  "Qty Up",         ("LC", "Item Code", "Description", "Old Qty", "New Qty", "Delta")),
    ("qty_decreased",  "Qty Down",       ("LC", "Item Code", "Description", "Old Qty", "New Qty", "Delta")),
    ("vendor_changed", "Vendor Changed", ("LC", "Item Code", "Description", "Old Vendor", "New Vendor")),
)

_DIFF_KEYS = {
    "LC": "line_code", "Item Code": "item_code", "Description": "description",
    "Qty": "qty", "Vendor": "vendor",
    "Old Qty": "old_qty", "New Qty": "new_qty", "Delta": "delta",
    "Old Vendor": "old_vendor", "New Vendor": "new_vendor",
}


class SessionDiffDialog(QDialog):
    """What changed since the most recent snapshot."""

    def __init__(self, diff: dict, *, summary_text: str = "", snapshot_label: str = "", parent=None):
        super().__init__(parent)
        self._diff = diff
        self.setWindowTitle("Session Diff")
        self.resize(950, 580)
        self.setStyleSheet(_dialog_base_style())

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        root.setSpacing(t.SPACE_MD)

        root.addWidget(_header_label(summary_text or "Session comparison"))
        if snapshot_label:
            root.addWidget(_subheader_label(f"Compared against snapshot from {snapshot_label}."))

        # Summary cards
        cards = QWidget()
        cards_layout = QGridLayout(cards)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setHorizontalSpacing(t.SPACE_SM)

        new_count = len(diff.get("new_items", []))
        removed_count = len(diff.get("removed_items", []))
        qty_up = len(diff.get("qty_increased", []))
        qty_down = len(diff.get("qty_decreased", []))
        vendor_changed = len(diff.get("vendor_changed", []))

        card_defs = [
            (str(new_count), "", "New Items", t.ACCENT_OK),
            (str(removed_count), "", "Removed", t.ACCENT_DANGER),
            (str(qty_up), "\u2191", "Qty Up", t.ACCENT_WARNING),
            (str(qty_down), "\u2193", "Qty Down", t.ACCENT_PRIMARY),
            (str(vendor_changed), "", "Vendor Changed", t.ACCENT_SPECIAL),
        ]
        for col, (val, units, title, accent) in enumerate(card_defs):
            cards_layout.addWidget(_summary_card(val, units, title, accent), 0, col)
        root.addWidget(cards)

        if not diff or all(not diff.get(k) for k, _, _ in _DIFF_TABS):
            empty = QLabel("No changes since the last session.")
            empty.setStyleSheet(f"color: {t.TEXT_DIM}; font-size: {t.FONT_BODY}px;")
            empty.setAlignment(Qt.AlignCenter)
            root.addWidget(empty, stretch=1)
        else:
            # Tabbed view
            tabs = QTabWidget()
            tabs.setStyleSheet(
                f"QTabWidget::pane {{ border: 1px solid {t.BORDER}; background: {t.BG_PANEL}; }}"
                f"QTabBar::tab {{ background: {t.BG_ELEVATED}; color: {t.TEXT_MUTED}; "
                f"padding: 6px 14px; border: 1px solid {t.BORDER}; "
                f"border-bottom: none; border-top-left-radius: {t.RADIUS_SM}px; "
                f"border-top-right-radius: {t.RADIUS_SM}px; }}"
                f"QTabBar::tab:selected {{ background: {t.BG_PANEL}; color: {t.TEXT_PRIMARY}; }}"
                f"QTabBar::tab:hover {{ color: {t.TEXT_PRIMARY}; }}"
            )
            for bucket_key, label, headers in _DIFF_TABS:
                rows = diff.get(bucket_key, []) or []
                tab_page = QWidget()
                tab_layout = QVBoxLayout(tab_page)
                tab_layout.setContentsMargins(t.SPACE_SM, t.SPACE_SM, t.SPACE_SM, t.SPACE_SM)

                table = QTableWidget()
                _setup_table(table, list(headers), stretches=[0, 0, 1] + [0] * (len(headers) - 3))
                table.setSelectionMode(QAbstractItemView.NoSelection)
                table.setRowCount(len(rows))
                for r, row in enumerate(rows):
                    for c, hdr in enumerate(headers):
                        key = _DIFF_KEYS.get(hdr, hdr.lower())
                        if key == "line_code":
                            val = row.get("line_code", "")
                        elif key == "delta":
                            d = row.get("delta", 0)
                            val = ("+" if d > 0 else "") + str(d)
                        else:
                            val = row.get(key, "")
                        cell = QTableWidgetItem(str(val) if val not in (None, "") else "\u2014")
                        cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                        table.setItem(r, c, cell)

                if not rows:
                    empty_lbl = QLabel(f"No {label.lower()} items.")
                    empty_lbl.setStyleSheet(f"color: {t.TEXT_DIM};")
                    tab_layout.addWidget(empty_lbl)
                tab_layout.addWidget(table, stretch=1)
                tabs.addTab(tab_page, f"{label} ({len(rows)})")
            root.addWidget(tabs, stretch=1)

        # Footer
        footer = QHBoxLayout()
        footer.addStretch(1)
        close_btn = _primary_btn("Close")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        root.addLayout(footer)


# ═════════════════════════════════════════════════════════════════════════
# 5. Supplier Map dialog
# ═════════════════════════════════════════════════════════════════════════

class SupplierMapDialog(QDialog):
    """Edit and apply supplier → vendor auto-mapping."""

    def __init__(self, mapping: dict[str, str], *, parent=None):
        super().__init__(parent)
        self._working = dict(mapping)
        self._applied_pairs: list[tuple] = []
        self._saved = False
        self.setWindowTitle("Supplier Map")
        self.resize(700, 520)
        self.setStyleSheet(_dialog_base_style())

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        root.setSpacing(t.SPACE_MD)

        root.addWidget(_header_label("Supplier \u2192 Vendor Mapping"))
        root.addWidget(_subheader_label(
            "Map X4 supplier codes to vendor codes for auto-assignment. "
            "Manual vendor assignments are never overwritten."
        ))

        # Table
        self._table = QTableWidget()
        _setup_table(self._table, ["Supplier Code", "Mapped Vendor"], stretches=[1, 1])
        root.addWidget(self._table, stretch=1)

        # Add/edit row
        edit_card = QFrame()
        edit_card.setStyleSheet(tq.card_style())
        edit_layout = QHBoxLayout(edit_card)
        edit_layout.setContentsMargins(t.SPACE_SM, t.SPACE_SM, t.SPACE_SM, t.SPACE_SM)
        edit_layout.setSpacing(t.SPACE_SM)

        edit_layout.addWidget(QLabel("Supplier:"))
        self._supplier_edit = QLineEdit()
        self._supplier_edit.setFixedWidth(140)
        self._supplier_edit.setPlaceholderText("e.g. ACME")
        edit_layout.addWidget(self._supplier_edit)

        edit_layout.addWidget(QLabel("Vendor:"))
        self._vendor_edit = QLineEdit()
        self._vendor_edit.setFixedWidth(140)
        self._vendor_edit.setPlaceholderText("e.g. ACM")
        edit_layout.addWidget(self._vendor_edit)

        btn_add = _ghost_btn("Add / Update")
        btn_add.clicked.connect(self._add_or_update)
        edit_layout.addWidget(btn_add)

        btn_remove = _ghost_btn("Remove Selected")
        btn_remove.clicked.connect(self._remove_selected)
        edit_layout.addWidget(btn_remove)

        edit_layout.addStretch(1)
        root.addWidget(edit_card)

        # Status + actions
        status_row = QHBoxLayout()
        self._lbl_count = QLabel()
        self._lbl_count.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: {t.FONT_SMALL}px;")
        status_row.addWidget(self._lbl_count)

        btn_learn = _ghost_btn("Auto-learn from History")
        btn_learn.clicked.connect(self._on_learn)
        status_row.addWidget(btn_learn)
        status_row.addStretch(1)
        root.addLayout(status_row)

        # Footer
        footer = QHBoxLayout()
        footer.setSpacing(t.SPACE_SM)
        cancel_btn = _ghost_btn("Cancel")
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)

        self._apply_btn = _ghost_btn("Apply to Session")
        self._apply_btn.clicked.connect(self._on_apply_signal)
        footer.addWidget(self._apply_btn)

        footer.addStretch(1)
        save_btn = _primary_btn("Save")
        save_btn.clicked.connect(self._on_save)
        footer.addWidget(save_btn)
        root.addLayout(footer)

        self._refresh()

    # ── Signals for the shell to connect ──
    apply_requested = Signal(dict)  # emits working mapping
    learn_requested = Signal()
    save_requested = Signal(dict)   # emits working mapping

    @property
    def working_mapping(self) -> dict[str, str]:
        return dict(self._working)

    @property
    def saved(self) -> bool:
        return self._saved

    def set_mapping(self, mapping: dict[str, str]):
        """Update the working mapping (e.g. after auto-learn)."""
        self._working = dict(mapping)
        self._refresh()

    def _refresh(self):
        self._table.setRowCount(0)
        self._table.setRowCount(len(self._working))
        for row, (supplier, vendor) in enumerate(sorted(self._working.items())):
            for col, val in enumerate([supplier, vendor]):
                cell = QTableWidgetItem(val)
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                self._table.setItem(row, col, cell)
        self._lbl_count.setText(f"{len(self._working)} mapping(s)")

    def _add_or_update(self):
        supplier = self._supplier_edit.text().strip().upper()
        vendor = self._vendor_edit.text().strip().upper()
        if not supplier or not vendor:
            QMessageBox.information(self, "Missing Code", "Both supplier and vendor are required.")
            return
        self._working[supplier] = vendor
        self._supplier_edit.clear()
        self._vendor_edit.clear()
        self._refresh()

    def _remove_selected(self):
        rows = {idx.row() for idx in self._table.selectionModel().selectedRows()}
        keys = sorted(self._working.keys())
        for row in sorted(rows, reverse=True):
            if 0 <= row < len(keys):
                self._working.pop(keys[row], None)
        self._refresh()

    def _on_learn(self):
        self.learn_requested.emit()

    def _on_apply_signal(self):
        self.apply_requested.emit(self._working)

    def _on_save(self):
        self._saved = True
        self.save_requested.emit(self._working)
        self.accept()


# ═════════════════════════════════════════════════════════════════════════
# 6. QOH Review dialog
# ═════════════════════════════════════════════════════════════════════════

class QohReviewDialog(QDialog):
    """Review and optionally revert QOH edits made this session."""

    def __init__(self, rows: list[dict], *, parent=None):
        super().__init__(parent)
        self._rows = list(rows)
        self._reverted_keys: list[tuple[str, str]] = []
        self.setWindowTitle("QOH Adjustments")
        self.resize(860, 520)
        self.setStyleSheet(_dialog_base_style())

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        root.setSpacing(t.SPACE_MD)

        root.addWidget(_header_label("QOH edits this session"))
        root.addWidget(_subheader_label(
            "Select rows and click Revert to restore original on-hand values."
        ))

        # Summary card
        cards = QWidget()
        cards_layout = QGridLayout(cards)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.addWidget(
            _summary_card(str(len(rows)), "edits", "This Session", t.ACCENT_SPECIAL), 0, 0,
        )
        root.addWidget(cards)

        # Table
        self._table = QTableWidget()
        _setup_table(self._table, [
            "LC", "Item Code", "Description", "Old QOH", "New QOH", "Delta",
        ], stretches=[0, 0, 1, 0, 0, 0])
        self._populate()
        root.addWidget(self._table, stretch=1)

        # Footer
        footer = QHBoxLayout()
        footer.setSpacing(t.SPACE_SM)

        self._lbl_count = QLabel(
            f"{len(rows)} adjustment(s)" if rows else "No adjustments"
        )
        self._lbl_count.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: {t.FONT_SMALL}px;")
        footer.addWidget(self._lbl_count)

        btn_revert = _danger_btn("Revert Selected")
        btn_revert.clicked.connect(self._on_revert)
        footer.addWidget(btn_revert)

        footer.addStretch(1)
        close_btn = _primary_btn("Close")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        root.addLayout(footer)

    @property
    def reverted_keys(self) -> list[tuple[str, str]]:
        return list(self._reverted_keys)

    def _populate(self):
        self._table.setRowCount(len(self._rows))
        for row, r in enumerate(self._rows):
            delta = r.get("delta", 0)
            delta_str = ("+" if delta > 0 else "") + self._fmt(delta)
            values = [
                r.get("line_code", ""),
                r.get("item_code", ""),
                r.get("description", ""),
                self._fmt(r.get("old_qoh", 0)),
                self._fmt(r.get("new_qoh", 0)),
                delta_str,
            ]
            for col, val in enumerate(values):
                cell = QTableWidgetItem(str(val))
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                if col == 5:  # delta
                    if delta > 0:
                        cell.setForeground(Qt.GlobalColor.green)
                    elif delta < 0:
                        cell.setForeground(Qt.GlobalColor.red)
                self._table.setItem(row, col, cell)

    @staticmethod
    def _fmt(value) -> str:
        try:
            if float(value) == int(float(value)):
                return str(int(float(value)))
            return f"{value:g}"
        except (TypeError, ValueError):
            return str(value)

    def _on_revert(self):
        selected = {idx.row() for idx in self._table.selectionModel().selectedRows()}
        if not selected:
            QMessageBox.information(self, "No Selection", "Select at least one row to revert.")
            return
        keys = []
        for row in selected:
            if 0 <= row < len(self._rows):
                r = self._rows[row]
                keys.append((r.get("line_code", ""), r.get("item_code", "")))
        if not keys:
            return
        confirm = QMessageBox.question(
            self, "Confirm Revert",
            f"Revert {len(keys)} QOH edit(s) to their original value?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self._reverted_keys = keys
        self.accept()


# ═════════════════════════════════════════════════════════════════════════
# 7. Skip Cleanup Tools dialog
# ═════════════════════════════════════════════════════════════════════════

class SkipActionsDialog(QDialog):
    """Bulk tooling for items that don't need ordering (skip status)."""

    def __init__(self, skip_items: list[dict], clusters: list[dict], *, parent=None):
        super().__init__(parent)
        self._skip_items = skip_items
        self._clusters = clusters
        self._action_result: dict = {}
        self.setWindowTitle("Skip Cleanup Tools")
        self.resize(740, 560)
        self.setStyleSheet(_dialog_base_style())

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        root.setSpacing(t.SPACE_MD)

        count = len(skip_items)
        root.addWidget(_header_label(
            f"{count} skip item(s) across {len(clusters)} line code(s)"
            if count else "No skip items in the current session"
        ))
        root.addWidget(_subheader_label(
            "Select line codes to scope actions, or leave empty to apply to all. "
            "All actions can be undone."
        ))

        if not skip_items:
            root.addStretch(1)
            close_btn = _primary_btn("Close")
            close_btn.clicked.connect(self.accept)
            f = QHBoxLayout()
            f.addStretch(1)
            f.addWidget(close_btn)
            root.addLayout(f)
            return

        # Summary cards
        cards = QWidget()
        cards_layout = QGridLayout(cards)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setHorizontalSpacing(t.SPACE_SM)
        cards_layout.addWidget(
            _summary_card(str(count), "items", "Skip Items", t.ACCENT_WARNING), 0, 0,
        )
        cards_layout.addWidget(
            _summary_card(str(len(clusters)), "codes", "Line Codes", t.ACCENT_PRIMARY), 0, 1,
        )
        root.addWidget(cards)

        # Cluster table
        self._table = QTableWidget()
        _setup_table(self._table, ["Line Code", "Skip Items"], stretches=[1, 0])
        self._table.setRowCount(len(clusters))
        for row, cluster in enumerate(clusters):
            lc = cluster.get("line_code", "") or "(blank)"
            cell_lc = QTableWidgetItem(lc)
            cell_lc.setFlags(cell_lc.flags() & ~Qt.ItemIsEditable)
            cell_lc.setData(Qt.UserRole, cluster.get("line_code", ""))
            self._table.setItem(row, 0, cell_lc)

            cell_count = QTableWidgetItem(str(cluster.get("count", 0)))
            cell_count.setFlags(cell_count.flags() & ~Qt.ItemIsEditable)
            cell_count.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(row, 1, cell_count)
        root.addWidget(self._table, stretch=1)

        # Action footer
        footer = QHBoxLayout()
        footer.setSpacing(t.SPACE_SM)

        close_btn = _ghost_btn("Close")
        close_btn.clicked.connect(self.reject)
        footer.addWidget(close_btn)

        footer.addStretch(1)

        btn_csv = _ghost_btn("Export CSV")
        btn_csv.clicked.connect(lambda: self._do_action("export_csv"))
        footer.addWidget(btn_csv)

        btn_disc = _ghost_btn("Flag Discontinue")
        btn_disc.clicked.connect(lambda: self._do_action("flag_discontinue"))
        footer.addWidget(btn_disc)

        btn_ignore = _primary_btn("Add to Ignore List")
        btn_ignore.clicked.connect(lambda: self._do_action("ignore"))
        footer.addWidget(btn_ignore)

        root.addLayout(footer)

    # ── Signals for the shell to connect ──
    action_requested = Signal(str, list)  # action_name, scoped items

    @property
    def action_result(self) -> dict:
        return dict(self._action_result)

    def _scoped_items(self) -> list[dict]:
        selected_rows = {idx.row() for idx in self._table.selectionModel().selectedRows()}
        if not selected_rows:
            return list(self._skip_items)
        selected_codes = set()
        for row in selected_rows:
            item = self._table.item(row, 0)
            if item:
                selected_codes.add(item.data(Qt.UserRole))
        return [
            it for it in self._skip_items
            if str(it.get("line_code", "") or "") in selected_codes
        ]

    def _do_action(self, action: str):
        scope = self._scoped_items()
        if not scope:
            QMessageBox.information(self, "Nothing to Apply", "No skip items in the selected scope.")
            return
        self._action_result = {"action": action, "items": scope}
        self.action_requested.emit(action, scope)


# ═════════════════════════════════════════════════════════════════════════
# 8. Bulk Rule Edit dialog
# ═════════════════════════════════════════════════════════════════════════

_POLICY_OPTIONS = [
    "",
    "standard",
    "pack_trigger",
    "soft_pack",
    "exact_qty",
    "reel_review",
    "reel_auto",
    "large_pack_review",
    "manual_only",
]


class BulkRuleEditDialog(QDialog):
    """Apply a partial buy-rule change to multiple items at once."""

    def __init__(self, key_count: int, *, parent=None):
        super().__init__(parent)
        self._changes: dict | None = None
        self.setWindowTitle(f"Edit Rule \u2014 {key_count} item{'s' if key_count != 1 else ''}")
        self.setMinimumWidth(460)
        self.setStyleSheet(_dialog_base_style())

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        root.setSpacing(t.SPACE_MD)

        root.addWidget(_header_label("Edit Buy Rule \u2014 Multiple Items"))
        root.addWidget(_subheader_label(
            f"Applies to {key_count} selected item{'s' if key_count != 1 else ''}. "
            "Leave a field blank to keep each item\u2019s existing value."
        ))

        # Form card
        form_card = QFrame()
        form_card.setStyleSheet(tq.card_style())
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(t.SPACE_MD, t.SPACE_MD, t.SPACE_MD, t.SPACE_MD)
        form_layout.setSpacing(t.SPACE_SM)

        # Order Policy
        row = QHBoxLayout()
        row.addWidget(QLabel("Order Policy:"))
        self._policy_combo = QComboBox()
        self._policy_combo.addItems(_POLICY_OPTIONS)
        self._policy_combo.setFixedWidth(200)
        row.addWidget(self._policy_combo)
        hint = QLabel("(blank = don\u2019t change)")
        hint.setStyleSheet(f"color: {t.TEXT_DIM}; font-size: {t.FONT_SMALL}px;")
        row.addWidget(hint)
        row.addStretch(1)
        form_layout.addLayout(row)

        # Pack Qty
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Pack Qty:"))
        self._pack_edit = QLineEdit()
        self._pack_edit.setFixedWidth(100)
        self._pack_edit.setPlaceholderText("blank = no change")
        row2.addWidget(self._pack_edit)
        row2.addStretch(1)
        form_layout.addLayout(row2)

        # Min Order Qty
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Min Order Qty:"))
        self._min_edit = QLineEdit()
        self._min_edit.setFixedWidth(100)
        self._min_edit.setPlaceholderText("blank = no change")
        row3.addWidget(self._min_edit)
        row3.addStretch(1)
        form_layout.addLayout(row3)

        # Cover Days
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("Cover Days:"))
        self._cover_edit = QLineEdit()
        self._cover_edit.setFixedWidth(100)
        self._cover_edit.setPlaceholderText("blank = no change")
        row4.addWidget(self._cover_edit)
        row4.addStretch(1)
        form_layout.addLayout(row4)

        root.addWidget(form_card)
        root.addStretch(1)

        # Footer
        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel_btn = _ghost_btn("Cancel")
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)
        apply_btn = _primary_btn("Apply to All Selected")
        apply_btn.clicked.connect(self._on_apply)
        footer.addWidget(apply_btn)
        root.addLayout(footer)

    @property
    def changes(self) -> dict | None:
        """The changes dict if applied, else None."""
        return self._changes

    def _on_apply(self):
        self._changes = {
            "order_policy": self._policy_combo.currentText(),
            "pack_size": self._pack_edit.text().strip(),
            "min_order_qty": self._min_edit.text().strip(),
            "cover_days": self._cover_edit.text().strip(),
        }
        self.accept()


# ═════════════════════════════════════════════════════════════════════════
# 9. Ignored Items Manager dialog
# ═════════════════════════════════════════════════════════════════════════

class IgnoredItemsDialog(QDialog):
    """View, filter, and remove items from the persistent ignore list."""

    def __init__(self, ignored_keys: list[str], *, parent=None):
        super().__init__(parent)
        self._all_keys = sorted(ignored_keys)
        self._keys_to_remove: set[str] = set()
        self._remove_all = False
        self.setWindowTitle("Ignored Items")
        self.resize(560, 500)
        self.setStyleSheet(_dialog_base_style())

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        root.setSpacing(t.SPACE_MD)

        root.addWidget(_header_label("Ignored Items"))
        root.addWidget(_subheader_label(
            "Items on this list are excluded from every session. "
            "Select and remove to restore them on the next load."
        ))

        # Filter
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Type to filter by line code or item code")
        self._filter_edit.textChanged.connect(self._refresh)
        filter_row.addWidget(self._filter_edit)
        root.addLayout(filter_row)

        # Table
        self._table = QTableWidget()
        _setup_table(self._table, ["Line Code", "Item Code"], stretches=[0, 1])
        root.addWidget(self._table, stretch=1)

        # Count label
        self._lbl_count = QLabel()
        self._lbl_count.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: {t.FONT_SMALL}px;")
        root.addWidget(self._lbl_count)

        # Footer
        footer = QHBoxLayout()
        footer.setSpacing(t.SPACE_SM)

        btn_remove = _danger_btn("Remove Selected")
        btn_remove.clicked.connect(self._on_remove)
        footer.addWidget(btn_remove)

        btn_remove_all = _ghost_btn("Remove All")
        btn_remove_all.clicked.connect(self._on_remove_all)
        footer.addWidget(btn_remove_all)

        footer.addStretch(1)
        close_btn = _primary_btn("Close")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        root.addLayout(footer)

        self._refresh()

    @property
    def keys_to_remove(self) -> set[str]:
        return set(self._keys_to_remove)

    @property
    def remove_all_requested(self) -> bool:
        return self._remove_all

    def _parse_key(self, key: str) -> tuple[str, str]:
        if ":" in key:
            idx = key.index(":")
            return key[:idx], key[idx + 1:]
        return "", key

    def _visible_keys(self) -> list[str]:
        needle = self._filter_edit.text().strip().lower()
        if not needle:
            return list(self._all_keys)
        result = []
        for key in self._all_keys:
            lc, ic = self._parse_key(key)
            if needle in lc.lower() or needle in ic.lower():
                result.append(key)
        return result

    def _refresh(self):
        visible = self._visible_keys()
        self._table.setRowCount(len(visible))
        for row, key in enumerate(visible):
            lc, ic = self._parse_key(key)
            cell_lc = QTableWidgetItem(lc)
            cell_lc.setFlags(cell_lc.flags() & ~Qt.ItemIsEditable)
            cell_lc.setData(Qt.UserRole, key)
            self._table.setItem(row, 0, cell_lc)
            cell_ic = QTableWidgetItem(ic)
            cell_ic.setFlags(cell_ic.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(row, 1, cell_ic)

        total = len(self._all_keys)
        shown = len(visible)
        if shown == total:
            self._lbl_count.setText(f"{total} item{'s' if total != 1 else ''} ignored")
        else:
            self._lbl_count.setText(f"Showing {shown} of {total} ignored items")

    def _on_remove(self):
        rows = {idx.row() for idx in self._table.selectionModel().selectedRows()}
        visible = self._visible_keys()
        for row in rows:
            if 0 <= row < len(visible):
                self._keys_to_remove.add(visible[row])
        if self._keys_to_remove:
            # Remove from local list and refresh
            self._all_keys = [k for k in self._all_keys if k not in self._keys_to_remove]
            self._refresh()

    def _on_remove_all(self):
        if not self._all_keys:
            return
        confirm = QMessageBox.question(
            self, "Remove All",
            f"Remove all {len(self._all_keys)} item(s) from the ignore list?\n\n"
            "They will reappear on the next file load.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self._remove_all = True
        self._keys_to_remove = set(self._all_keys)
        self.accept()


# ═════════════════════════════════════════════════════════════════════════
# 10. Vendor Policy Editor dialog
# ═════════════════════════════════════════════════════════════════════════

class VendorPolicyDialog(QDialog):
    """Configure shipping/release policy for a single vendor."""

    def __init__(self, vendor: str, policy: dict, *,
                 preset_options: list[tuple[str, str]] | None = None,
                 inferred_lead_days=None,
                 parent=None):
        super().__init__(parent)
        self._vendor = vendor
        self._saved_result: dict | None = None
        self.setWindowTitle(f"Shipping Policy \u2014 {vendor}")
        self.setMinimumWidth(540)
        self.setStyleSheet(_dialog_base_style())

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        root.setSpacing(t.SPACE_MD)

        root.addWidget(_header_label(f"Shipping Policy: {vendor}"))
        root.addWidget(_subheader_label(
            "Configure release timing. Leave default to clear the saved policy."
        ))

        # Form card
        form_card = QFrame()
        form_card.setStyleSheet(tq.card_style())
        form = QVBoxLayout(form_card)
        form.setContentsMargins(t.SPACE_MD, t.SPACE_MD, t.SPACE_MD, t.SPACE_MD)
        form.setSpacing(t.SPACE_SM)

        # Preset
        if preset_options:
            row = QHBoxLayout()
            row.addWidget(QLabel("Preset:"))
            self._preset_combo = QComboBox()
            self._preset_combo.addItem("")
            for key, label in preset_options:
                self._preset_combo.addItem(label, key)
            self._preset_combo.setFixedWidth(260)
            row.addWidget(self._preset_combo)
            row.addStretch(1)
            form.addLayout(row)
        else:
            self._preset_combo = None

        # Policy
        row_p = QHBoxLayout()
        row_p.addWidget(QLabel("Policy:"))
        self._policy_combo = QComboBox()
        self._policy_combo.addItems([
            "release_immediately",
            "hold_for_free_day",
            "hold_for_threshold",
            "hybrid_free_day_threshold",
        ])
        self._policy_combo.setCurrentText(policy.get("shipping_policy", "release_immediately"))
        self._policy_combo.setFixedWidth(260)
        row_p.addWidget(self._policy_combo)
        row_p.addStretch(1)
        form.addLayout(row_p)

        # Inferred lead time (read-only)
        lead_text = (f"{inferred_lead_days} days (from session history)"
                     if inferred_lead_days is not None else "\u2014 (no history yet)")
        row_lead = QHBoxLayout()
        row_lead.addWidget(QLabel("Inferred Lead Time:"))
        lead_lbl = QLabel(lead_text)
        lead_lbl.setStyleSheet(f"color: {t.TEXT_DIM};")
        row_lead.addWidget(lead_lbl)
        row_lead.addStretch(1)
        form.addLayout(row_lead)

        # Free-Ship Days
        row_wd = QHBoxLayout()
        row_wd.addWidget(QLabel("Free-Ship Days:"))
        self._weekdays_edit = QLineEdit()
        self._weekdays_edit.setFixedWidth(200)
        self._weekdays_edit.setText(", ".join(policy.get("preferred_free_ship_weekdays", [])))
        self._weekdays_edit.setPlaceholderText("e.g. Tuesday, Thursday")
        row_wd.addWidget(self._weekdays_edit)
        row_wd.addStretch(1)
        form.addLayout(row_wd)

        # Threshold
        row_th = QHBoxLayout()
        row_th.addWidget(QLabel("Freight Threshold:"))
        self._threshold_edit = QLineEdit()
        self._threshold_edit.setFixedWidth(120)
        th = policy.get("free_freight_threshold", 0)
        self._threshold_edit.setText(str(int(th)) if th and float(th).is_integer() else (str(th) if th else ""))
        row_th.addWidget(self._threshold_edit)
        row_th.addStretch(1)
        form.addLayout(row_th)

        # Urgent Floor
        row_uf = QHBoxLayout()
        row_uf.addWidget(QLabel("Urgent Floor:"))
        self._urgent_edit = QLineEdit()
        self._urgent_edit.setFixedWidth(120)
        uf = policy.get("urgent_release_floor", 0)
        self._urgent_edit.setText(str(int(uf)) if uf and float(uf).is_integer() else (str(uf) if uf else ""))
        row_uf.addWidget(self._urgent_edit)
        row_uf.addStretch(1)
        form.addLayout(row_uf)

        # Urgent Override
        row_um = QHBoxLayout()
        row_um.addWidget(QLabel("Urgent Override:"))
        self._urgent_mode_combo = QComboBox()
        self._urgent_mode_combo.addItems(["release_now", "paid_urgent_freight"])
        self._urgent_mode_combo.setCurrentText(policy.get("urgent_release_mode", "release_now"))
        self._urgent_mode_combo.setFixedWidth(200)
        row_um.addWidget(self._urgent_mode_combo)
        row_um.addStretch(1)
        form.addLayout(row_um)

        # Lead Days
        row_ld = QHBoxLayout()
        row_ld.addWidget(QLabel("Lead Days:"))
        self._lead_edit = QLineEdit()
        self._lead_edit.setFixedWidth(80)
        self._lead_edit.setText(str(int(policy.get("release_lead_business_days", 1) or 1)))
        row_ld.addWidget(self._lead_edit)
        row_ld.addStretch(1)
        form.addLayout(row_ld)

        root.addWidget(form_card)
        root.addStretch(1)

        # Footer
        footer = QHBoxLayout()
        footer.setSpacing(t.SPACE_SM)

        btn_clear = _ghost_btn("Clear Policy")
        btn_clear.clicked.connect(self._on_clear)
        footer.addWidget(btn_clear)

        footer.addStretch(1)

        cancel_btn = _ghost_btn("Close")
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)

        save_btn = _primary_btn("Save Policy")
        save_btn.clicked.connect(self._on_save)
        footer.addWidget(save_btn)
        root.addLayout(footer)

    @property
    def saved_result(self) -> dict | None:
        return self._saved_result

    def _on_clear(self):
        self._policy_combo.setCurrentText("release_immediately")
        self._weekdays_edit.clear()
        self._threshold_edit.clear()
        self._urgent_edit.clear()
        self._urgent_mode_combo.setCurrentText("release_now")
        self._lead_edit.setText("1")

    def _on_save(self):
        self._saved_result = {
            "shipping_policy": self._policy_combo.currentText(),
            "weekdays": self._weekdays_edit.text().strip(),
            "threshold": self._threshold_edit.text().strip(),
            "urgent_floor": self._urgent_edit.text().strip(),
            "urgent_mode": self._urgent_mode_combo.currentText(),
            "lead_days": self._lead_edit.text().strip(),
        }
        self.accept()


# ═════════════════════════════════════════════════════════════════════════
# 11. Vendor Manager dialog
# ═════════════════════════════════════════════════════════════════════════

class VendorManagerDialog(QDialog):
    """Add, rename, remove vendor codes and open policy editor."""

    def __init__(self, vendor_codes: list[str], *, parent=None):
        super().__init__(parent)
        self._vendors = list(vendor_codes)
        self._changes: list[dict] = []  # records of adds/removes/renames
        self.setWindowTitle("Vendor Manager")
        self.resize(540, 480)
        self.setStyleSheet(_dialog_base_style())

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        root.setSpacing(t.SPACE_MD)

        root.addWidget(_header_label("Vendor Manager"))
        root.addWidget(_subheader_label(
            "Add, rename, or remove vendor codes. "
            "Renaming also updates matching assignments in this session."
        ))

        # Vendor list table
        self._table = QTableWidget()
        _setup_table(self._table, ["Vendor Code"], stretches=[1])
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        root.addWidget(self._table, stretch=1)

        # Action row
        action_row = QHBoxLayout()
        action_row.setSpacing(t.SPACE_SM)

        btn_add = _ghost_btn("Add")
        btn_add.clicked.connect(self._on_add)
        action_row.addWidget(btn_add)

        btn_rename = _ghost_btn("Rename")
        btn_rename.clicked.connect(self._on_rename)
        action_row.addWidget(btn_rename)

        btn_remove = _danger_btn("Remove")
        btn_remove.clicked.connect(self._on_remove)
        action_row.addWidget(btn_remove)

        self._btn_policy = _ghost_btn("Shipping Policy\u2026")
        action_row.addWidget(self._btn_policy)

        action_row.addStretch(1)
        root.addLayout(action_row)

        # Footer
        footer = QHBoxLayout()
        footer.addStretch(1)
        close_btn = _primary_btn("Close")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        root.addLayout(footer)

        self._refresh()

    # Signal for the shell to open the policy editor for a vendor
    policy_edit_requested = Signal(str)

    @property
    def changes(self) -> list[dict]:
        return list(self._changes)

    @property
    def current_vendors(self) -> list[str]:
        return list(self._vendors)

    def _refresh(self):
        self._table.setRowCount(len(self._vendors))
        for row, code in enumerate(self._vendors):
            cell = QTableWidgetItem(code)
            cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(row, 0, cell)

    def _selected_vendor(self) -> str:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return ""
        row = rows[0].row()
        if 0 <= row < len(self._vendors):
            return self._vendors[row]
        return ""

    def _on_add(self):
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "Add Vendor", "Enter the new vendor code:")
        if not ok or not text.strip():
            return
        code = text.strip().upper()
        if code not in self._vendors:
            self._vendors.append(code)
            self._vendors.sort()
            self._changes.append({"action": "add", "code": code})
            self._refresh()

    def _on_rename(self):
        current = self._selected_vendor()
        if not current:
            QMessageBox.information(self, "Select Vendor", "Select a vendor to rename first.")
            return
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "Rename Vendor", "Enter the updated vendor code:", text=current)
        if not ok or not text.strip():
            return
        new_code = text.strip().upper()
        if new_code == current:
            return
        idx = self._vendors.index(current)
        self._vendors[idx] = new_code
        self._vendors.sort()
        self._changes.append({"action": "rename", "old": current, "new": new_code})
        self._refresh()

    def _on_remove(self):
        current = self._selected_vendor()
        if not current:
            QMessageBox.information(self, "Select Vendor", "Select a vendor to remove first.")
            return
        confirm = QMessageBox.question(
            self, "Remove Vendor",
            f"Remove vendor '{current}' from the saved list?\n\n"
            "This does not clear existing assignments on rows.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self._vendors.remove(current)
        self._changes.append({"action": "remove", "code": current})
        self._refresh()


# ═════════════════════════════════════════════════════════════════════════
# 12. Session History dialog
# ═════════════════════════════════════════════════════════════════════════

class SessionHistoryDialog(QDialog):
    """Browse past session snapshots and item histories."""

    def __init__(self, snapshots: list[dict], *, parent=None):
        super().__init__(parent)
        self._snapshots = snapshots
        self.setWindowTitle("Session History")
        self.resize(880, 620)
        self.setStyleSheet(_dialog_base_style())

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        root.setSpacing(t.SPACE_MD)

        count = len(snapshots)
        root.addWidget(_header_label("Session History"))
        root.addWidget(_subheader_label(
            f"{count} session{'s' if count != 1 else ''} found. "
            "Select a session to browse items. Select an item and click "
            "Copy Item History for its full order history."
        ))

        # Summary card
        cards = QWidget()
        cards_layout = QGridLayout(cards)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.addWidget(
            _summary_card(str(count), "sessions", "Loaded Snapshots", t.ACCENT_PRIMARY), 0, 0,
        )
        root.addWidget(cards)

        # Splitter
        splitter = QSplitter(Qt.Vertical)

        # Top: session list
        self._sess_table = QTableWidget()
        _setup_table(self._sess_table, ["Date", "Items", "Vendors", "Scope"], stretches=[0, 0, 0, 1])
        self._sess_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._sess_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._populate_sessions()
        self._sess_table.itemSelectionChanged.connect(self._on_session_selected)
        splitter.addWidget(self._sess_table)

        # Bottom: items
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, t.SPACE_SM, 0, 0)
        bottom_layout.setSpacing(t.SPACE_XS)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filter by item code or vendor")
        self._filter_edit.textChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._filter_edit)
        bottom_layout.addLayout(filter_row)

        self._item_table = QTableWidget()
        _setup_table(self._item_table, [
            "LC", "Item Code", "Description", "Vendor", "Sugg Qty", "Final Qty",
        ], stretches=[0, 0, 1, 0, 0, 0])
        bottom_layout.addWidget(self._item_table)
        splitter.addWidget(bottom)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, stretch=1)

        # Select first session
        if snapshots:
            self._sess_table.selectRow(0)

        # Footer
        footer = QHBoxLayout()
        footer.setSpacing(t.SPACE_SM)

        btn_copy = _ghost_btn("Copy Item History")
        btn_copy.clicked.connect(self._copy_item_history)
        footer.addWidget(btn_copy)

        hint = QLabel("(copies selected item\u2019s history across all sessions)")
        hint.setStyleSheet(f"color: {t.TEXT_DIM}; font-size: {t.FONT_SMALL}px;")
        footer.addWidget(hint)

        footer.addStretch(1)
        close_btn = _primary_btn("Close")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        root.addLayout(footer)

    def _snapshot_summary(self, snap: dict) -> dict:
        created_at = snap.get("created_at") or ""
        date_str = created_at[:19].replace("T", " ") if created_at else "\u2014"
        assigned = snap.get("assigned_items") or []
        vendors = {str(it.get("vendor") or "").strip().upper() for it in assigned}
        vendors.discard("")
        return {
            "date_str": date_str,
            "item_count": len(assigned),
            "vendor_count": len(vendors),
            "scope": snap.get("export_scope_label") or "\u2014",
        }

    def _populate_sessions(self):
        self._sess_table.setRowCount(len(self._snapshots))
        for row, snap in enumerate(self._snapshots):
            s = self._snapshot_summary(snap)
            for col, val in enumerate([s["date_str"], str(s["item_count"]),
                                       str(s["vendor_count"]), s["scope"]]):
                cell = QTableWidgetItem(val)
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                if col in (1, 2):
                    cell.setTextAlignment(Qt.AlignCenter)
                self._sess_table.setItem(row, col, cell)

    def _selected_snap(self) -> dict | None:
        rows = self._sess_table.selectionModel().selectedRows()
        if not rows:
            return None
        idx = rows[0].row()
        if 0 <= idx < len(self._snapshots):
            return self._snapshots[idx]
        return None

    def _on_session_selected(self):
        self._populate_items()

    def _on_filter_changed(self):
        self._populate_items()

    def _populate_items(self):
        self._item_table.setRowCount(0)
        snap = self._selected_snap()
        if snap is None:
            return
        assigned = snap.get("assigned_items") or []
        needle = self._filter_edit.text().strip().lower()
        rows = []
        for item in assigned:
            ic = str(item.get("item_code") or "")
            vendor = str(item.get("vendor") or "").strip().upper()
            if needle and needle not in ic.lower() and needle not in vendor.lower():
                continue
            rows.append(item)

        self._item_table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            sug = item.get("suggested_qty")
            fq = item.get("final_qty")
            values = [
                str(item.get("line_code") or ""),
                str(item.get("item_code") or ""),
                str(item.get("description") or ""),
                str(item.get("vendor") or "").strip().upper(),
                str(int(sug)) if isinstance(sug, (int, float)) and sug > 0 else "",
                str(int(fq)) if isinstance(fq, (int, float)) and fq > 0 else "",
            ]
            for col, val in enumerate(values):
                cell = QTableWidgetItem(val)
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                if col in (4, 5):
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._item_table.setItem(row, col, cell)

    def _copy_item_history(self):
        rows = self._item_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        lc_item = self._item_table.item(row, 0)
        ic_item = self._item_table.item(row, 1)
        if not lc_item or not ic_item:
            return
        line_code = lc_item.text()
        item_code = ic_item.text()

        # Gather history across all snapshots
        history = []
        for snap in self._snapshots:
            created_at = snap.get("created_at") or ""
            date_str = created_at[:19].replace("T", " ") if created_at else "\u2014"
            for item in (snap.get("assigned_items") or []):
                if (str(item.get("line_code") or "") == line_code
                        and str(item.get("item_code") or "") == item_code):
                    sug = item.get("suggested_qty")
                    fq = item.get("final_qty")
                    history.append(
                        f"{date_str}\t{line_code}\t{item_code}\t"
                        f"{str(item.get('vendor') or '').strip().upper()}\t"
                        f"{int(sug) if isinstance(sug, (int, float)) and sug > 0 else ''}\t"
                        f"{int(fq) if isinstance(fq, (int, float)) and fq > 0 else ''}"
                    )
                    break

        if history:
            header = "Session Date\tLine Code\tItem Code\tVendor\tSuggested Qty\tFinal Qty"
            tsv = header + "\n" + "\n".join(history)
            QApplication.clipboard().setText(tsv)
