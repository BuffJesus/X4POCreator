"""Qt keyboard shortcut overlay — press ? on the bulk grid to show."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import theme as t

# Reuse the same data from the tkinter version
from ui_shortcut_overlay import SHORTCUT_GROUPS


class ShortcutOverlayDialog(QDialog):
    """Modal dialog showing all keyboard shortcuts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setFixedSize(520, 480)
        self.setStyleSheet(
            f"background-color: {t.BG_PANEL}; "
            f"color: {t.TEXT_SECONDARY};"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        layout.setSpacing(t.SPACE_MD)

        title = QLabel("Keyboard Shortcuts")
        title.setStyleSheet(
            f"color: {t.TEXT_PRIMARY}; font-size: {t.FONT_HEADING}px; "
            f"font-weight: bold;"
        )
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(t.SPACE_MD)

        for group_name, shortcuts in SHORTCUT_GROUPS:
            group_label = QLabel(group_name)
            group_label.setStyleSheet(
                f"color: {t.ACCENT_PRIMARY}; font-size: {t.FONT_LABEL}px; "
                f"font-weight: bold; padding-top: {t.SPACE_SM}px; "
                f"border-top: 1px solid {t.BORDER};"
            )
            content_layout.addWidget(group_label)

            for key, description in shortcuts:
                row = QHBoxLayout()
                row.setSpacing(t.SPACE_MD)

                key_label = QLabel(key)
                key_label.setFixedWidth(180)
                key_label.setStyleSheet(
                    f"color: {t.TEXT_PRIMARY}; font-size: {t.FONT_BODY}px; "
                    f"font-weight: bold; background: {t.BG_INSET}; "
                    f"border: 1px solid {t.BORDER}; border-radius: 3px; "
                    f"padding: 2px 6px;"
                )
                row.addWidget(key_label)

                desc_label = QLabel(description)
                desc_label.setStyleSheet(
                    f"color: {t.TEXT_MUTED}; font-size: {t.FONT_BODY}px;"
                )
                row.addWidget(desc_label, stretch=1)

                content_layout.addLayout(row)

        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, stretch=1)

        hint = QLabel("Press Escape to close")
        hint.setStyleSheet(
            f"color: {t.TEXT_DIM}; font-size: {t.FONT_MICRO}px;"
        )
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
