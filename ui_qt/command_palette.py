"""Qt command palette — Ctrl+K to open, type to search, Enter to run.

Reuses the index-building and ranking functions from
``command_palette_data.py`` (UI-agnostic) and presents them in a Qt dialog.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

import theme as t

# Import the UI-agnostic index/rank functions
from command_palette_data import (
    build_item_index,
    build_vendor_index,
    rank_results,
)


def _build_action_index(shell) -> list[dict]:
    """Build action index adapted for the Qt shell."""
    from ui_qt.shell import NAV_ITEMS

    actions = []
    for i, (label, tooltip) in enumerate(NAV_ITEMS):
        def _switch(idx=i):
            shell.sidebar.setCurrentRow(idx)
        actions.append({
            "kind": "action",
            "label": f"Go to {label}",
            "sublabel": tooltip,
            "haystack": f"{label.lower()} {tooltip.lower()}",
            "run": _switch,
            "sort_key": (f"{i:02d}", label.lower()),
        })

    # Export action
    if hasattr(shell, "_on_export_requested"):
        actions.append({
            "kind": "action",
            "label": "Export POs",
            "sublabel": "Write per-vendor PO files",
            "haystack": "export excel vendor finalize po",
            "run": lambda: shell.sidebar.setCurrentRow(3),  # Review tab
            "sort_key": ("10", "export"),
        })

    return actions


class CommandPaletteDialog(QDialog):
    """Modal search dialog for keyboard-first navigation."""

    def __init__(self, shell, parent=None):
        super().__init__(parent or shell)
        self._shell = shell
        self._results: list[dict] = []
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(80)
        self._debounce_timer.timeout.connect(self._do_search)

        self.setWindowTitle("Command Palette")
        self.setFixedSize(520, 400)
        self.setStyleSheet(
            f"background-color: {t.BG_PANEL}; "
            f"color: {t.TEXT_SECONDARY}; "
            f"border: 1px solid {t.BORDER_ACCENT}; "
            f"border-radius: {t.RADIUS_MD}px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SPACE_MD, t.SPACE_MD, t.SPACE_MD, t.SPACE_MD)
        layout.setSpacing(t.SPACE_SM)

        # Search input
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type to search actions, items, vendors\u2026")
        self._input.setStyleSheet(
            f"background: {t.BG_INSET}; color: {t.TEXT_PRIMARY}; "
            f"border: 1px solid {t.BORDER_ACCENT}; border-radius: {t.RADIUS_SM}px; "
            f"padding: 8px; font-size: {t.FONT_MEDIUM}px;"
        )
        self._input.textChanged.connect(lambda: self._debounce_timer.start())
        layout.addWidget(self._input)

        # Results list
        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget {{ background: {t.BG_BASE}; border: 1px solid {t.BORDER}; "
            f"  border-radius: {t.RADIUS_SM}px; outline: none; }}"
            f"QListWidget::item {{ padding: 6px 10px; color: {t.TEXT_SECONDARY}; }}"
            f"QListWidget::item:selected {{ background: {t.FILL_PRIMARY_SOFT}; "
            f"  color: {t.TEXT_PRIMARY}; }}"
        )
        self._list.itemActivated.connect(self._on_activate)
        layout.addWidget(self._list, stretch=1)

        # Hint
        hint = QLabel("Enter to run \u00b7 \u2191\u2193 to navigate \u00b7 Esc to close")
        hint.setStyleSheet(
            f"color: {t.TEXT_DIM}; font-size: {t.FONT_MICRO}px; border: none;"
        )
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        # Build indexes
        self._action_index = _build_action_index(shell)
        model = getattr(shell.bulk_tab, "model", None) if shell.bulk_tab else None
        items = model.items if model else []
        self._item_index = build_item_index(items, self._jump_to_item)
        vendors = getattr(shell.controller, "vendor_codes_used", [])
        self._vendor_index = build_vendor_index(vendors, self._filter_to_vendor)

        # Initial population (empty query shows actions)
        self._do_search()
        self._input.setFocus()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._on_activate(self._list.currentItem())
        elif event.key() == Qt.Key_Down:
            row = self._list.currentRow()
            if row < self._list.count() - 1:
                self._list.setCurrentRow(row + 1)
        elif event.key() == Qt.Key_Up:
            row = self._list.currentRow()
            if row > 0:
                self._list.setCurrentRow(row - 1)
        else:
            super().keyPressEvent(event)

    def _do_search(self):
        query = self._input.text()
        self._results = rank_results(
            query,
            self._action_index,
            self._item_index,
            self._vendor_index,
        )
        self._list.clear()
        _KIND_COLORS = {
            "action": t.ACCENT_PRIMARY,
            "item": t.TEXT_SECONDARY,
            "vendor": t.ACCENT_OK,
        }
        for entry in self._results:
            kind = entry.get("kind", "")
            label = entry.get("label", "")
            sublabel = entry.get("sublabel", "")
            display = f"{label}  —  {sublabel}" if sublabel else label
            item = QListWidgetItem(display)
            color = _KIND_COLORS.get(kind, t.TEXT_SECONDARY)
            item.setForeground(QColor(color))
            self._list.addItem(item)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _on_activate(self, item):
        if item is None:
            return
        row = self._list.row(item)
        if 0 <= row < len(self._results):
            entry = self._results[row]
            run = entry.get("run")
            if callable(run):
                self.accept()
                run()

    def _jump_to_item(self, line_code: str, item_code: str):
        """Switch to bulk tab and scroll to item."""
        shell = self._shell
        if shell.bulk_tab:
            # Switch to Bulk tab
            from ui_qt.shell import NAV_ITEMS
            bulk_idx = next(
                (i for i, (label, _) in enumerate(NAV_ITEMS) if label == "Bulk"),
                None,
            )
            if bulk_idx is not None:
                shell.sidebar.setCurrentRow(bulk_idx)
            # Find and select the row
            model = shell.bulk_tab.model
            for row in range(model.rowCount()):
                item = model.item_at(row)
                if item and item.get("line_code") == line_code and item.get("item_code") == item_code:
                    vis_row = model.visible_row_for_source(row)
                    if vis_row >= 0:
                        vis_idx = model.index(vis_row, 0)
                        shell.bulk_tab.table.selectRow(vis_row)
                        shell.bulk_tab.table.scrollTo(vis_idx)
                    break

    def _filter_to_vendor(self, vendor: str):
        """Set the vendor worksheet filter on the bulk tab."""
        shell = self._shell
        if shell.bulk_tab:
            from ui_qt.shell import NAV_ITEMS
            bulk_idx = next(
                (i for i, (label, _) in enumerate(NAV_ITEMS) if label == "Bulk"),
                None,
            )
            if bulk_idx is not None:
                shell.sidebar.setCurrentRow(bulk_idx)
            shell.bulk_tab._vendor_ws_combo.setCurrentText(vendor)
