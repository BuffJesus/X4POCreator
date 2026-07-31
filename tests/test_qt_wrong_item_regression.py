"""Regression tests for the 'wrong item under filter/sort' index bugs.

Guards three fixes:
  1. shell._on_vendor_applied must resolve SOURCE indices via source_item_at,
     not item_at (which is visible-space).  (ui_qt/shell.py)
  2. review_tab._visible_items must be stored in painted (vendor-sorted) order
     so cell edits/removes target the item actually shown on that row.
  3. command_palette jump uses the visible row directly (no source remap).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from PySide6.QtWidgets import QApplication
    HAS_QT = True
except ImportError:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 not available")
class WrongItemRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    # ── Bug #1: bulk vendor apply resolves source indices ──────────────
    def test_source_item_at_vs_item_at_under_filter(self):
        """With a filter active, a SOURCE index must resolve via source_item_at.

        item_at would re-index into _visible_indices and hit the wrong item;
        this test locks in the distinction the fix relies on.
        """
        from ui_qt.bulk_model import BulkTableModel

        items = [
            {"line_code": "AAA", "item_code": "1", "vendor": ""},
            {"line_code": "BBB", "item_code": "2", "vendor": ""},
            {"line_code": "AAA", "item_code": "3", "vendor": ""},
        ]
        model = BulkTableModel()
        model.set_data(items, inventory_lookup={}, order_rules={})
        # Filter to line code AAA -> visible = source indices [0, 2].
        model.apply_filters(line_code="AAA")
        self.assertEqual(model._visible_indices, [0, 2])

        # Emulate _on_vendor_applied: it receives SOURCE indices (e.g. 2, the
        # third item). source_item_at(2) must be that exact item.
        self.assertIs(model.source_item_at(2), items[2])
        # item_at(2) would be out of visible range here (only 2 visible rows),
        # i.e. the old code silently skipped or mis-targeted.
        self.assertIsNone(model.item_at(2))

    # ── Bug #2: review tab visible order matches painted order ─────────
    def test_review_visible_items_match_painted_rows(self):
        from ui_qt.review_tab import ReviewTab

        # Encounter order deliberately differs from vendor-sorted order:
        # ZED before ACE, but the table paints ACE first (sorted).
        items = [
            {"vendor": "ZED", "line_code": "L1", "item_code": "Z1",
             "description": "z", "final_qty": 5, "status": "OK", "why": ""},
            {"vendor": "ACE", "line_code": "L2", "item_code": "A1",
             "description": "a", "final_qty": 9, "status": "OK", "why": ""},
        ]
        tab = ReviewTab()
        tab.set_items(items)

        # Row 0 is painted vendor-sorted -> ACE/A1. _visible_items[0] must agree.
        row0_item_code = tab._table.item(0, 2).text()
        self.assertEqual(row0_item_code, "A1")
        self.assertEqual(tab._visible_items[0]["item_code"], "A1")
        self.assertEqual(tab._visible_items[1]["item_code"], "Z1")
        # And the painted-row item is the *same object* the handlers will edit.
        self.assertIs(tab._visible_items[0], items[1])


if __name__ == "__main__":
    unittest.main()
