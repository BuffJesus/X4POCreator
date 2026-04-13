"""Settings dialog for PO Builder preferences."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

import theme as t
import theme_qt as tq


class SettingsDialog(QDialog):
    """Modal dialog for editing app settings."""

    def __init__(self, app_settings: dict, *, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)
        self.setStyleSheet(
            f"background-color: {t.BG_PANEL}; color: {t.TEXT_SECONDARY};"
        )
        self._settings = app_settings
        self._changed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        layout.setSpacing(t.SPACE_MD)

        title = QLabel("Settings")
        title.setStyleSheet(
            f"color: {t.TEXT_PRIMARY}; font-size: {t.FONT_HEADING}px; font-weight: bold;"
        )
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(t.SPACE_SM)
        form.setContentsMargins(0, 0, 0, 0)

        # Update check
        self._chk_updates = QCheckBox("Check for updates on startup")
        self._chk_updates.setChecked(
            bool(app_settings.get("check_for_updates_on_startup", True))
        )
        self._chk_updates.setStyleSheet(f"color: {t.TEXT_PRIMARY};")
        form.addRow("", self._chk_updates)

        # Mixed export behavior
        self._export_combo = QComboBox()
        self._export_combo.addItems([
            "all_exportable",
            "immediate_only",
            "ask_when_mixed",
        ])
        current = str(app_settings.get("mixed_export_behavior", "all_exportable") or "")
        idx = self._export_combo.findText(current)
        if idx >= 0:
            self._export_combo.setCurrentIndex(idx)
        self._export_combo.setStyleSheet(
            f"background: {t.BG_INSET}; color: {t.TEXT_PRIMARY}; "
            f"border: 1px solid {t.BORDER}; padding: 2px 6px;"
        )
        form.addRow(self._make_label("Mixed export behavior"), self._export_combo)

        # Shared data folder
        shared_row = QHBoxLayout()
        self._shared_edit = QLineEdit(
            str(app_settings.get("shared_data_dir", "") or "")
        )
        self._shared_edit.setPlaceholderText("(local data — no shared folder)")
        self._shared_edit.setStyleSheet(
            f"background: {t.BG_INSET}; color: {t.TEXT_PRIMARY}; "
            f"border: 1px solid {t.BORDER}; border-radius: 3px; padding: 2px 6px;"
        )
        shared_row.addWidget(self._shared_edit, stretch=1)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_shared)
        shared_row.addWidget(browse_btn)
        form.addRow(self._make_label("Shared data folder"), shared_row)

        # Scan folder
        scan_row = QHBoxLayout()
        self._scan_edit = QLineEdit(
            str(app_settings.get("last_scan_folder", "") or "")
        )
        self._scan_edit.setPlaceholderText("(no default scan folder)")
        self._scan_edit.setStyleSheet(
            f"background: {t.BG_INSET}; color: {t.TEXT_PRIMARY}; "
            f"border: 1px solid {t.BORDER}; border-radius: 3px; padding: 2px 6px;"
        )
        scan_row.addWidget(self._scan_edit, stretch=1)
        scan_browse = QPushButton("Browse")
        scan_browse.clicked.connect(self._browse_scan)
        scan_row.addWidget(scan_browse)
        form.addRow(self._make_label("Default scan folder"), scan_row)

        layout.addLayout(form)
        layout.addStretch(1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(
            f"QPushButton {{ background: {t.ACCENT_PRIMARY}; color: {t.TEXT_INVERSE}; "
            f"border: none; border-radius: {t.RADIUS_SM}px; padding: 6px 20px; "
            f"font-weight: bold; }}"
            f"QPushButton:hover {{ background: {t.ACCENT_OK}; }}"
        )
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: {t.FONT_SMALL}px;")
        return lbl

    def _browse_shared(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Shared Data Folder",
            self._shared_edit.text(),
        )
        if path:
            self._shared_edit.setText(path)

    def _browse_scan(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Default Scan Folder",
            self._scan_edit.text(),
        )
        if path:
            self._scan_edit.setText(path)

    def _save(self):
        self._settings["check_for_updates_on_startup"] = self._chk_updates.isChecked()
        self._settings["mixed_export_behavior"] = self._export_combo.currentText()
        self._settings["shared_data_dir"] = self._shared_edit.text().strip()
        self._settings["last_scan_folder"] = self._scan_edit.text().strip()
        self._changed = True
        self.accept()

    @property
    def changed(self) -> bool:
        return self._changed
