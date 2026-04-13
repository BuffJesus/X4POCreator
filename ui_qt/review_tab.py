"""Qt Review & Export tab with a guided finish-line layout."""

from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QKeySequence, QShortcut

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
    """Review and export surface for assigned items."""

    export_requested = Signal(str)
    items_changed = Signal()  # emitted after edits or removals

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[dict] = []
        self._filter_buttons: dict[str, QPushButton] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        layout.setSpacing(t.SPACE_MD)

        header = QLabel()
        header.setTextFormat(Qt.RichText)
        header.setText(
            tq.tab_header_html(
                "Review & Export",
                "Check the final scope, then export per-vendor PO files",
            )
        )
        header.setStyleSheet(tq.tab_header_style())
        layout.addWidget(header)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(t.SPACE_SM)
        self._card_ready = self._make_card(t.ACCENT_OK)
        self._card_exceptions = self._make_card(t.ACCENT_WARNING)
        self._card_vendors = self._make_card(t.ACCENT_PRIMARY)
        self._card_qty = self._make_card(t.ACCENT_SPECIAL)
        for card in (self._card_ready, self._card_exceptions, self._card_vendors, self._card_qty):
            cards_row.addWidget(card)
        cards_row.addStretch(1)
        layout.addLayout(cards_row)

        self._context_card = QFrame()
        self._context_card.setStyleSheet(tq.card_style(t.ACCENT_PRIMARY))
        context_layout = QHBoxLayout(self._context_card)
        context_layout.setContentsMargins(t.SPACE_MD, t.SPACE_MD, t.SPACE_MD, t.SPACE_MD)
        context_layout.setSpacing(t.SPACE_MD)

        context_copy = QVBoxLayout()
        context_copy.setSpacing(t.SPACE_XS)
        context_layout.addLayout(context_copy, stretch=3)

        context_title = QLabel("Final review before export")
        context_title.setStyleSheet(
            f"color: {t.TEXT_PRIMARY}; font-size: {t.FONT_BODY}px; font-weight: bold;"
        )
        context_copy.addWidget(context_title)

        self._context_summary = QLabel()
        self._context_summary.setWordWrap(True)
        self._context_summary.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FONT_SMALL}px;"
        )
        context_copy.addWidget(self._context_summary)

        self._focus_chip = QLabel()
        self._focus_chip.setTextFormat(Qt.RichText)
        self._focus_chip.setAlignment(Qt.AlignCenter)
        self._focus_chip.setMinimumWidth(240)
        self._focus_chip.setStyleSheet(tq.chip_style(t.ACCENT_WARNING))
        context_layout.addWidget(self._focus_chip, stretch=2)
        layout.addWidget(self._context_card)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(t.SPACE_XS)

        btn_all = QPushButton("All Assigned")
        btn_all.setCursor(Qt.PointingHandCursor)
        btn_all.clicked.connect(lambda: self._set_show("All Assigned"))
        self._filter_buttons["All Assigned"] = btn_all
        filter_row.addWidget(btn_all)

        btn_exc = QPushButton("Exceptions Only")
        btn_exc.setCursor(Qt.PointingHandCursor)
        btn_exc.clicked.connect(lambda: self._set_show("Exceptions Only"))
        self._filter_buttons["Exceptions Only"] = btn_exc
        filter_row.addWidget(btn_exc)

        filter_row.addSpacing(t.SPACE_MD)
        vendor_label = QLabel("Vendor:")
        vendor_label.setStyleSheet(f"color: {t.TEXT_DIM}; font-size: {t.FONT_SMALL}px;")
        filter_row.addWidget(vendor_label)

        self._vendor_combo = QComboBox()
        self._vendor_combo.setFixedWidth(160)
        self._vendor_combo.addItem("ALL")
        self._vendor_combo.currentTextChanged.connect(self._refresh_table)
        filter_row.addWidget(self._vendor_combo)
        filter_row.addStretch(1)
        layout.addLayout(filter_row)

        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ["Vendor", "LC", "Item Code", "Description", "Final Qty", "Status", "Why"]
        )
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        self._table.cellChanged.connect(self._on_cell_changed)
        self._delete_shortcut = QShortcut(QKeySequence(Qt.Key_Delete), self._table)
        self._delete_shortcut.activated.connect(self._remove_selected)
        self._backspace_shortcut = QShortcut(QKeySequence(Qt.Key_Backspace), self._table)
        self._backspace_shortcut.activated.connect(self._remove_selected)
        self._table.verticalHeader().setDefaultSectionSize(26)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self._table.setStyleSheet(
            f"QTableWidget {{ background: {t.BG_PANEL}; border: 1px solid {t.BORDER}; "
            f"border-radius: {t.RADIUS_MD}px; gridline-color: {t.BORDER_SOFT}; }}"
            f"QHeaderView::section {{ background: {t.BG_ELEVATED}; color: {t.TEXT_MUTED}; "
            f"border: none; border-bottom: 1px solid {t.BORDER}; padding: {t.SPACE_SM}px; "
            f"font-size: {t.FONT_SMALL}px; font-weight: bold; }}"
        )
        layout.addWidget(self._table, stretch=1)

        export_card = QFrame()
        export_card.setStyleSheet(tq.card_style(t.ACCENT_OK))
        export_layout = QHBoxLayout(export_card)
        export_layout.setContentsMargins(t.SPACE_LG, t.SPACE_MD, t.SPACE_LG, t.SPACE_MD)
        export_layout.setSpacing(t.SPACE_MD)

        self._export_summary = QLabel()
        self._export_summary.setTextFormat(Qt.RichText)
        self._export_summary.setStyleSheet(f"color: {t.TEXT_SECONDARY};")
        export_layout.addWidget(self._export_summary, stretch=1)

        self._export_btn = QPushButton("Export PO Files ->")
        self._export_btn.setFixedHeight(40)
        self._export_btn.setMinimumWidth(200)
        self._export_btn.setCursor(Qt.PointingHandCursor)
        self._export_btn.setStyleSheet(
            f"QPushButton {{ background: {t.ACCENT_OK}; color: {t.TEXT_INVERSE}; border: none; "
            f"border-radius: {t.RADIUS_SM}px; font-weight: bold; font-size: {t.FONT_MEDIUM}px; "
            f"padding: 8px 24px; }}"
            f"QPushButton:hover {{ background: {t.ACCENT_PRIMARY}; }}"
            f"QPushButton:disabled {{ background: {t.BG_INSET}; color: {t.TEXT_DIM}; "
            f"border: 1px solid {t.BORDER}; }}"
        )
        self._export_btn.clicked.connect(self._on_export)
        self._export_btn.setEnabled(False)
        export_layout.addWidget(self._export_btn)
        layout.addWidget(export_card)

        self._show_mode = "All Assigned"
        self._update_filter_button_styles()
        self._refresh_table()

    def set_items(self, items: list[dict]):
        self._items = list(items)
        vendors = sorted(
            {
                str(item.get("vendor", "")).strip().upper()
                for item in items
                if item.get("vendor")
            }
        )
        current = self._vendor_combo.currentText()
        self._vendor_combo.clear()
        self._vendor_combo.addItem("ALL")
        self._vendor_combo.addItems(vendors)
        self._vendor_combo.setCurrentText(current if current in (["ALL"] + vendors) else "ALL")
        self._export_btn.setEnabled(bool(items))
        self._refresh_table()

    def _make_card(self, accent: str) -> QLabel:
        card = QLabel()
        card.setTextFormat(Qt.RichText)
        card.setAlignment(Qt.AlignCenter)
        card.setFixedHeight(56)
        card.setMinimumWidth(130)
        card.setStyleSheet(tq.number_card_style(accent))
        return card

    def _set_show(self, mode: str):
        self._show_mode = mode
        self._update_filter_button_styles()
        self._refresh_table()

    def _refresh_table(self, _=None):
        vendor_filter = self._vendor_combo.currentText()
        visible = []
        for item in self._items:
            if vendor_filter != "ALL" and str(item.get("vendor", "")).strip().upper() != vendor_filter:
                continue
            if self._show_mode == "Exceptions Only" and not _is_exception(item):
                continue
            visible.append(item)

        by_vendor = defaultdict(list)
        for item in visible:
            by_vendor[str(item.get("vendor", "")).strip().upper()].append(item)

        self._table.blockSignals(True)
        self._visible_items = visible
        self._table.setRowCount(len(visible))
        row_idx = 0
        for vendor_code in sorted(by_vendor.keys()):
            for item in by_vendor[vendor_code]:
                is_exc = _is_exception(item)
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
                    # Vendor (0) and Final Qty (4) are editable
                    if col not in (0, 4):
                        cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                    if is_exc:
                        cell.setForeground(QColor(t.ACCENT_WARNING))
                    elif col == 0:
                        cell.setForeground(QColor(t.ACCENT_OK))
                    if col == 4:
                        cell.setTextAlignment(Qt.AlignCenter)
                    self._table.setItem(row_idx, col, cell)
                row_idx += 1
        self._table.blockSignals(False)

        total = len(self._items)
        ready = total - sum(1 for item in self._items if _is_exception(item))
        all_exceptions = sum(1 for item in self._items if _is_exception(item))
        vendors = len({str(item.get("vendor", "")).strip() for item in self._items if item.get("vendor")})
        total_qty = sum(item.get("final_qty", item.get("order_qty", 0)) or 0 for item in self._items)
        visible_vendors = len(by_vendor)

        self._card_ready.setText(
            tq.number_card_html(
                f"{ready:,}",
                "items",
                "Ready to Export",
                t.ACCENT_OK if ready > 0 else t.TEXT_DIM,
                value_font_size=t.FONT_HEADING,
            )
        )
        self._card_exceptions.setText(
            tq.number_card_html(
                f"{all_exceptions:,}",
                "items",
                "Exceptions",
                t.ACCENT_WARNING if all_exceptions > 0 else t.ACCENT_OK,
                value_font_size=t.FONT_HEADING,
            )
        )
        self._card_vendors.setText(
            tq.number_card_html(
                f"{vendors:,}",
                "vendors",
                "Vendor Files",
                t.ACCENT_PRIMARY,
                value_font_size=t.FONT_HEADING,
            )
        )
        self._card_qty.setText(
            tq.number_card_html(
                f"{total_qty:,}",
                "units",
                "Total Quantity",
                t.ACCENT_SPECIAL,
                value_font_size=t.FONT_HEADING,
            )
        )

        if total:
            self._context_summary.setText(
                f"You have <b>{ready:,}</b> item(s) ready across <b>{vendors}</b> vendor file(s). "
                f"Use the filters to narrow the list, then continue when the scope looks right."
            )
        else:
            self._context_summary.setText(
                "Nothing is ready here yet. Assign vendors in the Bulk Grid and return for the final check."
            )

        top_vendor, top_count = self._top_exception_vendor()
        if all_exceptions and top_vendor:
            self._focus_chip.setText(
                f"<span style='color: {t.ACCENT_WARNING}; font-weight: bold;'>{all_exceptions:,}</span>"
                f"<span style='color: {t.TEXT_MUTED};'> exception(s)</span><br>"
                f"<span style='color: {t.TEXT_DIM}; font-size: {t.FONT_MICRO}px;'>"
                f"Most attention: {top_vendor} ({top_count})</span>"
            )
        else:
            filter_label = self._show_mode if vendor_filter == "ALL" else f"{self._show_mode} - {vendor_filter}"
            self._focus_chip.setText(
                f"<span style='color: {t.ACCENT_OK}; font-weight: bold;'>{visible_vendors:,}</span>"
                f"<span style='color: {t.TEXT_MUTED};'> vendor view(s)</span><br>"
                f"<span style='color: {t.TEXT_DIM}; font-size: {t.FONT_MICRO}px;'>"
                f"Current filter: {filter_label}</span>"
            )

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

    def _update_filter_button_styles(self):
        for mode, button in self._filter_buttons.items():
            accent = t.ACCENT_WARNING if mode == "Exceptions Only" else t.ACCENT_PRIMARY
            fill = t.FILL_WARNING_SOFT if mode == "Exceptions Only" else t.FILL_PRIMARY_SOFT
            if mode == self._show_mode:
                button.setStyleSheet(
                    f"QPushButton {{ background: {fill}; color: {accent}; border: 1px solid {accent}; "
                    f"border-radius: 12px; padding: 4px 14px; font-size: {t.FONT_SMALL}px; "
                    f"font-weight: bold; }}"
                )
            else:
                button.setStyleSheet(
                    f"QPushButton {{ background: {t.BG_INSET}; color: {t.TEXT_MUTED}; border: 1px solid {t.BORDER}; "
                    f"border-radius: 12px; padding: 4px 14px; font-size: {t.FONT_SMALL}px; }}"
                    f"QPushButton:hover {{ background: {t.BG_ELEVATED}; color: {accent}; border-color: {accent}; }}"
                )

    def _top_exception_vendor(self):
        counts = defaultdict(int)
        for item in self._items:
            if _is_exception(item):
                vendor = str(item.get("vendor", "")).strip().upper() or "UNASSIGNED"
                counts[vendor] += 1
        if not counts:
            return None, 0
        vendor = max(sorted(counts), key=lambda code: counts[code])
        return vendor, counts[vendor]

    def _on_cell_changed(self, row: int, col: int):
        """Propagate edits on Vendor or Final Qty back to the item dict."""
        if not hasattr(self, "_visible_items") or row >= len(self._visible_items):
            return
        item = self._visible_items[row]
        cell = self._table.item(row, col)
        if not cell:
            return
        if col == 0:  # Vendor
            item["vendor"] = cell.text().strip().upper()
            self.items_changed.emit()
        elif col == 4:  # Final Qty
            try:
                qty = int(float(cell.text()))
                item["final_qty"] = qty
                item["order_qty"] = qty
                item["manual_override"] = True
                self.items_changed.emit()
            except (ValueError, TypeError):
                self._table.blockSignals(True)
                cell.setText(str(item.get("final_qty", 0)))
                self._table.blockSignals(False)

    def _remove_selected(self):
        """Remove selected rows from the review items list."""
        selected_rows = sorted({idx.row() for idx in self._table.selectedIndexes()}, reverse=True)
        if not selected_rows or not hasattr(self, "_visible_items"):
            return
        to_remove = set()
        for row in selected_rows:
            if row < len(self._visible_items):
                item = self._visible_items[row]
                to_remove.add((item.get("line_code", ""), item.get("item_code", "")))
        if not to_remove:
            return
        before = len(self._items)
        self._items = [
            item for item in self._items
            if (item.get("line_code", ""), item.get("item_code", "")) not in to_remove
        ]
        removed = before - len(self._items)
        if removed:
            self._refresh_table()
            self.items_changed.emit()

    def _on_context_menu(self, pos):
        idx = self._table.indexAt(pos)
        if not idx.isValid():
            return
        menu = QMenu(self)
        menu.addAction("Remove Selected Rows", self._remove_selected)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _on_export(self):
        self.export_requested.emit("")
