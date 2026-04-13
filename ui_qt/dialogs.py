"""Qt dialogs for the bulk grid — item details and buy rule editor.

These are modal QDialogs opened from the bulk grid's context menu
or keyboard shortcuts.  They read/write item dicts and order_rules
via the session controller.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

import theme as t
import theme_qt as tq


# ─── Item Details dialog ──────────────────────────────────────────────────

class ItemDetailsDialog(QDialog):
    """Read-only item details view."""

    def __init__(self, item: dict, inventory: dict | None = None,
                 order_rule: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(
            f"Item Details — {item.get('line_code', '')}{item.get('item_code', '')}"
        )
        self.setMinimumWidth(500)
        self.setStyleSheet(
            f"background-color: {t.BG_PANEL}; color: {t.TEXT_SECONDARY};"
        )

        inv = inventory or {}
        rule = order_rule or {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        layout.setSpacing(t.SPACE_MD)

        # Title
        title = QLabel(
            f"{item.get('line_code', '')} {item.get('item_code', '')} — "
            f"{item.get('description', '')}"
        )
        title.setStyleSheet(
            f"color: {t.TEXT_PRIMARY}; font-size: {t.FONT_LABEL}px; font-weight: bold;"
        )
        title.setWordWrap(True)
        layout.addWidget(title)

        # Sections
        self._add_section(layout, "Order", [
            ("Vendor", item.get("vendor", "")),
            ("Status", item.get("status", "")),
            ("Raw Need", item.get("raw_need", 0)),
            ("Suggested Qty", item.get("suggested_qty", 0)),
            ("Final Qty", item.get("final_qty", item.get("order_qty", 0))),
            ("Pack Size", item.get("pack_size", "")),
            ("Pack Source", item.get("pack_size_source", "")),
            ("Order Policy", item.get("order_policy", "")),
        ])

        self._add_section(layout, "Inventory", [
            ("QOH", inv.get("qoh", "")),
            ("Min", inv.get("min", "")),
            ("Max", inv.get("max", "")),
            ("Supplier", inv.get("supplier", "")),
            ("Qty on PO", item.get("qty_on_po", 0)),
            ("Inventory Position", item.get("inventory_position", "")),
            ("Target Stock", item.get("target_stock", "")),
        ])

        self._add_section(layout, "Demand", [
            ("Qty Sold", item.get("qty_sold", 0)),
            ("Qty Suspended", item.get("qty_suspended", 0)),
            ("Demand Signal", item.get("demand_signal", 0)),
            ("Source", "Sales" if item.get("qty_sold", 0) > 0 else "Susp"),
            ("Annualized Demand", f"{item.get('annualized_demand', 0):.1f}"
             if item.get("annualized_demand") else ""),
        ])

        # Activity & Risk
        repl_cost = item.get("repl_cost") or inv.get("repl_cost")
        cost_display = f"${repl_cost:,.2f}" if isinstance(repl_cost, (int, float)) and repl_cost else ""
        risk = item.get("stockout_risk_score")
        risk_display = f"{int(round(risk * 100))}%" if isinstance(risk, float) else ""
        activity_fields = [
            ("Unit Cost", cost_display),
            ("Last Sale", inv.get("last_sale", "")),
            ("Last Receipt", inv.get("last_receipt", "")),
            ("Days Since Last Sale", item.get("days_since_last_sale", "")),
            ("Stockout Risk", risk_display),
            ("Dead Stock", item.get("dead_stock", "")),
            ("Recency Confidence", item.get("recency_confidence", "")),
        ]
        # Receipt history fields (stamped during enrichment)
        if item.get("receipt_primary_vendor"):
            receipt_vendor = item.get("receipt_primary_vendor", "")
            assigned_vendor = str(item.get("vendor", "") or "").strip().upper()
            confidence = item.get("receipt_vendor_confidence", "")
            activity_fields.append(("Receipt Primary Vendor", receipt_vendor))
            activity_fields.append(("Vendor Confidence", confidence))
            if (assigned_vendor and receipt_vendor
                    and assigned_vendor != str(receipt_vendor).strip().upper()
                    and confidence not in ("", "none", "low")):
                activity_fields.append(("VENDOR MISMATCH",
                    f"Assigned {assigned_vendor} but receipts suggest {receipt_vendor}"))
        if item.get("receipt_pack_candidate"):
            activity_fields.append(("Receipt Pack Candidate", item.get("receipt_pack_candidate", "")))
            activity_fields.append(("Receipt Pack Confidence", item.get("receipt_pack_confidence", "")))
        if item.get("target_basis"):
            activity_fields.append(("Target Basis", item.get("target_basis", "")))
        if item.get("deferred_pack_overshoot"):
            activity_fields.append(("Deferred", "Pack overshoot — stock comfortable"))
        self._add_section(layout, "Activity & Risk", activity_fields)

        self._add_section(layout, "Why", [
            ("Why This Qty", item.get("why", "")),
        ])

        if item.get("notes"):
            self._add_section(layout, "Notes", [
                ("Notes", item.get("notes", "")),
            ])

        # Close button
        footer = QHBoxLayout()
        footer.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(30)
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        layout.addLayout(footer)

    def _add_section(self, parent_layout, title, fields):
        card = QFrame()
        card.setStyleSheet(tq.card_style())
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(t.SPACE_SM, t.SPACE_SM, t.SPACE_SM, t.SPACE_SM)
        card_layout.setSpacing(2)

        header = QLabel(title)
        header.setStyleSheet(
            f"color: {t.ACCENT_PRIMARY}; font-size: {t.FONT_BODY}px; font-weight: bold;"
        )
        card_layout.addWidget(header)

        form = QFormLayout()
        form.setSpacing(2)
        form.setContentsMargins(0, 0, 0, 0)
        for label, value in fields:
            val_label = QLabel(str(value) if value not in (None, "") else "\u2014")
            val_label.setStyleSheet(f"color: {t.TEXT_PRIMARY};")
            val_label.setWordWrap(True)
            name_label = QLabel(label)
            name_label.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: {t.FONT_SMALL}px;")
            form.addRow(name_label, val_label)
        card_layout.addLayout(form)
        parent_layout.addWidget(card)


# ─── Buy Rule Editor dialog ──────────────────────────────────────────────

class BuyRuleEditorDialog(QDialog):
    """Edit buy rules for an item (pack size, min packs, trigger, cover days)."""

    def __init__(self, item: dict, rule: dict | None = None, parent=None):
        super().__init__(parent)
        self._item = item
        self._rule = dict(rule) if rule else {}
        self._accepted_rule = None

        lc = item.get("line_code", "")
        ic = item.get("item_code", "")
        self.setWindowTitle(f"Buy Rule — {lc}:{ic}")
        self.setMinimumWidth(400)
        self.setStyleSheet(
            f"background-color: {t.BG_PANEL}; color: {t.TEXT_SECONDARY};"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        layout.setSpacing(t.SPACE_MD)

        title = QLabel(f"{lc} {ic} — {item.get('description', '')}")
        title.setStyleSheet(
            f"color: {t.TEXT_PRIMARY}; font-size: {t.FONT_LABEL}px; font-weight: bold;"
        )
        title.setWordWrap(True)
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(t.SPACE_SM)

        # Pack size
        self._pack_spin = QSpinBox()
        self._pack_spin.setRange(0, 99999)
        self._pack_spin.setSpecialValueText("Auto")
        self._pack_spin.setValue(int(self._rule.get("pack_size") or 0))
        form.addRow("Pack Size:", self._pack_spin)

        # Minimum packs on hand
        self._min_packs_spin = QSpinBox()
        self._min_packs_spin.setRange(0, 999)
        self._min_packs_spin.setSpecialValueText("None")
        self._min_packs_spin.setValue(int(self._rule.get("minimum_packs_on_hand") or 0))
        form.addRow("Min Packs on Hand:", self._min_packs_spin)

        # Reorder trigger qty
        self._trigger_spin = QSpinBox()
        self._trigger_spin.setRange(0, 99999)
        self._trigger_spin.setSpecialValueText("Auto")
        self._trigger_spin.setValue(int(self._rule.get("reorder_trigger_qty") or 0))
        form.addRow("Reorder Trigger Qty:", self._trigger_spin)

        # Cover days
        self._cover_spin = QSpinBox()
        self._cover_spin.setRange(0, 365)
        self._cover_spin.setSpecialValueText("Default")
        self._cover_spin.setValue(int(self._rule.get("cover_days") or 0))
        form.addRow("Cover Days:", self._cover_spin)

        # Exact qty override
        self._exact_edit = QLineEdit()
        self._exact_edit.setPlaceholderText("Leave blank for auto")
        exact = self._rule.get("exact_order_qty")
        if exact not in (None, "", 0):
            self._exact_edit.setText(str(exact))
        form.addRow("Exact Order Qty:", self._exact_edit)

        layout.addLayout(form)

        # Buttons
        footer = QHBoxLayout()
        footer.addStretch(1)

        clear_btn = QPushButton("Clear Rule")
        clear_btn.clicked.connect(self._on_clear)
        footer.addWidget(clear_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(
            f"background: {t.ACCENT_PRIMARY}; color: {t.TEXT_INVERSE}; "
            f"border: none; border-radius: {t.RADIUS_SM}px; "
            f"font-weight: bold; padding: 6px 18px;"
        )
        save_btn.clicked.connect(self._on_save)
        footer.addWidget(save_btn)

        layout.addLayout(footer)

    @property
    def accepted_rule(self) -> dict | None:
        """Return the rule dict if saved, or None if cancelled/cleared."""
        return self._accepted_rule

    def _on_save(self):
        rule = {}
        if self._pack_spin.value() > 0:
            rule["pack_size"] = self._pack_spin.value()
        if self._min_packs_spin.value() > 0:
            rule["minimum_packs_on_hand"] = self._min_packs_spin.value()
        if self._trigger_spin.value() > 0:
            rule["reorder_trigger_qty"] = self._trigger_spin.value()
        if self._cover_spin.value() > 0:
            rule["cover_days"] = self._cover_spin.value()
        exact_text = self._exact_edit.text().strip()
        if exact_text:
            try:
                rule["exact_order_qty"] = int(float(exact_text))
            except ValueError:
                pass
        self._accepted_rule = rule
        self.accept()

    def _on_clear(self):
        self._accepted_rule = {}
        self.accept()
