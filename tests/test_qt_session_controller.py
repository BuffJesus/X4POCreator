"""Tests for ui_qt.session_controller — QtSessionController."""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    HAS_QT = True
except ImportError:
    HAS_QT = False


def _make_item(lc="A", ic="001", desc="Widget", vendor="", status="", qty_sold=10, **extra):
    item = {
        "line_code": lc, "item_code": ic, "description": desc,
        "vendor": vendor, "status": status, "qty_sold": qty_sold,
        "qty_suspended": 0, "pack_size": None, "order_qty": 0,
        "raw_need": 0, "suggested_qty": 0, "final_qty": 0,
        "why": "", "notes": "", "order_policy": "",
    }
    item.update(extra)
    return item


@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestQtSessionController(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_init(self):
        from ui_qt.session_controller import QtSessionController
        ctrl = QtSessionController()
        self.assertIsNotNone(ctrl.session)
        self.assertIsInstance(ctrl.vendor_codes_used, list)
        self.assertIsInstance(ctrl.order_rules, dict)

    def test_get_rule_key(self):
        from ui_qt.session_controller import get_rule_key
        self.assertEqual(get_rule_key("A", "001"), "A:001")

    def test_resolve_pack_size_empty(self):
        from ui_qt.session_controller import QtSessionController
        ctrl = QtSessionController()
        pack = ctrl._resolve_pack_size(("A", "001"))
        self.assertIsNone(pack)

    def test_resolve_pack_size_from_session(self):
        from ui_qt.session_controller import QtSessionController
        ctrl = QtSessionController()
        ctrl.session.pack_size_lookup = {("A", "001"): 12}
        pack, source = ctrl._resolve_pack_size_with_source(("A", "001"))
        self.assertEqual(pack, 12)
        self.assertEqual(source, "x4_exact")

    def test_suggest_min_max_cache(self):
        from ui_qt.session_controller import QtSessionController
        ctrl = QtSessionController()
        # First call fills cache, second hits it
        result1 = ctrl._suggest_min_max(("A", "001"))
        result2 = ctrl._suggest_min_max(("A", "001"))
        self.assertEqual(result1, result2)

    def test_suspense_carry_dict_entry(self):
        from ui_qt.session_controller import QtSessionController
        ctrl = QtSessionController()
        ctrl.suspense_carry = {("A", "001"): {"qty": 5, "updated_at": ""}}
        self.assertEqual(ctrl._get_suspense_carry_qty(("A", "001")), 5)

    def test_suspense_carry_missing(self):
        from ui_qt.session_controller import QtSessionController
        ctrl = QtSessionController()
        self.assertEqual(ctrl._get_suspense_carry_qty(("A", "999")), 0)

    def test_remember_vendor_code(self):
        from ui_qt.session_controller import QtSessionController
        ctrl = QtSessionController()
        initial = len(ctrl.vendor_codes_used)
        ctrl._remember_vendor_code("ZZZNEW")
        self.assertIn("ZZZNEW", ctrl.vendor_codes_used)
        # Second call is idempotent
        ctrl._remember_vendor_code("ZZZNEW")
        self.assertEqual(ctrl.vendor_codes_used.count("ZZZNEW"), 1)

    def test_build_data_paths(self):
        from ui_qt.session_controller import build_data_paths
        paths = build_data_paths("/tmp/test")
        self.assertIn("order_rules", paths)
        self.assertIn("vendor_codes", paths)
        self.assertTrue(paths["order_rules"].endswith("order_rules.json"))


@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestBulkModelSetData(unittest.TestCase):
    """Test setData editing on BulkTableModel."""

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_setdata_vendor_no_callback(self):
        from ui_qt.bulk_model import BulkTableModel, COL_INDEX
        model = BulkTableModel()
        items = [_make_item(vendor="OLD")]
        model.set_data(items, {}, {})
        idx = model.index(0, COL_INDEX["vendor"])
        result = model.setData(idx, "NEW", Qt.EditRole)
        self.assertTrue(result)
        self.assertEqual(items[0]["vendor"], "NEW")

    def test_setdata_notes_no_callback(self):
        from ui_qt.bulk_model import BulkTableModel, COL_INDEX
        model = BulkTableModel()
        items = [_make_item()]
        model.set_data(items, {}, {})
        idx = model.index(0, COL_INDEX["notes"])
        model.setData(idx, "Hello", Qt.EditRole)
        self.assertEqual(items[0]["notes"], "Hello")

    def test_setdata_readonly_column(self):
        from ui_qt.bulk_model import BulkTableModel, COL_INDEX
        model = BulkTableModel()
        items = [_make_item(desc="Original")]
        model.set_data(items, {}, {})
        idx = model.index(0, COL_INDEX["description"])
        result = model.setData(idx, "Changed", Qt.EditRole)
        self.assertFalse(result)
        self.assertEqual(items[0]["description"], "Original")

    def test_setdata_with_callback(self):
        from ui_qt.bulk_model import BulkTableModel, COL_INDEX
        model = BulkTableModel()
        items = [_make_item()]
        model.set_data(items, {}, {})
        edits = []
        model.edit_callback = lambda item, col, val: edits.append((item, col, val))
        idx = model.index(0, COL_INDEX["vendor"])
        model.setData(idx, "ABC", Qt.EditRole)
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0][1], "vendor")
        self.assertEqual(edits[0][2], "ABC")

    def test_setdata_final_qty(self):
        from ui_qt.bulk_model import BulkTableModel, COL_INDEX
        model = BulkTableModel()
        items = [_make_item()]
        model.set_data(items, {}, {})
        idx = model.index(0, COL_INDEX["final_qty"])
        model.setData(idx, "42", Qt.EditRole)
        self.assertEqual(items[0]["final_qty"], 42)

    def test_setdata_invalid_qty(self):
        from ui_qt.bulk_model import BulkTableModel, COL_INDEX
        model = BulkTableModel()
        items = [_make_item()]
        model.set_data(items, {}, {})
        idx = model.index(0, COL_INDEX["final_qty"])
        result = model.setData(idx, "abc", Qt.EditRole)
        self.assertFalse(result)


@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestShellEditing(unittest.TestCase):
    """Integration tests for shell edit handlers."""

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def _make_shell(self, n=20):
        from ui_qt.shell import POBuilderShell
        shell = POBuilderShell(app_version="test")
        items = [_make_item(lc="A", ic=f"{i:03d}", vendor="" if i % 2 else "VND") for i in range(n)]
        shell.bulk_tab.set_data(items, {}, {})
        return shell, items

    def test_vendor_apply(self):
        shell, items = self._make_shell()
        shell._on_vendor_applied([0, 1, 2], "ABC")
        self.assertEqual(items[0]["vendor"], "ABC")
        self.assertEqual(items[1]["vendor"], "ABC")
        self.assertEqual(items[2]["vendor"], "ABC")

    def test_row_removal(self):
        shell, items = self._make_shell(10)
        shell._on_rows_removed([0, 5])
        self.assertEqual(shell.bulk_tab.model.rowCount(), 8)

    def test_cell_edit_vendor(self):
        shell, items = self._make_shell()
        from ui_qt.bulk_model import COL_INDEX
        idx = shell.bulk_tab.model.index(0, COL_INDEX["vendor"])
        shell.bulk_tab.model.setData(idx, "XYZ", Qt.EditRole)
        # Edit goes through callback which mutates the item directly
        self.assertEqual(items[0]["vendor"], "XYZ")


if __name__ == "__main__":
    unittest.main()
