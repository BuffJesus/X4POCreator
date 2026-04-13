"""Tests for ui_qt.workflow_dialogs — all workflow dialog classes."""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from PySide6.QtWidgets import QApplication
    HAS_QT = True
except ImportError:
    HAS_QT = False


def _candidate(**kw):
    d = {
        "line_code": "A", "item_code": "001", "description": "Widget",
        "final_qty": 12, "qoh": 5, "max": 30, "sug_max": 25,
        "reason": "Inventory covers demand", "auto_remove": True,
    }
    d.update(kw)
    return d


def _flagged(**kw):
    d = {
        "item": {"line_code": "A", "item_code": "001",
                 "description": "Widget", "order_qty": 10, "final_qty": 10},
        "qoh": 5, "pack_size": 6, "min": 10, "max": 30, "sug_max": 25,
        "reasons": ["Inventory covers demand"],
    }
    d.update(kw)
    return d


# ── RemoveNotNeededDialog ──────────────────────────────────────────

@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestRemoveNotNeededDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_construct_empty(self):
        from ui_qt.workflow_dialogs import RemoveNotNeededDialog
        dialog = RemoveNotNeededDialog([])
        self.assertEqual(dialog.removed_indices, [])

    def test_construct_with_candidates(self):
        from ui_qt.workflow_dialogs import RemoveNotNeededDialog
        cands = [_candidate(), _candidate(item_code="002", auto_remove=False)]
        dialog = RemoveNotNeededDialog(cands, excluded_assigned_count=3)
        self.assertIsNotNone(dialog)
        self.assertEqual(dialog._table.rowCount(), 2)

    def test_auto_check_state(self):
        from ui_qt.workflow_dialogs import RemoveNotNeededDialog
        from PySide6.QtCore import Qt
        cands = [_candidate(auto_remove=True), _candidate(auto_remove=False)]
        dialog = RemoveNotNeededDialog(cands)
        self.assertEqual(dialog._table.item(0, 0).checkState(), Qt.Checked)
        self.assertEqual(dialog._table.item(1, 0).checkState(), Qt.Unchecked)

    def test_select_all_deselect_all(self):
        from ui_qt.workflow_dialogs import RemoveNotNeededDialog
        from PySide6.QtCore import Qt
        cands = [_candidate(auto_remove=False), _candidate(auto_remove=False)]
        dialog = RemoveNotNeededDialog(cands)
        dialog._set_all(True)
        self.assertTrue(all(
            dialog._table.item(r, 0).checkState() == Qt.Checked
            for r in range(dialog._table.rowCount())
        ))
        dialog._set_all(False)
        self.assertTrue(all(
            dialog._table.item(r, 0).checkState() == Qt.Unchecked
            for r in range(dialog._table.rowCount())
        ))


# ── StockWarningsDialog ───────────────────────────────────────────

@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestStockWarningsDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_construct_empty(self):
        from ui_qt.workflow_dialogs import StockWarningsDialog
        dialog = StockWarningsDialog([])
        self.assertFalse(dialog.proceed)

    def test_construct_with_flagged(self):
        from ui_qt.workflow_dialogs import StockWarningsDialog
        flagged = [_flagged(), _flagged(item={"line_code": "B", "item_code": "002",
                                               "description": "Gear", "order_qty": 5})]
        dialog = StockWarningsDialog(flagged)
        self.assertEqual(len(dialog._checks), 2)
        self.assertTrue(all(cb.isChecked() for cb in dialog._checks))

    def test_uncheck_returns_unassign(self):
        from ui_qt.workflow_dialogs import StockWarningsDialog
        flagged = [_flagged()]
        dialog = StockWarningsDialog(flagged)
        dialog._checks[0].setChecked(False)
        self.assertEqual(len(dialog.items_to_unassign), 1)


# ── TooManyFlaggedDialog ─────────────────────────────────────────

@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestTooManyFlaggedDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_construct(self):
        from ui_qt.workflow_dialogs import TooManyFlaggedDialog
        dialog = TooManyFlaggedDialog(150)
        self.assertFalse(dialog.proceed)


# ── VendorReviewDialog ───────────────────────────────────────────

@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestVendorReviewDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_construct_empty(self):
        from ui_qt.workflow_dialogs import VendorReviewDialog
        dialog = VendorReviewDialog([])
        self.assertIsNotNone(dialog)

    def test_construct_with_summaries(self):
        from ui_qt.workflow_dialogs import VendorReviewDialog
        summaries = [
            {"vendor_code": "ABC", "order_count": 5, "total_qty_ordered": 100,
             "total_qty_received": 80, "last_session_date": "2026-04-01T12:00:00",
             "inferred_lead_days": 7,
             "top_items": [{"line_code": "A", "item_code": "001",
                            "description": "Widget", "qty": 50}]},
        ]
        dialog = VendorReviewDialog(summaries, focus_vendor="ABC")
        self.assertIsNotNone(dialog)


# ── SessionDiffDialog ────────────────────────────────────────────

@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestSessionDiffDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_construct_empty(self):
        from ui_qt.workflow_dialogs import SessionDiffDialog
        dialog = SessionDiffDialog({}, summary_text="No changes")
        self.assertIsNotNone(dialog)

    def test_construct_with_diff(self):
        from ui_qt.workflow_dialogs import SessionDiffDialog
        diff = {
            "new_items": [{"line_code": "A", "item_code": "001",
                           "description": "New", "qty": 10, "vendor": "V"}],
            "removed_items": [],
            "qty_increased": [],
            "qty_decreased": [],
            "vendor_changed": [],
        }
        dialog = SessionDiffDialog(diff, summary_text="1 new item",
                                    snapshot_label="2026-04-01")
        self.assertIsNotNone(dialog)


# ── SupplierMapDialog ────────────────────────────────────────────

@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestSupplierMapDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_construct_empty(self):
        from ui_qt.workflow_dialogs import SupplierMapDialog
        dialog = SupplierMapDialog({})
        self.assertEqual(dialog.working_mapping, {})

    def test_construct_with_mapping(self):
        from ui_qt.workflow_dialogs import SupplierMapDialog
        dialog = SupplierMapDialog({"ACME": "ACM", "BETA": "BET"})
        self.assertEqual(len(dialog.working_mapping), 2)

    def test_add_entry(self):
        from ui_qt.workflow_dialogs import SupplierMapDialog
        dialog = SupplierMapDialog({})
        dialog._supplier_edit.setText("ACME")
        dialog._vendor_edit.setText("ACM")
        dialog._add_or_update()
        self.assertEqual(dialog.working_mapping, {"ACME": "ACM"})


# ── QohReviewDialog ──────────────────────────────────────────────

@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestQohReviewDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_construct_empty(self):
        from ui_qt.workflow_dialogs import QohReviewDialog
        dialog = QohReviewDialog([])
        self.assertEqual(dialog.reverted_keys, [])

    def test_construct_with_rows(self):
        from ui_qt.workflow_dialogs import QohReviewDialog
        rows = [{"line_code": "A", "item_code": "001", "description": "X",
                 "old_qoh": 10, "new_qoh": 15, "delta": 5}]
        dialog = QohReviewDialog(rows)
        self.assertIsNotNone(dialog)


# ── SkipActionsDialog ────────────────────────────────────────────

@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestSkipActionsDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_construct_empty(self):
        from ui_qt.workflow_dialogs import SkipActionsDialog
        dialog = SkipActionsDialog([], [])
        self.assertIsNotNone(dialog)

    def test_construct_with_data(self):
        from ui_qt.workflow_dialogs import SkipActionsDialog
        items = [{"line_code": "A", "item_code": "001", "status": "skip"}]
        clusters = [{"line_code": "A", "count": 1}]
        dialog = SkipActionsDialog(items, clusters)
        self.assertIsNotNone(dialog)


# ── BulkRuleEditDialog ───────────────────────────────────────────

@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestBulkRuleEditDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_construct(self):
        from ui_qt.workflow_dialogs import BulkRuleEditDialog
        dialog = BulkRuleEditDialog(5)
        self.assertIsNone(dialog.changes)

    def test_apply_returns_changes(self):
        from ui_qt.workflow_dialogs import BulkRuleEditDialog
        dialog = BulkRuleEditDialog(3)
        dialog._policy_combo.setCurrentText("standard")
        dialog._pack_edit.setText("12")
        dialog._on_apply()
        self.assertIsNotNone(dialog.changes)
        self.assertEqual(dialog.changes["order_policy"], "standard")
        self.assertEqual(dialog.changes["pack_size"], "12")


# ── IgnoredItemsDialog ───────────────────────────────────────────

@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestIgnoredItemsDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_construct_empty(self):
        from ui_qt.workflow_dialogs import IgnoredItemsDialog
        dialog = IgnoredItemsDialog([])
        self.assertEqual(dialog.keys_to_remove, set())

    def test_construct_with_keys(self):
        from ui_qt.workflow_dialogs import IgnoredItemsDialog
        dialog = IgnoredItemsDialog(["A:001", "B:002"])
        self.assertIsNotNone(dialog)

    def test_filter(self):
        from ui_qt.workflow_dialogs import IgnoredItemsDialog
        dialog = IgnoredItemsDialog(["A:001", "B:002", "A:003"])
        dialog._filter_edit.setText("B")
        visible = dialog._visible_keys()
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0], "B:002")


# ── VendorPolicyDialog ───────────────────────────────────────────

@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestVendorPolicyDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_construct_defaults(self):
        from ui_qt.workflow_dialogs import VendorPolicyDialog
        dialog = VendorPolicyDialog("ABC", {})
        self.assertIsNone(dialog.saved_result)

    def test_construct_with_policy(self):
        from ui_qt.workflow_dialogs import VendorPolicyDialog
        policy = {
            "shipping_policy": "hold_for_threshold",
            "free_freight_threshold": 500,
            "preferred_free_ship_weekdays": ["Tuesday"],
        }
        dialog = VendorPolicyDialog("ABC", policy, inferred_lead_days=5)
        self.assertIsNotNone(dialog)

    def test_clear(self):
        from ui_qt.workflow_dialogs import VendorPolicyDialog
        dialog = VendorPolicyDialog("ABC", {"shipping_policy": "hold_for_threshold"})
        dialog._on_clear()
        self.assertEqual(dialog._policy_combo.currentText(), "release_immediately")


# ── VendorManagerDialog ──────────────────────────────────────────

@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestVendorManagerDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_construct(self):
        from ui_qt.workflow_dialogs import VendorManagerDialog
        dialog = VendorManagerDialog(["ABC", "DEF"])
        self.assertEqual(dialog.current_vendors, ["ABC", "DEF"])
        self.assertEqual(dialog.changes, [])


# ── SessionHistoryDialog ─────────────────────────────────────────

@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestSessionHistoryDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_construct_empty(self):
        from ui_qt.workflow_dialogs import SessionHistoryDialog
        dialog = SessionHistoryDialog([])
        self.assertIsNotNone(dialog)

    def test_construct_with_snapshots(self):
        from ui_qt.workflow_dialogs import SessionHistoryDialog
        snapshots = [{
            "created_at": "2026-04-01T12:00:00",
            "export_scope_label": "all",
            "assigned_items": [
                {"line_code": "A", "item_code": "001", "description": "W",
                 "vendor": "V", "suggested_qty": 10, "final_qty": 12},
            ],
        }]
        dialog = SessionHistoryDialog(snapshots)
        self.assertIsNotNone(dialog)


if __name__ == "__main__":
    unittest.main()
