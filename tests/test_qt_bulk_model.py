"""Tests for ui_qt.bulk_model — BulkTableModel + BulkFilterProxyModel.

These are headless (no QApplication needed for model logic), but
PySide6 must be importable.
"""

import unittest
import sys

try:
    from PySide6.QtCore import Qt, QModelIndex
    from PySide6.QtWidgets import QApplication
    HAS_QT = True
except ImportError:
    HAS_QT = False

# Ensure project root is on path
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_item(lc="A", ic="001", desc="Widget", vendor="", status="", qty_sold=10,
               qty_suspended=0, pack_size=None, order_qty=0, **extra):
    item = {
        "line_code": lc, "item_code": ic, "description": desc,
        "vendor": vendor, "status": status, "qty_sold": qty_sold,
        "qty_suspended": qty_suspended, "pack_size": pack_size,
        "order_qty": order_qty, "raw_need": order_qty,
        "suggested_qty": order_qty, "final_qty": order_qty,
        "why": "test", "notes": "", "order_policy": "",
    }
    item.update(extra)
    return item


def _make_items(n=10):
    items = []
    for i in range(n):
        lc = chr(65 + (i % 3))  # A, B, C
        vendor = "VND" if i % 3 == 0 else ""
        status = ["", "REVIEW", "SKIP"][i % 3]
        items.append(_make_item(
            lc=lc, ic=f"{i:03d}", desc=f"Item {i}",
            vendor=vendor, status=status, qty_sold=i * 5,
        ))
    return items


@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestBulkTableModel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)
        else:
            cls._app = QApplication.instance()

    def test_empty_model(self):
        from ui_qt.bulk_model import BulkTableModel
        model = BulkTableModel()
        self.assertEqual(model.rowCount(), 0)
        self.assertEqual(model.columnCount(), 22)

    def test_set_data(self):
        from ui_qt.bulk_model import BulkTableModel, COLUMNS
        model = BulkTableModel()
        items = _make_items(5)
        model.set_data(items, {}, {})
        self.assertEqual(model.rowCount(), 5)
        self.assertEqual(model.columnCount(), len(COLUMNS))

    def test_display_data(self):
        from ui_qt.bulk_model import BulkTableModel, COL_INDEX
        model = BulkTableModel()
        items = [_make_item(lc="A", ic="100", desc="Test Widget", vendor="ABC")]
        model.set_data(items, {}, {})
        # Vendor column
        idx = model.index(0, COL_INDEX["vendor"])
        self.assertEqual(model.data(idx, Qt.DisplayRole), "ABC")
        # Item code column
        idx = model.index(0, COL_INDEX["item_code"])
        self.assertEqual(model.data(idx, Qt.DisplayRole), "100")
        # Description
        idx = model.index(0, COL_INDEX["description"])
        self.assertEqual(model.data(idx, Qt.DisplayRole), "Test Widget")

    def test_header_data(self):
        from ui_qt.bulk_model import BulkTableModel
        model = BulkTableModel()
        model.set_data(_make_items(3), {}, {})
        self.assertEqual(model.headerData(0, Qt.Horizontal, Qt.DisplayRole), "Vendor")
        self.assertEqual(model.headerData(1, Qt.Horizontal, Qt.DisplayRole), "LC")

    def test_flags_editable(self):
        from ui_qt.bulk_model import BulkTableModel, COL_INDEX
        model = BulkTableModel()
        model.set_data([_make_item()], {}, {})
        # vendor is editable
        vendor_idx = model.index(0, COL_INDEX["vendor"])
        self.assertTrue(model.flags(vendor_idx) & Qt.ItemIsEditable)
        # description is not
        desc_idx = model.index(0, COL_INDEX["description"])
        self.assertFalse(model.flags(desc_idx) & Qt.ItemIsEditable)

    def test_row_tint_role(self):
        from ui_qt.bulk_model import BulkTableModel, ROW_TINT_ROLE, COL_INDEX
        import theme as t
        model = BulkTableModel()
        items = [
            _make_item(vendor="ABC", status="OK"),      # assigned → green tint
            _make_item(ic="002", status="REVIEW"),       # review → amber tint
            _make_item(ic="003", status="SKIP"),         # skip → dark tint
            _make_item(ic="004", vendor="", status=""),  # no tint
        ]
        model.set_data(items, {}, {})
        # Assigned item
        tint0 = model.data(model.index(0, 0), ROW_TINT_ROLE)
        self.assertEqual(tint0, t.FILL_OK_SOFT)
        # Review item
        tint1 = model.data(model.index(1, 0), ROW_TINT_ROLE)
        self.assertEqual(tint1, t.FILL_WARNING_SOFT)
        # Skip item
        tint2 = model.data(model.index(2, 0), ROW_TINT_ROLE)
        self.assertEqual(tint2, t.FILL_SKIP_SOFT)
        # No tint
        tint3 = model.data(model.index(3, 0), ROW_TINT_ROLE)
        self.assertIsNone(tint3)

    def test_generation_cache(self):
        from ui_qt.bulk_model import BulkTableModel, COL_INDEX
        model = BulkTableModel()
        items = [_make_item(vendor="OLD")]
        model.set_data(items, {}, {})
        # Read vendor
        idx = model.index(0, COL_INDEX["vendor"])
        self.assertEqual(model.data(idx, Qt.DisplayRole), "OLD")
        # Mutate item directly and bump generation
        items[0]["vendor"] = "NEW"
        model.bump_generation()
        self.assertEqual(model.data(idx, Qt.DisplayRole), "NEW")

    def test_item_at(self):
        from ui_qt.bulk_model import BulkTableModel
        model = BulkTableModel()
        items = _make_items(3)
        model.set_data(items, {}, {})
        self.assertIs(model.item_at(0), items[0])
        self.assertIsNone(model.item_at(99))

    def test_refresh_rows(self):
        from ui_qt.bulk_model import BulkTableModel
        model = BulkTableModel()
        model.set_data(_make_items(5), {}, {})
        # Should not raise
        model.refresh_rows([0, 2, 4])


@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestBulkFilterProxyModel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)
        else:
            cls._app = QApplication.instance()

    def _setup(self, items=None):
        from ui_qt.bulk_model import BulkTableModel, BulkFilterProxyModel
        model = BulkTableModel()
        proxy = BulkFilterProxyModel()
        proxy.setSourceModel(model)
        model.set_data(items or _make_items(9), {}, {})
        return model, proxy

    def test_no_filter(self):
        model, proxy = self._setup()
        self.assertEqual(proxy.rowCount(), model.rowCount())

    def test_text_filter(self):
        items = [
            _make_item(ic="BOLT", desc="Hex Bolt"),
            _make_item(ic="NUT", desc="Hex Nut"),
            _make_item(ic="WASH", desc="Flat Washer"),
        ]
        _, proxy = self._setup(items)
        proxy.set_text_filter("hex")
        self.assertEqual(proxy.rowCount(), 2)

    def test_line_code_filter(self):
        items = _make_items(9)  # A, B, C cycling
        _, proxy = self._setup(items)
        proxy.set_line_code_filter("A")
        # A appears at indices 0, 3, 6 = 3 items
        self.assertEqual(proxy.rowCount(), 3)

    def test_status_filter_assigned(self):
        items = [
            _make_item(ic="001", vendor="VND"),
            _make_item(ic="002", vendor=""),
            _make_item(ic="003", vendor="ABC"),
        ]
        _, proxy = self._setup(items)
        proxy.set_status_filter("Assigned")
        self.assertEqual(proxy.rowCount(), 2)

    def test_status_filter_unassigned(self):
        items = [
            _make_item(ic="001", vendor="VND"),
            _make_item(ic="002", vendor=""),
            _make_item(ic="003", vendor=""),
        ]
        _, proxy = self._setup(items)
        proxy.set_status_filter("Unassigned")
        self.assertEqual(proxy.rowCount(), 2)

    def test_vendor_worksheet(self):
        items = [
            _make_item(ic="001", vendor="ABC"),
            _make_item(ic="002", vendor="XYZ"),
            _make_item(ic="003", vendor="ABC"),
        ]
        _, proxy = self._setup(items)
        proxy.set_vendor_worksheet("ABC")
        self.assertEqual(proxy.rowCount(), 2)

    def test_item_status_filter(self):
        items = [
            _make_item(ic="001", status="REVIEW"),
            _make_item(ic="002", status="SKIP"),
            _make_item(ic="003", status="OK"),
        ]
        _, proxy = self._setup(items)
        proxy.set_item_status_filter("Review")
        self.assertEqual(proxy.rowCount(), 1)

    def test_source_filter(self):
        items = [
            _make_item(ic="001", qty_sold=10, qty_suspended=0),   # Sales
            _make_item(ic="002", qty_sold=0, qty_suspended=5),    # Susp
            _make_item(ic="003", qty_sold=10, qty_suspended=5),   # Both
        ]
        _, proxy = self._setup(items)
        proxy.set_source_filter("Susp")
        self.assertEqual(proxy.rowCount(), 1)

    def test_combined_filters(self):
        items = [
            _make_item(lc="A", ic="001", vendor="VND", status="OK"),
            _make_item(lc="A", ic="002", vendor="", status="REVIEW"),
            _make_item(lc="B", ic="003", vendor="VND", status="OK"),
        ]
        _, proxy = self._setup(items)
        proxy.set_line_code_filter("A")
        proxy.set_status_filter("Assigned")
        self.assertEqual(proxy.rowCount(), 1)

    def test_reset_filters(self):
        items = _make_items(9)
        model, proxy = self._setup(items)
        proxy.set_line_code_filter("A")
        self.assertLess(proxy.rowCount(), model.rowCount())
        proxy.reset_all_filters()
        self.assertEqual(proxy.rowCount(), model.rowCount())


@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestBulkRowHelpers(unittest.TestCase):

    def test_bulk_row_id(self):
        from ui_qt.bulk_model import bulk_row_id
        item = {"line_code": "A", "item_code": "001"}
        rid = bulk_row_id(item)
        self.assertEqual(rid, '["A","001"]')
        # Cached on second call
        self.assertEqual(bulk_row_id(item), rid)

    def test_row_zone(self):
        from ui_qt.bulk_model import row_zone
        self.assertEqual(row_zone({"vendor": "ABC", "status": "OK"}), "assigned")
        self.assertEqual(row_zone({"vendor": "", "status": "REVIEW"}), "review")
        self.assertEqual(row_zone({"vendor": "", "status": "WARNING"}), "warning")
        self.assertEqual(row_zone({"vendor": "", "status": "SKIP"}), "skip")
        self.assertEqual(row_zone({"vendor": "", "status": ""}), "")
        # Vendor + review → review wins
        self.assertEqual(row_zone({"vendor": "ABC", "status": "REVIEW"}), "review")

    def test_build_row_values_returns_tuple(self):
        from ui_qt.bulk_model import build_row_values, COLUMNS
        item = _make_item(lc="X", ic="999", desc="Test", vendor="VND")
        values = build_row_values(item, {}, {})
        self.assertIsInstance(values, tuple)
        self.assertEqual(len(values), len(COLUMNS))
        self.assertEqual(values[0], "VND")  # vendor


if __name__ == "__main__":
    unittest.main()
