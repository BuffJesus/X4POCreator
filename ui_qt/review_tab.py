"""Qt Review & Export tab — Tuner-style finish line.

The final surface before export.  Designed to feel like a confident
summary — "here's what you're about to send" — not a scary wall of
data.  The layout:

    [ header                                                 ]
    [ number cards: Ready | Exceptions | Vendors | Total Qty ]
    [ filter pills: All | Exceptions | vendor dropdown       ]
    [ ─── item table (vendor-grouped, exception-highlighted) ]
    [ ─── export finish line card ─────────────────────────  ]
"""

from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import theme as t
import theme_qt as tq


def _is_exception(item: dict) -> bool:
    """Return True if this item needs operator review before export."""
    status = str(item.get("status", "") or "").strip().lower()
    if status in ("review", "warning"):
        return True
    if item.get("review_required"):
        return True
    return False


class ReviewTab(QWidget):
    """Review & Export surface.

    Signals:
        export_requested(str) — output directory path
    """

    export_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        layout.setSpacing(t.SPACE_MD)

        # ── Header ────────────────────────────────────────────────
        header = QLabel()
        header.setTextFormat(Qt.RichText)
        header.setText(tq.tab_header_html(
            "Review & Export",
            "Confirm your selections, then export per-vendor PO files",
        ))
        header.setStyleSheet(tq.tab_header_style())
        layout.addWidget(header)

        # ── Number cards ──────────────────────────────────────────
        cards_row = QHBoxLayout()
        cards_row.setSpacing(t.SPACE_SM)

        self._card_ready = QLabel()
        self._card_ready.setTextFormat(Qt.RichText)
        self._card_ready.setAlignment(Qt.AlignCenter)
        self._card_ready.setFixedHeight(56)
        self._card_ready.setMinimumWidth(130)
        self._card_ready.setStyleSheet(tq.number_card_style(t.ACCENT_OK))
        cards_row.addWidget(self._card_ready)

        self._card_exceptions = QLabel()
        self._card_exceptions.setTextFormat(Qt.RichText)
        self._card_exceptions.setAlignment(Qt.AlignCenter)
        self._card_exceptions.setFixedHeight(56)
        self._card_exceptions.setMinimumWidth(130)
        self._card_exceptions.setStyleSheet(tq.number_card_style(t.ACCENT_WARNING))
        cards_row.addWidget(self._card_exceptions)

        self._card_vendors = QLabel()
        self._card_vendors.setTextFormat(Qt.RichText)
        self._card_vendors.setAlignment(Qt.AlignCenter)
        self._card_vendors.setFixedHeight(56)
        self._card_vendors.setMinimumWidth(130)
        self._card_vendors.setStyleSheet(tq.number_card_style(t.ACCENT_PRIMARY))
        cards_row.addWidget(self._card_vendors)

        self._card_qty = QLabel()
        self._card_qty.setTextFormat(Qt.RichText)
        self._card_qty.setAlignment(Qt.AlignCenter)
        self._card_qty.setFixedHeight(56)
        self._card_qty.setMinimumWidth(130)
        self._card_qty.setStyleSheet(tq.number_card_style(t.ACCENT_SPECIAL))
        cards_row.addWidget(self._card_qty)

        cards_row.addStretch(1)
        layout.addLayout(cards_row)

        # ── Filter pills ──────────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.setSpacing(t.SPACE_XS)

        _PILL = (
            f"QPushButton {{ background: {t.BG_INSET}; color: {t.TEXT_MUTED}; "
            f"  border: 1px solid {t.BORDER}; border-radius: 12px; "
            f"  padding: 4px 14px; font-size: {t.FONT_SMALL}px; }}"
            f"QPushButton:hover {{ background: {t.BG_ELEVATED}; "
            f"  color: {t.TEXT_PRIMARY}; border-color: {t.BORDER_ACCENT}; }}"
        )

        btn_all = QPushButton("All Assigned")
        btn_all.setStyleSheet(_PILL)
        btn_all.setCursor(Qt.PointingHandCursor)
        btn_all.clicked.connect(lambda: self._set_show("All Assigned"))
        filter_row.addWidget(btn_all)

        btn_exc = QPushButton("Exceptions Only")
        btn_exc.setStyleSheet(
            f"QPushButton {{ background: {t.BG_INSET}; color: {t.TEXT_MUTED}; "
            f"  border: 1px solid {t.BORDER}; border-radius: 12px; "
            f"  padding: 4px 14px; font-size: {t.FONT_SMALL}px; }}"
            f"QPushButton:hover {{ background: {t.BG_ELEVATED}; "
            f"  color: {t.ACCENT_WARNING}; border-color: {t.ACCENT_WARNING}; }}"
        )
        btn_exc.setCursor(Qt.PointingHandCursor)
        btn_exc.clicked.connect(lambda: self._set_show("Exceptions Only"))
        filter_row.addWidget(btn_exc)

        filter_row.addSpacing(t.SPACE_MD)
        vl = QLabel("Vendor:")
        vl.setStyleSheet(f"color: {t.TEXT_DIM}; font-size: {t.FONT_SMALL}px;")
        filter_row.addWidget(vl)
        self._vendor_combo = QComboBox()
        self._vendor_combo.setFixedWidth(130)
        self._vendor_combo.addItem("ALL")
        self._vendor_combo.currentTextChanged.connect(self._refresh_table)
        filter_row.addWidget(self._vendor_combo)

        filter_row.addStretch(1)
        layout.addLayout(filter_row)

        # ── Item table ────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "Vendor", "LC", "Item Code", "Description",
            "Final Qty", "Status", "Why",
        ])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setDefaultSectionSize(26)
        self._table.verticalHeader().setVisible(False)
        self._table.setColumnWidth(0, 80)
        self._table.setColumnWidth(1, 48)
        self._table.setColumnWidth(2, 100)
        self._table.setColumnWidth(3, 200)
        self._table.setColumnWidth(4, 70)
        self._table.setColumnWidth(5, 70)
        layout.addWidget(self._table, stretch=1)

        # ── Export finish line ────────────────────────────────────
        export_card = QFrame()
        export_card.setStyleSheet(
            f"background: {t.BG_PANEL}; "
            f"border: 2px solid {t.ACCENT_OK}; "
            f"border-radius: {t.RADIUS_MD}px;"
        )
        export_layout = QHBoxLayout(export_card)
        export_layout.setContentsMargins(t.SPACE_LG, t.SPACE_MD, t.SPACE_LG, t.SPACE_MD)
        export_layout.setSpacing(t.SPACE_MD)

        self._export_summary = QLabel()
        self._export_summary.setTextFormat(Qt.RichText)
        self._export_summary.setStyleSheet(f"color: {t.TEXT_SECONDARY};")
        export_layout.addWidget(self._export_summary, stretch=1)

        self._export_btn = QPushButton("Export PO Files \u2192")
        self._export_btn.setFixedHeight(40)
        self._export_btn.setMinimumWidth(200)
        self._export_btn.setCursor(Qt.PointingHandCursor)
        self._export_btn.setStyleSheet(
            f"QPushButton {{ background: {t.ACCENT_OK}; "
            f"  color: {t.TEXT_INVERSE}; border: none; "
            f"  border-radius: {t.RADIUS_SM}px; font-weight: bold; "
            f"  font-size: {t.FONT_MEDIUM}px; padding: 8px 24px; }}"
            f"QPushButton:hover {{ background: #4ec878; }}"
            f"QPushButton:disabled {{ background: {t.BG_INSET}; "
            f"  color: {t.TEXT_DIM}; border: 1px solid {t.BORDER}; }}"
        )
        self._export_btn.clicked.connect(self._on_export)
        self._export_btn.setEnabled(False)
        export_layout.addWidget(self._export_btn)

        layout.addWidget(export_card)

        # Internal state
        self._show_mode = "All Assigned"

    # ── Public API ────────────────────────────────────────────────

    def set_items(self, items: list[dict]):
        self._items = list(items)
        vendors = sorted({
            str(item.get("vendor", "")).strip().upper()
            for item in items if item.get("vendor")
        })
        current = self._vendor_combo.currentText()
        self._vendor_combo.clear()
        self._vendor_combo.addItem("ALL")
        self._vendor_combo.addItems(vendors)
        self._vendor_combo.setCurrentText(current if current in (["ALL"] + vendors) else "ALL")
        self._export_btn.setEnabled(bool(items))
        self._refresh_table()

    # ── Internal ──────────────────────────────────────────────────

    def _set_show(self, mode: str):
        self._show_mode = mode
        self._refresh_table()

    def _refresh_table(self, _=None):
        vendor_filter = self._vendor_combo.currentText()

        visible = []
        for item in self._items:
            if vendor_filter != "ALL":
                if str(item.get("vendor", "")).strip().upper() != vendor_filter:
                    continue
            if self._show_mode == "Exceptions Only" and not _is_exception(item):
                continue
            visible.append(item)

        # Group by vendor for visual separation
        by_vendor = defaultdict(list)
        for item in visible:
            by_vendor[str(item.get("vendor", "")).strip().upper()].append(item)

        total_rows = len(visible)
        self._table.setRowCount(total_rows)
        exceptions = 0
        row_idx = 0
        for vendor_code in sorted(by_vendor.keys()):
            vendor_items = by_vendor[vendor_code]
            for item in vendor_items:
                is_exc = _is_exception(item)
                if is_exc:
                    exceptions += 1
                values = [
                    item.get("vendor", ""),
                    item.get("line_code", ""),
                    item.get("item_code", ""),
                    item.get("description", ""),
                    str(item.get("final_qty", item.get("order_qty", 0))),
                    item.get("status", ""),
                    item.get("why", "")[:80],
                ]
                for col, val in enumerate(values):
                    cell = QTableWidgetItem(str(val))
                    if is_exc:
                        cell.setForeground(QColor(t.ACCENT_WARNING))
                    elif col == 0:
                        cell.setForeground(QColor(t.ACCENT_OK))
                    self._table.setItem(row_idx, col, cell)
                row_idx += 1

        # Update number cards
        total = len(self._items)
        ready = total - sum(1 for i in self._items if _is_exception(i))
        all_exceptions = sum(1 for i in self._items if _is_exception(i))
        vendors = len({str(i.get("vendor", "")).strip() for i in self._items if i.get("vendor")})
        total_qty = sum(i.get("final_qty", i.get("order_qty", 0)) or 0 for i in self._items)

        self._card_ready.setText(tq.number_card_html(
            f"{ready:,}", "items", "Ready to Export",
            t.ACCENT_OK if ready > 0 else t.TEXT_DIM,
            value_font_size=t.FONT_HEADING,
        ))
        exc_accent = t.ACCENT_WARNING if all_exceptions > 0 else t.ACCENT_OK
        self._card_exceptions.setText(tq.number_card_html(
            f"{all_exceptions:,}", "items", "Exceptions",
            exc_accent, value_font_size=t.FONT_HEADING,
        ))
        self._card_vendors.setText(tq.number_card_html(
            f"{vendors:,}", "vendors", "Vendor Files",
            t.ACCENT_PRIMARY, value_font_size=t.FONT_HEADING,
        ))
        self._card_qty.setText(tq.number_card_html(
            f"{total_qty:,}", "units", "Total Quantity",
            t.ACCENT_SPECIAL, value_font_size=t.FONT_HEADING,
        ))

        # Update export finish line
        if total > 0:
            self._export_summary.setText(
                f"<span style='font-size: {t.FONT_BODY}px; color: {t.TEXT_PRIMARY};'>"
                f"<b>{ready:,}</b> items across <b>{vendors}</b> vendors ready to export</span>"
                f"<br><span style='font-size: {t.FONT_SMALL}px; color: {t.TEXT_DIM};'>"
                f"{total_qty:,} total units"
                f"{f' &middot; {all_exceptions} exception(s) to review' if all_exceptions else ''}"
                f"</span>"
            )
        else:
            self._export_summary.setText(
                f"<span style='color: {t.TEXT_DIM};'>No assigned items yet. "
                f"Go to the Bulk Grid to assign vendors.</span>"
            )

    def _on_export(self):
        output_dir = QFileDialog.getExistingDirectory(
            self, "Select Output Folder for PO Files",
        )
        if output_dir:
            self.export_requested.emit(output_dir)
