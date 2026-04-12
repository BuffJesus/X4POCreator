"""Tests for ui_qt.dialogs — ItemDetailsDialog and BuyRuleEditorDialog."""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from PySide6.QtWidgets import QApplication
    HAS_QT = True
except ImportError:
    HAS_QT = False


def _item(**kw):
    d = {
        "line_code": "A", "item_code": "001", "description": "Test Widget",
        "vendor": "VND", "status": "OK", "qty_sold": 100, "qty_suspended": 0,
        "pack_size": 12, "order_qty": 24, "raw_need": 20, "suggested_qty": 24,
        "final_qty": 24, "why": "Low stock", "notes": "Test note",
        "order_policy": "pack_round", "pack_size_source": "x4_exact",
        "qty_on_po": 0, "inventory_position": 5, "target_stock": 30,
        "demand_signal": 20,
    }
    d.update(kw)
    return d


@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestItemDetailsDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_construct(self):
        from ui_qt.dialogs import ItemDetailsDialog
        item = _item()
        dialog = ItemDetailsDialog(item)
        self.assertIn("A", dialog.windowTitle())
        self.assertIn("001", dialog.windowTitle())

    def test_with_inventory(self):
        from ui_qt.dialogs import ItemDetailsDialog
        item = _item()
        inv = {"qoh": 5, "min": 10, "max": 30, "supplier": "ACME"}
        dialog = ItemDetailsDialog(item, inv)
        self.assertIsNotNone(dialog)

    def test_empty_item(self):
        from ui_qt.dialogs import ItemDetailsDialog
        dialog = ItemDetailsDialog({
            "line_code": "", "item_code": "", "description": "",
        })
        self.assertIsNotNone(dialog)


@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestBuyRuleEditorDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_construct_empty_rule(self):
        from ui_qt.dialogs import BuyRuleEditorDialog
        dialog = BuyRuleEditorDialog(_item())
        self.assertEqual(dialog._pack_spin.value(), 0)
        self.assertEqual(dialog._trigger_spin.value(), 0)

    def test_construct_with_rule(self):
        from ui_qt.dialogs import BuyRuleEditorDialog
        rule = {"pack_size": 24, "minimum_packs_on_hand": 2, "cover_days": 30}
        dialog = BuyRuleEditorDialog(_item(), rule)
        self.assertEqual(dialog._pack_spin.value(), 24)
        self.assertEqual(dialog._min_packs_spin.value(), 2)
        self.assertEqual(dialog._cover_spin.value(), 30)

    def test_save_produces_rule(self):
        from ui_qt.dialogs import BuyRuleEditorDialog
        dialog = BuyRuleEditorDialog(_item())
        dialog._pack_spin.setValue(12)
        dialog._trigger_spin.setValue(5)
        dialog._on_save()
        rule = dialog.accepted_rule
        self.assertIsNotNone(rule)
        self.assertEqual(rule["pack_size"], 12)
        self.assertEqual(rule["reorder_trigger_qty"], 5)

    def test_clear_produces_empty(self):
        from ui_qt.dialogs import BuyRuleEditorDialog
        dialog = BuyRuleEditorDialog(_item(), {"pack_size": 24})
        dialog._on_clear()
        self.assertEqual(dialog.accepted_rule, {})

    def test_save_with_exact_qty(self):
        from ui_qt.dialogs import BuyRuleEditorDialog
        dialog = BuyRuleEditorDialog(_item())
        dialog._exact_edit.setText("50")
        dialog._on_save()
        self.assertEqual(dialog.accepted_rule["exact_order_qty"], 50)

    def test_zero_values_omitted(self):
        from ui_qt.dialogs import BuyRuleEditorDialog
        dialog = BuyRuleEditorDialog(_item())
        # All spinboxes at 0 (default) → empty rule
        dialog._on_save()
        self.assertEqual(dialog.accepted_rule, {})


@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestRemoveNotNeededSignal(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_signal_emits(self):
        from ui_qt.bulk_tab import BulkTab
        tab = BulkTab()
        signals = []
        tab.remove_not_needed.connect(lambda: signals.append(True))
        tab._on_remove_not_needed()
        self.assertEqual(len(signals), 1)

    def test_ignore_signal_emits(self):
        from ui_qt.bulk_tab import BulkTab
        tab = BulkTab()
        signals = []
        tab.ignore_item.connect(lambda lc, ic: signals.append((lc, ic)))
        tab._ctx_ignore_item({"line_code": "A", "item_code": "001"})
        self.assertEqual(signals, [("A", "001")])


if __name__ == "__main__":
    unittest.main()
