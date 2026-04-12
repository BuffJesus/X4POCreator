"""Styled item delegate for the bulk grid QTableView.

Responsibilities:
- Row background tinting by zone (assigned/review/warning/skip)
- Right-aligned numeric columns
- Combo editor for vendor column
- Appropriate editors for qty / pack / min / max / notes columns
- Explicit editor styling so text is visible against the dark grid
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QModelIndex
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QLineEdit,
    QSpinBox,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

import theme as t
from ui_qt.bulk_model import COLUMNS, EDITABLE_COLS, ROW_TINT_ROLE, COL_INDEX

# Explicit editor stylesheet — ensures text is always visible against
# the dark grid background, even when the cell has a row tint or the
# system palette overrides the app stylesheet on Windows.
_EDITOR_STYLE = (
    f"background-color: {t.BG_ELEVATED}; "
    f"color: {t.TEXT_PRIMARY}; "
    f"border: 2px solid {t.ACCENT_PRIMARY}; "
    f"border-radius: 2px; "
    f"padding: 2px 4px; "
    f"font-size: {t.FONT_BODY}px; "
    f"selection-background-color: {t.FILL_PRIMARY_SOFT}; "
    f"selection-color: {t.TEXT_PRIMARY};"
)


class BulkDelegate(QStyledItemDelegate):
    """Custom delegate for bulk grid cells.

    Paint: applies row tint from the model's ROW_TINT_ROLE.
    Editor: creates appropriate input widgets for editable columns.
    """

    def __init__(self, known_vendors_fn=None, parent=None):
        super().__init__(parent)
        self._known_vendors_fn = known_vendors_fn or (lambda: [])

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        tint = index.data(ROW_TINT_ROLE)
        if tint:
            painter.save()
            painter.fillRect(option.rect, QColor(tint))
            painter.restore()
        super().paint(painter, option, index)

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> QWidget | None:
        col = index.column()
        if col < 0 or col >= len(COLUMNS):
            return None
        col_name = COLUMNS[col]
        if col_name not in EDITABLE_COLS:
            return None

        if col_name == "vendor":
            combo = QComboBox(parent)
            combo.setEditable(True)
            combo.addItems(self._known_vendors_fn())
            combo.setInsertPolicy(QComboBox.NoInsert)
            combo.setStyleSheet(_EDITOR_STYLE)
            combo.lineEdit().setStyleSheet(_EDITOR_STYLE)
            return combo

        if col_name == "notes":
            editor = QLineEdit(parent)
            editor.setPlaceholderText("Notes…")
            editor.setStyleSheet(_EDITOR_STYLE)
            return editor

        if col_name in ("final_qty", "qoh", "cur_min", "cur_max", "pack_size"):
            spin = QSpinBox(parent)
            spin.setMinimum(0)
            spin.setMaximum(999999)
            spin.setSpecialValueText("")
            spin.setStyleSheet(_EDITOR_STYLE)
            return spin

        return super().createEditor(parent, option, index)

    def setEditorData(self, editor: QWidget, index: QModelIndex):
        value = index.data(Qt.EditRole) or ""
        if isinstance(editor, QComboBox):
            editor.setCurrentText(str(value))
        elif isinstance(editor, QSpinBox):
            try:
                editor.setValue(int(float(value)) if value else 0)
            except (ValueError, TypeError):
                editor.setValue(0)
        elif isinstance(editor, QLineEdit):
            editor.setText(str(value))
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor: QWidget, model, index: QModelIndex):
        if isinstance(editor, QComboBox):
            model.setData(index, editor.currentText().strip().upper(), Qt.EditRole)
        elif isinstance(editor, QSpinBox):
            model.setData(index, str(editor.value()), Qt.EditRole)
        elif isinstance(editor, QLineEdit):
            model.setData(index, editor.text(), Qt.EditRole)
        else:
            super().setModelData(editor, model, index)
