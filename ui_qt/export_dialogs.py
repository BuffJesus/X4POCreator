"""Qt export dialogs with the Tuner card grammar."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import theme as t
import theme_qt as tq


class ExportPreviewDialog(QDialog):
    """Review export scope before writing vendor PO files."""

    def __init__(self, preview_data: dict, *, initial_overrides: dict | None = None, parent=None):
        super().__init__(parent)
        self._preview_data = preview_data or {}
        self._overrides = dict(initial_overrides or {})
        self.setWindowTitle("Final Export Check")
        self.resize(820, 620)
        self.setStyleSheet(f"background-color: {t.BG_BASE}; color: {t.TEXT_SECONDARY};")

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        root.setSpacing(t.SPACE_MD)

        header = QLabel()
        header.setTextFormat(Qt.RichText)
        header.setText(tq.tab_header_html(
            "Final Export Check",
            "Review vendor scope before writing PO files",
        ))
        header.setStyleSheet(tq.tab_header_style())
        root.addWidget(header)

        summary = self._build_summary_cards()
        root.addWidget(summary)

        root.addWidget(self._build_guidance_panel())

        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Vendor", "Rows", "Est. Value", "Action"])
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionMode(QTableWidget.NoSelection)
        self._table.setFocusPolicy(Qt.NoFocus)
        self._table.setStyleSheet(
            f"QTableWidget {{ background: {t.BG_PANEL}; border: 1px solid {t.BORDER}; "
            f"border-radius: {t.RADIUS_MD}px; gridline-color: {t.BORDER_SOFT}; }}"
            f"QHeaderView::section {{ background: {t.BG_ELEVATED}; color: {t.TEXT_MUTED}; "
            f"border: none; border-bottom: 1px solid {t.BORDER}; "
            f"padding: {t.SPACE_SM}px; font-size: {t.FONT_SMALL}px; font-weight: bold; }}"
        )
        root.addWidget(self._table, stretch=1)

        footer = QHBoxLayout()
        footer.setSpacing(t.SPACE_SM)
        footer_label = QLabel(
            "Nothing is written until you continue. Leaving a vendor on Include uses the default export scope."
        )
        footer_label.setWordWrap(True)
        footer_label.setStyleSheet(f"color: {t.TEXT_DIM}; font-size: {t.FONT_SMALL}px;")
        footer.addWidget(footer_label, stretch=1)

        footer.addStretch(1)

        cancel_btn = QPushButton("Back")
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)

        export_btn = QPushButton("Continue to Export")
        export_btn.setStyleSheet(
            f"QPushButton {{ background: {t.ACCENT_PRIMARY}; color: {t.TEXT_INVERSE}; "
             f"border: none; border-radius: {t.RADIUS_SM}px; padding: 7px 18px; "
            f"font-weight: bold; }}"
            f"QPushButton:hover {{ background: {t.BORDER_ACCENT}; }}"
        )
        export_btn.clicked.connect(self.accept)
        footer.addWidget(export_btn)

        root.addLayout(footer)
        self._populate_table()

    @property
    def overrides(self) -> dict:
        return dict(self._overrides)

    def _build_summary_cards(self) -> QWidget:
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(t.SPACE_SM)
        layout.setVerticalSpacing(t.SPACE_SM)

        rows = list(self._preview_data.get("vendor_summaries", []) or [])
        vendor_count = len(rows)
        item_count = int(self._preview_data.get("total_item_count", 0) or 0)
        total_value = float(self._preview_data.get("total_estimated_value", 0.0) or 0.0)

        cards = [
            (f"{vendor_count:,}", "vendors", "Included Vendors", t.ACCENT_PRIMARY),
            (f"{item_count:,}", "items", "Queued Rows", t.ACCENT_OK),
            (f"${total_value:,.2f}", "", "Estimated Value", t.ACCENT_SPECIAL),
        ]
        for col, (value, units, title, accent) in enumerate(cards):
            label = QLabel()
            label.setTextFormat(Qt.RichText)
            label.setAlignment(Qt.AlignCenter)
            label.setMinimumHeight(74)
            label.setStyleSheet(tq.number_card_style(accent))
            label.setText(tq.number_card_html(
                value,
                units,
                title,
                accent,
                value_font_size=t.FONT_HEADING,
            ))
            layout.addWidget(label, 0, col)
        return widget

    def _build_guidance_panel(self) -> QFrame:
        panel = QFrame()
        panel.setStyleSheet(tq.card_style(t.ACCENT_PRIMARY))

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(t.SPACE_MD, t.SPACE_MD, t.SPACE_MD, t.SPACE_MD)
        layout.setSpacing(t.SPACE_XS)

        title = QLabel("Choose how each vendor should be handled")
        title.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: {t.FONT_BODY}px; font-weight: bold;")
        layout.addWidget(title)

        body = QLabel(
            "Include exports the vendor now. Defer keeps the vendor in this session for later. "
            "Skip leaves the vendor out of this export pass."
        )
        body.setWordWrap(True)
        body.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: {t.FONT_SMALL}px;")
        layout.addWidget(body)
        return panel

    def _populate_table(self):
        rows = list(self._preview_data.get("vendor_summaries", []) or [])
        self._table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            vendor = str(row.get("vendor", "") or "UNKNOWN")
            item_count = int(row.get("item_count", 0) or 0)
            est_value = float(row.get("estimated_value", 0.0) or 0.0)

            values = [
                vendor,
                f"{item_count:,}",
                f"${est_value:,.2f}",
            ]
            for col_idx, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                if col_idx == 0:
                    cell.setForeground(Qt.GlobalColor.white)
                    cell.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                elif col_idx == 1:
                    cell.setTextAlignment(Qt.AlignCenter)
                else:
                    cell.setTextAlignment(Qt.AlignVCenter | Qt.AlignRight)
                self._table.setItem(row_idx, col_idx, cell)

            combo = QComboBox()
            combo.addItem("Include now", "include")
            combo.addItem("Defer for later", "defer")
            combo.addItem("Skip this pass", "skip")
            current = self._overrides.get(vendor, "include")
            for idx in range(combo.count()):
                if combo.itemData(idx) == current:
                    combo.setCurrentIndex(idx)
                    break
            combo.setStyleSheet(
                f"QComboBox {{ background: {t.BG_INSET}; border: 1px solid {t.BORDER_ACCENT}; "
                f"border-radius: {t.RADIUS_SM}px; padding: 4px 8px; min-width: 150px; }}"
            )
            combo.currentIndexChanged.connect(
                lambda _idx, vendor_code=vendor, box=combo: self._set_override(vendor_code, box.currentData())
            )
            self._table.setCellWidget(row_idx, 3, combo)

        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setStretchLastSection(True)

    def _set_override(self, vendor: str, mode: str):
        normalized = str(mode or "include").strip() or "include"
        if normalized == "include":
            self._overrides.pop(vendor, None)
        else:
            self._overrides[vendor] = normalized
