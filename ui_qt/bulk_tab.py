"""Qt Bulk assignment tab — the primary working surface.

Layout (top → bottom):
    [ header banner                                            ]
    [ vendor worksheet combo | quick filter pills              ]
    [ vendor apply combo | Apply Selected | Apply Visible | …  ]
    [ filter row: search | line code | status | source | …     ]
    [ summary strip: 1,234 items · 456 assigned · $12,345      ]
    [ ─── QTableView (63K rows via model/proxy) ───────────── ]
    [                                                          ]
    [ status bar: cell info                                    ]

The table view uses:
- ``BulkTableModel`` — source data from ``filtered_items``
- ``BulkFilterProxyModel`` — multi-criteria filtering
- ``BulkDelegate`` — row tinting + cell editors

This module stays UI-only.  All business logic lives in the flow
modules (``assignment_flow``, ``bulk_edit_flow``, ``bulk_remove_flow``,
etc.) which are called from the shell's controller layer.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QItemSelectionModel
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
)

import theme as t
import theme_qt as tq
from debug_log import write_debug
from ui_qt.bulk_model import (
    BulkTableModel,
    COLUMNS,
    COL_INDEX,
    DEFAULT_HIDDEN,
    EDITABLE_COLS,
    LABELS,
    WIDTHS,
)
from ui_qt.bulk_delegate import BulkDelegate


class BulkTab(QWidget):
    """Top-level bulk assignment surface for the Qt build.

    Signals:
        vendor_applied(list[int], str)  — (source row indices, vendor code)
        rows_removed(list[int])         — source row indices removed
        edit_committed(int, str, str)   — (source row, col_name, new_value)
    """

    vendor_applied = Signal(list, str)
    rows_removed = Signal(list)
    remove_not_needed = Signal()
    ignore_item = Signal(str, str)  # (line_code, item_code)
    edit_committed = Signal(int, str, str)
    cycle_changed = Signal(int)  # cycle_weeks
    draft_review_requested = Signal()
    undo_requested = Signal()
    redo_requested = Signal()
    # Workflow dialog signals
    vendor_review_requested = Signal()
    session_diff_requested = Signal()
    supplier_map_requested = Signal()
    qoh_review_requested = Signal()
    skip_actions_requested = Signal()
    session_history_requested = Signal()
    ignored_items_requested = Signal()
    vendor_manager_requested = Signal()
    export_dead_stock = Signal()
    export_deferred = Signal()
    export_session_summary = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._model = BulkTableModel(self)
        self._hidden_columns: set[str] = set(DEFAULT_HIDDEN)
        self._known_vendors: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        layout.setSpacing(t.SPACE_SM)

        # ─── Header ──────────────────────────────────────────────
        header = QLabel()
        header.setTextFormat(Qt.RichText)
        header.setText(tq.tab_header_html(
            "Bulk Grid",
            "Assign vendors and review draft quantities",
        ))
        header.setStyleSheet(tq.tab_header_style())
        layout.addWidget(header)

        # ─── Quick filter pills (chip-styled) ────────────────────
        pills_row = QHBoxLayout()
        pills_row.setSpacing(t.SPACE_XS)

        _PILL_STYLE = (
            f"QPushButton {{ background: {t.BG_INSET}; color: {t.TEXT_MUTED}; "
            f"  border: 1px solid {t.BORDER}; border-radius: 12px; "
            f"  padding: 4px 14px; font-size: {t.FONT_SMALL}px; }}"
            f"QPushButton:hover {{ background: {t.BG_ELEVATED}; color: {t.TEXT_PRIMARY}; "
            f"  border-color: {t.BORDER_ACCENT}; }}"
        )
        _PILL_ACCENTS = {
            "All": t.ACCENT_PRIMARY,
            "Unassigned": t.ACCENT_WARNING,
            "Needs Review": t.ACCENT_DANGER,
            "Warnings": t.ACCENT_DANGER,
            "High Risk": t.ACCENT_SPECIAL,
            "Dead Stock": t.TEXT_DIM,
            "Deferred": t.ACCENT_WARNING,
        }
        for label, kwargs in [
            ("All", {}),
            ("Unassigned", {"status": "Unassigned"}),
            ("Needs Review", {"item_status": "Review"}),
            ("Warnings", {"item_status": "Warning"}),
            ("High Risk", {"attention": "High Risk"}),
            ("Dead Stock", {"special": "dead_stock"}),
            ("Deferred", {"special": "deferred"}),
        ]:
            btn = QPushButton(label)
            accent = _PILL_ACCENTS.get(label, t.ACCENT_PRIMARY)
            btn.setStyleSheet(
                f"QPushButton {{ background: {t.BG_INSET}; color: {t.TEXT_MUTED}; "
                f"  border: 1px solid {t.BORDER}; border-radius: 12px; "
                f"  padding: 4px 14px; font-size: {t.FONT_SMALL}px; }}"
                f"QPushButton:hover {{ background: {t.BG_ELEVATED}; color: {accent}; "
                f"  border-color: {accent}; }}"
            )
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, kw=kwargs: self._apply_quick_filter(**kw))
            pills_row.addWidget(btn)

        pills_row.addSpacing(t.SPACE_LG)

        # Vendor worksheet dropdown
        ws_label = QLabel("Vendor:")
        ws_label.setStyleSheet(f"color: {t.TEXT_DIM}; font-size: {t.FONT_SMALL}px;")
        pills_row.addWidget(ws_label)
        self._vendor_ws_combo = QComboBox()
        self._vendor_ws_combo.setFixedWidth(130)
        self._vendor_ws_combo.setEditable(True)
        self._vendor_ws_combo.addItem("")
        self._vendor_ws_combo.currentTextChanged.connect(self._on_vendor_worksheet_changed)
        pills_row.addWidget(self._vendor_ws_combo)

        pills_row.addSpacing(t.SPACE_LG)

        # Reorder cycle dropdown
        cycle_label = QLabel("Cycle:")
        cycle_label.setStyleSheet(f"color: {t.TEXT_DIM}; font-size: {t.FONT_SMALL}px;")
        pills_row.addWidget(cycle_label)
        self._cycle_combo = QComboBox()
        self._cycle_combo.setFixedWidth(110)
        self._cycle_combo.addItems(["Weekly", "Biweekly", "Monthly"])
        self._cycle_combo.setCurrentText("Biweekly")
        self._cycle_combo.currentTextChanged.connect(self._on_cycle_changed)
        pills_row.addWidget(self._cycle_combo)

        pills_row.addStretch(1)
        layout.addLayout(pills_row)

        # ─── Action bar (primary + secondary) ────────────────────
        action_card = QFrame()
        action_card.setStyleSheet(
            f"background: {t.BG_PANEL}; border: 1px solid {t.BORDER}; "
            f"border-radius: {t.RADIUS_SM}px;"
        )
        action_layout = QHBoxLayout(action_card)
        action_layout.setContentsMargins(t.SPACE_SM, t.SPACE_XS, t.SPACE_SM, t.SPACE_XS)
        action_layout.setSpacing(t.SPACE_SM)

        # Primary: vendor assign
        self._vendor_apply_combo = QComboBox()
        self._vendor_apply_combo.setEditable(True)
        self._vendor_apply_combo.setFixedWidth(120)
        self._vendor_apply_combo.setPlaceholderText("Vendor\u2026")
        action_layout.addWidget(self._vendor_apply_combo)

        _PRIMARY_BTN = (
            f"QPushButton {{ background: {t.ACCENT_PRIMARY}; color: {t.TEXT_INVERSE}; "
            f"  border: none; border-radius: {t.RADIUS_SM}px; "
            f"  padding: 5px 14px; font-weight: bold; font-size: {t.FONT_SMALL}px; }}"
            f"QPushButton:hover {{ background: #6bb0ea; }}"
        )
        btn_apply_sel = QPushButton("Apply to Selected")
        btn_apply_sel.setStyleSheet(_PRIMARY_BTN)
        btn_apply_sel.setCursor(Qt.PointingHandCursor)
        btn_apply_sel.clicked.connect(self._on_apply_vendor_selected)
        action_layout.addWidget(btn_apply_sel)

        btn_apply_vis = QPushButton("Apply to All Visible")
        btn_apply_vis.setStyleSheet(
            f"QPushButton {{ background: {t.BG_ELEVATED}; color: {t.TEXT_SECONDARY}; "
            f"  border: 1px solid {t.BORDER}; border-radius: {t.RADIUS_SM}px; "
            f"  padding: 5px 12px; font-size: {t.FONT_SMALL}px; }}"
            f"QPushButton:hover {{ border-color: {t.ACCENT_PRIMARY}; color: {t.TEXT_PRIMARY}; }}"
        )
        btn_apply_vis.clicked.connect(self._on_apply_vendor_visible)
        action_layout.addWidget(btn_apply_vis)

        self._add_separator(action_layout)

        # Secondary: remove, undo/redo
        _SECONDARY_BTN = (
            f"QPushButton {{ background: transparent; color: {t.TEXT_MUTED}; "
            f"  border: 1px solid {t.BORDER_SOFT}; border-radius: {t.RADIUS_SM}px; "
            f"  padding: 4px 10px; font-size: {t.FONT_SMALL}px; }}"
            f"QPushButton:hover {{ color: {t.TEXT_PRIMARY}; border-color: {t.BORDER}; }}"
        )
        for text, handler in [
            ("Remove Not Needed", self._on_remove_not_needed),
            ("Draft Review", self._on_draft_review),
            ("Undo", self._on_undo),
            ("Redo", self._on_redo),
        ]:
            btn = QPushButton(text)
            btn.setStyleSheet(_SECONDARY_BTN)
            btn.clicked.connect(handler)
            action_layout.addWidget(btn)

        self._add_separator(action_layout)

        # "More" dropdown — workflow dialogs
        btn_more = QPushButton("More \u25BE")
        btn_more.setStyleSheet(_SECONDARY_BTN)
        self._more_menu = QMenu(self)
        self._more_menu.addAction("Vendor Review", lambda: self.vendor_review_requested.emit())
        self._more_menu.addAction("Session Diff", lambda: self.session_diff_requested.emit())
        self._more_menu.addAction("Supplier Map", lambda: self.supplier_map_requested.emit())
        self._more_menu.addAction("QOH Adjustments", lambda: self.qoh_review_requested.emit())
        self._more_menu.addAction("Skip Cleanup", lambda: self.skip_actions_requested.emit())
        self._more_menu.addSeparator()
        self._more_menu.addAction("Session History", lambda: self.session_history_requested.emit())
        self._more_menu.addAction("Ignored Items", lambda: self.ignored_items_requested.emit())
        self._more_menu.addAction("Vendor Manager", lambda: self.vendor_manager_requested.emit())
        self._more_menu.addSeparator()
        reports_menu = self._more_menu.addMenu("Export Reports")
        reports_menu.addAction("Dead Stock Report", lambda: self.export_dead_stock.emit())
        reports_menu.addAction("Deferred Items Report", lambda: self.export_deferred.emit())
        reports_menu.addAction("Session Summary", lambda: self.export_session_summary.emit())
        btn_more.setMenu(self._more_menu)
        action_layout.addWidget(btn_more)

        action_layout.addStretch(1)
        layout.addWidget(action_card)

        # ─── Filter row (compact, inside a subtle card) ──────────
        filter_card = QFrame()
        filter_card.setStyleSheet(
            f"background: {t.BG_BASE}; border: 1px solid {t.BORDER_SOFT}; "
            f"border-radius: {t.RADIUS_SM}px;"
        )
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(t.SPACE_SM, t.SPACE_XS, t.SPACE_SM, t.SPACE_XS)
        filter_layout.setSpacing(t.SPACE_SM)

        _FILTER_LABEL = f"color: {t.TEXT_DIM}; font-size: {t.FONT_SMALL}px;"

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("\U0001F50D Search items\u2026")
        self._search_edit.setFixedWidth(200)
        self._search_edit.textChanged.connect(lambda t: self._model.apply_filters(text=t))
        filter_layout.addWidget(self._search_edit)

        for label_text, combo_attr, width, values, filter_key in [
            ("LC:", "_lc_combo", 80, ["ALL"], "line_code"),
            ("Status:", "_status_combo", 100, ["ALL", "Unassigned", "Assigned"], "status"),
            ("Source:", "_source_combo", 75, ["ALL", "Sales", "Susp", "Both"], "source"),
            ("Item:", "_item_status_combo", 90, ["ALL", "Review", "Warning", "Skip", "OK"], "item_status"),
        ]:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(_FILTER_LABEL)
            filter_layout.addWidget(lbl)
            combo = QComboBox()
            combo.setFixedWidth(width)
            combo.addItems(values)
            _key = filter_key
            combo.currentTextChanged.connect(lambda val, k=_key: self._model.apply_filters(**{k: val}))
            setattr(self, combo_attr, combo)
            filter_layout.addWidget(combo)

        btn_reset = QPushButton("\u00D7")
        btn_reset.setToolTip("Reset all filters")
        btn_reset.setFixedSize(24, 24)
        btn_reset.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {t.TEXT_DIM}; "
            f"  border: 1px solid {t.BORDER_SOFT}; border-radius: 12px; "
            f"  font-size: {t.FONT_MEDIUM}px; font-weight: bold; }}"
            f"QPushButton:hover {{ color: {t.ACCENT_DANGER}; border-color: {t.ACCENT_DANGER}; }}"
        )
        btn_reset.clicked.connect(self._reset_filters)
        filter_layout.addWidget(btn_reset)

        filter_layout.addStretch(1)
        layout.addWidget(filter_card)

        # ─── Summary strip (Tuner-style number cards) ──────────────
        summary_row = QHBoxLayout()
        summary_row.setSpacing(t.SPACE_SM)

        self._card_total = QLabel()
        self._card_total.setTextFormat(Qt.RichText)
        self._card_total.setAlignment(Qt.AlignCenter)
        self._card_total.setFixedHeight(52)
        self._card_total.setMinimumWidth(120)
        self._card_total.setStyleSheet(tq.number_card_style(t.ACCENT_PRIMARY))
        summary_row.addWidget(self._card_total)

        self._card_assigned = QLabel()
        self._card_assigned.setTextFormat(Qt.RichText)
        self._card_assigned.setAlignment(Qt.AlignCenter)
        self._card_assigned.setFixedHeight(52)
        self._card_assigned.setMinimumWidth(120)
        self._card_assigned.setStyleSheet(tq.number_card_style(t.ACCENT_OK))
        summary_row.addWidget(self._card_assigned)

        self._card_unassigned = QLabel()
        self._card_unassigned.setTextFormat(Qt.RichText)
        self._card_unassigned.setAlignment(Qt.AlignCenter)
        self._card_unassigned.setFixedHeight(52)
        self._card_unassigned.setMinimumWidth(120)
        self._card_unassigned.setStyleSheet(tq.number_card_style(t.ACCENT_WARNING))
        summary_row.addWidget(self._card_unassigned)

        self._card_visible = QLabel()
        self._card_visible.setTextFormat(Qt.RichText)
        self._card_visible.setAlignment(Qt.AlignCenter)
        self._card_visible.setFixedHeight(52)
        self._card_visible.setMinimumWidth(120)
        self._card_visible.setStyleSheet(tq.number_card_style(t.ACCENT_SPECIAL))
        summary_row.addWidget(self._card_visible)

        self._card_order_value = QLabel()
        self._card_order_value.setTextFormat(Qt.RichText)
        self._card_order_value.setAlignment(Qt.AlignCenter)
        self._card_order_value.setFixedHeight(52)
        self._card_order_value.setMinimumWidth(140)
        self._card_order_value.setStyleSheet(tq.number_card_style(t.ACCENT_SPECIAL))
        summary_row.addWidget(self._card_order_value)

        summary_row.addStretch(1)
        layout.addLayout(summary_row)

        # ─── Table view ──────────────────────────────────────────
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setItemDelegate(BulkDelegate(
            known_vendors_fn=lambda: self._known_vendors,
            parent=self._table,
        ))
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setSortingEnabled(True)
        # Intercept header clicks to detect Shift for secondary sort
        self._table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        # Only allow editing via double-click or F2 — Enter opens details
        self._table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self._table.setWordWrap(False)
        self._table.verticalHeader().setDefaultSectionSize(24)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setHighlightSections(False)
        self._table.horizontalHeader().setSectionsMovable(True)
        self._table.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.horizontalHeader().customContextMenuRequested.connect(
            self._on_header_context_menu
        )
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)

        # Apply column widths
        for col_name, width in WIDTHS.items():
            idx = COL_INDEX.get(col_name)
            if idx is not None:
                self._table.setColumnWidth(idx, width)

        # Apply default hidden columns
        self._apply_column_visibility()

        layout.addWidget(self._table, stretch=1)

        # ─── Status bar ──────────────────────────────────────────
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(
            f"color: {t.TEXT_DIM}; font-size: {t.FONT_SMALL}px;"
        )
        layout.addWidget(self._status_label)

        # ─── Keyboard shortcuts ───────────────────────────────────
        self._setup_shortcuts()

        # Update summary when filter changes
        self._model.modelReset.connect(self._update_summary)

    # ── Public API ────────────────────────────────────────────────

    @property
    def model(self) -> BulkTableModel:
        return self._model

    @property
    def proxy(self):
        """Compatibility property — the model now handles filtering directly."""
        return self._model

    @property
    def table(self) -> QTableView:
        return self._table

    def set_data(self, items, inventory_lookup, order_rules, suggest_min_max_fn=None):
        """Load data into the bulk grid."""
        write_debug("qt.bulk_tab.set_data", items=len(items),
                     inventory=len(inventory_lookup), rules=len(order_rules))
        self._model.set_data(items, inventory_lookup, order_rules, suggest_min_max_fn)
        self._update_line_code_combo()
        self._update_summary()

    def set_known_vendors(self, vendors: list[str]):
        self._known_vendors = list(vendors)
        # Refresh apply combo
        current = self._vendor_apply_combo.currentText()
        self._vendor_apply_combo.clear()
        self._vendor_apply_combo.addItems(self._known_vendors)
        self._vendor_apply_combo.setCurrentText(current)
        # Refresh worksheet combo
        ws_current = self._vendor_ws_combo.currentText()
        self._vendor_ws_combo.clear()
        self._vendor_ws_combo.addItem("")  # "All"
        self._vendor_ws_combo.addItems(self._known_vendors)
        self._vendor_ws_combo.setCurrentText(ws_current)

    def selected_source_rows(self) -> list[int]:
        """Return source (unfiltered) item indices for the current table selection."""
        selection = self._table.selectionModel().selectedRows()
        return sorted({self._model._source_index(idx.row())
                       for idx in selection
                       if 0 <= idx.row() < len(self._model._visible_indices)})

    def visible_source_rows(self) -> list[int]:
        """Return source (unfiltered) item indices for all visible rows."""
        return list(self._model._visible_indices)

    # ── Filter helpers ────────────────────────────────────────────

    def _apply_quick_filter(self, status="ALL", item_status="ALL", attention="ALL", special=""):
        write_debug("qt.bulk_tab.quick_filter", status=status, item_status=item_status,
                     attention=attention, special=special)
        self._status_combo.setCurrentText(status)
        self._item_status_combo.setCurrentText(item_status)
        self._model.apply_filters(special=special)
        if attention == "High Risk":
            self._search_edit.clear()
            self._lc_combo.setCurrentText("ALL")
            self._source_combo.setCurrentText("ALL")
            self._table.sortByColumn(
                COL_INDEX.get("risk", 0), Qt.DescendingOrder
            )

    def _on_cycle_changed(self, text: str):
        weeks = {"Weekly": 1, "Biweekly": 2, "Monthly": 4}.get(text, 2)
        write_debug("qt.bulk_tab.cycle_changed", cycle=text, weeks=weeks)
        self.cycle_changed.emit(weeks)

    def _on_vendor_worksheet_changed(self, text: str):
        write_debug("qt.bulk_tab.vendor_worksheet", vendor=text)
        self._model.apply_filters(vendor_ws=text)

    def _reset_filters(self):
        write_debug("qt.bulk_tab.reset_filters")
        # Block signals to avoid multiple filter rebuilds
        for w in (self._search_edit, self._lc_combo, self._status_combo,
                  self._source_combo, self._item_status_combo, self._vendor_ws_combo):
            w.blockSignals(True)
        self._search_edit.clear()
        self._lc_combo.setCurrentText("ALL")
        self._status_combo.setCurrentText("ALL")
        self._source_combo.setCurrentText("ALL")
        self._item_status_combo.setCurrentText("ALL")
        self._vendor_ws_combo.setCurrentText("")
        for w in (self._search_edit, self._lc_combo, self._status_combo,
                  self._source_combo, self._item_status_combo, self._vendor_ws_combo):
            w.blockSignals(False)
        self._model.reset_all_filters()

    def _update_line_code_combo(self):
        items = self._model.items
        lcs = sorted({item.get("line_code", "") for item in items if item.get("line_code")})
        current = self._lc_combo.currentText()
        self._lc_combo.clear()
        self._lc_combo.addItem("ALL")
        self._lc_combo.addItems(lcs)
        self._lc_combo.setCurrentText(current)

    def _update_summary(self):
        import time
        t0 = time.perf_counter()
        total = self._model.total_count
        visible = self._model.visible_count
        assigned = sum(
            1 for item in self._model.items
            if item.get("vendor")
        )
        unassigned = total - assigned
        self._card_total.setText(tq.number_card_html(
            f"{total:,}", "items", "Total", t.ACCENT_PRIMARY, value_font_size=t.FONT_HEADING,
        ))
        self._card_assigned.setText(tq.number_card_html(
            f"{assigned:,}", "items", "Assigned", t.ACCENT_OK, value_font_size=t.FONT_HEADING,
        ))
        self._card_unassigned.setText(tq.number_card_html(
            f"{unassigned:,}", "items", "Unassigned",
            t.ACCENT_WARNING if unassigned > 0 else t.ACCENT_OK,
            value_font_size=t.FONT_HEADING,
        ))
        if visible != total:
            self._card_visible.setText(tq.number_card_html(
                f"{visible:,}", "visible", "Filtered", t.ACCENT_SPECIAL,
                value_font_size=t.FONT_HEADING,
            ))
            self._card_visible.setVisible(True)
        else:
            self._card_visible.setVisible(False)
        inv_lookup = self._model._inventory_lookup or {}
        order_value = 0.0
        for item in self._model.items:
            if not item.get("vendor"):
                continue
            qty = item.get("final_qty", 0) or 0
            key = (item.get("line_code", ""), item.get("item_code", ""))
            cost = item.get("repl_cost") or (inv_lookup.get(key) or {}).get("repl_cost") or 0
            if isinstance(cost, (int, float)) and isinstance(qty, (int, float)):
                order_value += cost * qty
        if order_value > 0:
            self._card_order_value.setText(tq.number_card_html(
                f"${order_value:,.0f}", "estimated", "Order Value", t.ACCENT_SPECIAL,
                value_font_size=t.FONT_HEADING,
            ))
            self._card_order_value.setVisible(True)
        else:
            self._card_order_value.setVisible(False)
        elapsed = (time.perf_counter() - t0) * 1000
        write_debug("qt.update_summary", total=total, assigned=assigned,
                     visible=visible, order_value=round(order_value, 2),
                     elapsed_ms=round(elapsed, 1))

    # ── Action handlers (emit signals for the controller) ─────────

    def _on_apply_vendor_selected(self):
        vendor = self._vendor_apply_combo.currentText().strip().upper()
        if not vendor:
            return
        rows = self.selected_source_rows()
        if not rows:
            QMessageBox.information(self, "No Selection", "Select rows first.")
            return
        write_debug("qt.bulk_tab.apply_vendor_selected", vendor=vendor, rows=len(rows))
        self.vendor_applied.emit(rows, vendor)

    def _on_apply_vendor_visible(self):
        vendor = self._vendor_apply_combo.currentText().strip().upper()
        if not vendor:
            return
        rows = self.visible_source_rows()
        if not rows:
            return
        write_debug("qt.bulk_tab.apply_vendor_visible", vendor=vendor, rows=len(rows))
        self.vendor_applied.emit(rows, vendor)

    def _on_remove_not_needed(self):
        self.remove_not_needed.emit()

    def _on_draft_review(self):
        write_debug("qt.bulk_tab.draft_review")
        self.draft_review_requested.emit()

    def _on_undo(self):
        self.undo_requested.emit()

    def _on_redo(self):
        self.redo_requested.emit()

    # ── Context menus ─────────────────────────────────────────────

    def _on_header_clicked(self, logical_index: int):
        """Detect Shift+click for secondary sort."""
        from PySide6.QtWidgets import QApplication
        modifiers = QApplication.keyboardModifiers()
        header = self._table.horizontalHeader()
        order = header.sortIndicatorOrder()
        if modifiers & Qt.ShiftModifier:
            self._proxy.add_sort_key(logical_index, order)
            write_debug("qt.sort.secondary", col=COLUMNS[logical_index] if logical_index < len(COLUMNS) else logical_index,
                         keys=len(self._proxy.sort_keys))
        else:
            self._proxy.set_primary_sort(logical_index, order)

    def _on_header_context_menu(self, pos):
        """Column visibility toggle via header right-click."""
        menu = QMenu(self)
        for col_name in COLUMNS:
            label = LABELS.get(col_name, col_name)
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(col_name not in self._hidden_columns)
            action.toggled.connect(
                lambda checked, cn=col_name: self._toggle_column(cn, checked)
            )
        menu.exec(self._table.horizontalHeader().mapToGlobal(pos))

    def _on_table_context_menu(self, pos):
        """Row context menu."""
        idx = self._table.indexAt(pos)
        if not idx.isValid():
            return
        item = self._model.item_at(idx.row())
        if not item:
            return

        menu = QMenu(self)
        menu.addAction("Remove Selected Rows", self._ctx_remove_selected)
        menu.addSeparator()
        menu.addAction("View Item Details", lambda: self._ctx_view_details(item))
        menu.addAction("Edit Buy Rule", lambda: self._ctx_edit_buy_rule(item))
        menu.addSeparator()
        menu.addAction("Ignore Item", lambda: self._ctx_ignore_item(item))
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _ctx_remove_selected(self):
        rows = self.selected_source_rows()
        if rows:
            write_debug("qt.bulk_tab.ctx_remove_selected", rows=len(rows))
            self.rows_removed.emit(rows)

    def _ctx_view_details(self, item):
        from ui_qt.dialogs import ItemDetailsDialog
        key = (item.get("line_code", ""), item.get("item_code", ""))
        write_debug("qt.bulk_tab.view_details", line_code=key[0], item_code=key[1])
        inv = self._model._inventory_lookup.get(key, {})
        rule_key = f"{key[0]}:{key[1]}"
        rule = self._model._order_rules.get(rule_key, {})
        dialog = ItemDetailsDialog(item, inv, rule, parent=self)
        dialog.exec()

    def _ctx_edit_buy_rule(self, item):
        from ui_qt.dialogs import BuyRuleEditorDialog
        key = (item.get("line_code", ""), item.get("item_code", ""))
        rule_key = f"{key[0]}:{key[1]}"
        write_debug("qt.bulk_tab.edit_buy_rule.open", rule_key=rule_key)
        rule = self._model._order_rules.get(rule_key, {})
        dialog = BuyRuleEditorDialog(item, rule, parent=self)
        if dialog.exec() == BuyRuleEditorDialog.Accepted:
            new_rule = dialog.accepted_rule
            if new_rule is not None:
                if new_rule:
                    self._model._order_rules[rule_key] = new_rule
                else:
                    self._model._order_rules.pop(rule_key, None)
                # Find the source row for this item
                source_row = -1
                for i in range(self._model.rowCount()):
                    if self._model.item_at(i) is item:
                        source_row = i
                        break
                write_debug("qt.bulk_tab.buy_rule.saved",
                             rule_key=rule_key, source_row=source_row,
                             rule=str(new_rule)[:80])
                self.edit_committed.emit(source_row, "buy_rule", rule_key)
        else:
            write_debug("qt.bulk_tab.buy_rule.cancelled", rule_key=rule_key)

    def _ctx_ignore_item(self, item):
        lc = item.get("line_code", "")
        ic = item.get("item_code", "")
        if lc or ic:
            write_debug("qt.bulk_tab.ctx_ignore", line_code=lc, item_code=ic)
            self.ignore_item.emit(lc, ic)

    # ── Column visibility ─────────────────────────────────────────

    def _toggle_column(self, col_name: str, visible: bool):
        if visible:
            self._hidden_columns.discard(col_name)
        else:
            self._hidden_columns.add(col_name)
        self._apply_column_visibility()

    def _apply_column_visibility(self):
        for col_name in COLUMNS:
            idx = COL_INDEX.get(col_name)
            if idx is not None:
                self._table.setColumnHidden(idx, col_name in self._hidden_columns)

    # ── Keyboard shortcuts ────────────────────────────────────────

    def _setup_shortcuts(self):
        delete_action = QAction("Delete rows", self)
        delete_action.setShortcut(QKeySequence(Qt.Key_Delete))
        delete_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        delete_action.triggered.connect(self._on_delete_key)
        self.addAction(delete_action)

        undo_action = QAction("Undo", self)
        undo_action.setShortcut(QKeySequence.Undo)
        undo_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        undo_action.triggered.connect(self._on_undo)
        self.addAction(undo_action)

        redo_action = QAction("Redo", self)
        redo_action.setShortcut(QKeySequence.Redo)
        redo_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        redo_action.triggered.connect(self._on_redo)
        self.addAction(redo_action)

        enter_action = QAction("View details", self)
        enter_action.setShortcut(QKeySequence(Qt.Key_Return))
        enter_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        enter_action.triggered.connect(self._on_enter_key)
        self.addAction(enter_action)

        search_action = QAction("Focus search", self)
        search_action.setShortcut(QKeySequence("Ctrl+F"))
        search_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        search_action.triggered.connect(lambda: self._search_edit.setFocus())
        self.addAction(search_action)

    def _on_enter_key(self):
        """Enter key → view item details for the current row."""
        idx = self._table.currentIndex()
        if not idx.isValid():
            return
        item = self._model.item_at(idx.row())
        if item:
            self._ctx_view_details(item)

    def _on_delete_key(self):
        rows = self.selected_source_rows()
        if rows:
            write_debug("qt.bulk_tab.delete_key", rows=len(rows))
            confirm = QMessageBox.question(
                self, "Confirm Remove",
                f"Remove {len(rows)} item(s) from this session?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if confirm == QMessageBox.Yes:
                write_debug("qt.bulk_tab.delete_key.confirmed", rows=len(rows))
                self.rows_removed.emit(rows)
            else:
                write_debug("qt.bulk_tab.delete_key.cancelled")

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _add_separator(layout: QHBoxLayout):
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"color: {t.BORDER};")
        layout.addWidget(sep)
