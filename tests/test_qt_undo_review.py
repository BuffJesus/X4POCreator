"""Tests for ui_qt.undo_stack and ui_qt.review_tab."""

import copy
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


def _item(lc="A", ic="001", vendor="", status="", **kw):
    d = {
        "line_code": lc, "item_code": ic, "description": f"Item {ic}",
        "vendor": vendor, "status": status, "qty_sold": 10,
        "qty_suspended": 0, "pack_size": None, "order_qty": 0,
        "raw_need": 0, "suggested_qty": 0, "final_qty": 0,
        "why": "", "notes": "", "order_policy": "",
    }
    d.update(kw)
    return d


# ─── UndoStack tests (no QApplication needed) ────────────────────────────

class TestBulkUndoStack(unittest.TestCase):

    def test_empty_stack(self):
        from ui_qt.undo_stack import BulkUndoStack
        stack = BulkUndoStack()
        self.assertFalse(stack.can_undo())
        self.assertFalse(stack.can_redo())

    def test_push_edit_and_undo(self):
        from ui_qt.undo_stack import BulkUndoStack
        stack = BulkUndoStack()
        items = [_item(vendor="OLD")]
        stack.push_edit("edit:vendor", items, [0])
        items[0]["vendor"] = "NEW"
        self.assertTrue(stack.can_undo())
        entry = stack.undo(items)
        self.assertIsNotNone(entry)
        self.assertEqual(items[0]["vendor"], "OLD")

    def test_redo_after_undo(self):
        from ui_qt.undo_stack import BulkUndoStack
        stack = BulkUndoStack()
        items = [_item(vendor="OLD")]
        stack.push_edit("edit:vendor", items, [0])
        items[0]["vendor"] = "NEW"
        stack.undo(items)
        self.assertEqual(items[0]["vendor"], "OLD")
        self.assertTrue(stack.can_redo())
        stack.redo(items)
        self.assertEqual(items[0]["vendor"], "NEW")

    def test_push_clears_redo(self):
        from ui_qt.undo_stack import BulkUndoStack
        stack = BulkUndoStack()
        items = [_item(vendor="A")]
        stack.push_edit("edit1", items, [0])
        items[0]["vendor"] = "B"
        stack.undo(items)
        self.assertTrue(stack.can_redo())
        # New edit clears redo
        stack.push_edit("edit2", items, [0])
        self.assertFalse(stack.can_redo())

    def test_removal_undo(self):
        from ui_qt.undo_stack import BulkUndoStack
        stack = BulkUndoStack()
        items = [_item(ic="001"), _item(ic="002"), _item(ic="003")]
        pairs = [(1, copy.deepcopy(items[1]))]
        stack.push_removal("remove", pairs)
        items.pop(1)
        self.assertEqual(len(items), 2)
        stack.undo(items)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[1]["item_code"], "002")

    def test_removal_redo(self):
        from ui_qt.undo_stack import BulkUndoStack
        stack = BulkUndoStack()
        items = [_item(ic="001"), _item(ic="002"), _item(ic="003")]
        pairs = [(1, copy.deepcopy(items[1]))]
        stack.push_removal("remove", pairs)
        items.pop(1)
        stack.undo(items)
        self.assertEqual(len(items), 3)
        stack.redo(items)
        self.assertEqual(len(items), 2)

    def test_max_depth(self):
        from ui_qt.undo_stack import BulkUndoStack, MAX_UNDO_DEPTH
        stack = BulkUndoStack()
        items = [_item()]
        for i in range(MAX_UNDO_DEPTH + 10):
            stack.push_edit(f"edit{i}", items, [0])
        self.assertEqual(len(stack._undo), MAX_UNDO_DEPTH)

    def test_labels(self):
        from ui_qt.undo_stack import BulkUndoStack
        stack = BulkUndoStack()
        items = [_item()]
        stack.push_edit("my_label", items, [0])
        self.assertEqual(stack.undo_label, "my_label")

    def test_clear(self):
        from ui_qt.undo_stack import BulkUndoStack
        stack = BulkUndoStack()
        items = [_item()]
        stack.push_edit("a", items, [0])
        stack.clear()
        self.assertFalse(stack.can_undo())


# ─── ReviewTab tests ──────────────────────────────────────────────────────

@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestReviewTab(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_empty(self):
        from ui_qt.review_tab import ReviewTab
        tab = ReviewTab()
        tab.set_items([])
        self.assertEqual(tab._table.rowCount(), 0)

    def test_set_items(self):
        from ui_qt.review_tab import ReviewTab
        tab = ReviewTab()
        items = [
            _item(ic="001", vendor="ABC", status="OK"),
            _item(ic="002", vendor="ABC", status="REVIEW"),
            _item(ic="003", vendor="XYZ", status="OK"),
        ]
        tab.set_items(items)
        self.assertEqual(tab._table.rowCount(), 3)

    def test_vendor_filter(self):
        from ui_qt.review_tab import ReviewTab
        tab = ReviewTab()
        items = [
            _item(ic="001", vendor="ABC"),
            _item(ic="002", vendor="XYZ"),
        ]
        tab.set_items(items)
        tab._vendor_combo.setCurrentText("ABC")
        tab._refresh_table()
        self.assertEqual(tab._table.rowCount(), 1)

    def test_exceptions_only(self):
        from ui_qt.review_tab import ReviewTab
        tab = ReviewTab()
        items = [
            _item(ic="001", vendor="ABC", status="OK"),
            _item(ic="002", vendor="ABC", status="REVIEW"),
            _item(ic="003", vendor="ABC", status="WARNING"),
        ]
        tab.set_items(items)
        tab._set_show("Exceptions Only")
        self.assertEqual(tab._table.rowCount(), 2)

    def test_context_summary_mentions_ready_items(self):
        from ui_qt.review_tab import ReviewTab
        tab = ReviewTab()
        tab.set_items([
            _item(ic="001", vendor="ABC", status="OK", final_qty=3),
            _item(ic="002", vendor="XYZ", status="REVIEW", final_qty=1),
        ])
        self.assertIn("1", tab._context_summary.text())
        self.assertIn("vendor file", tab._context_summary.text())

    def test_focus_chip_mentions_top_exception_vendor(self):
        from ui_qt.review_tab import ReviewTab
        tab = ReviewTab()
        tab.set_items([
            _item(ic="001", vendor="ABC", status="REVIEW"),
            _item(ic="002", vendor="ABC", status="WARNING"),
            _item(ic="003", vendor="XYZ", status="REVIEW"),
        ])
        self.assertIn("ABC", tab._focus_chip.text())

    def test_is_exception(self):
        from ui_qt.review_tab import _is_exception
        self.assertTrue(_is_exception({"status": "REVIEW"}))
        self.assertTrue(_is_exception({"status": "warning"}))
        self.assertTrue(_is_exception({"status": "OK", "review_required": True}))
        self.assertFalse(_is_exception({"status": "OK"}))
        self.assertFalse(_is_exception({"status": ""}))


@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestExportPreviewDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_constructs_with_preview_data(self):
        from ui_qt.export_dialogs import ExportPreviewDialog
        dialog = ExportPreviewDialog({
            "vendor_summaries": [
                {"vendor": "ABC", "item_count": 2, "estimated_value": 20.0},
                {"vendor": "XYZ", "item_count": 1, "estimated_value": 5.0},
            ],
            "total_item_count": 3,
            "total_estimated_value": 25.0,
        })
        self.assertEqual(dialog._table.rowCount(), 2)

    def test_override_changes_are_captured(self):
        from ui_qt.export_dialogs import ExportPreviewDialog
        dialog = ExportPreviewDialog({
            "vendor_summaries": [
                {"vendor": "ABC", "item_count": 2, "estimated_value": 20.0},
            ],
            "total_item_count": 2,
            "total_estimated_value": 20.0,
        })
        combo = dialog._table.cellWidget(0, 3)
        combo.setCurrentIndex(1)  # Defer
        self.assertEqual(dialog.overrides, {"ABC": "defer"})


# ─── Shell integration ────────────────────────────────────────────────────

@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestShellReview(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_review_tab_exists(self):
        from ui_qt.shell import POBuilderShell
        from ui_qt.review_tab import ReviewTab
        shell = POBuilderShell(app_version="test")
        self.assertIsInstance(shell.review_tab, ReviewTab)

    def test_nav_to_review_populates(self):
        from ui_qt.shell import POBuilderShell
        shell = POBuilderShell(app_version="test")
        items = [
            _item(ic="001", vendor="ABC"),
            _item(ic="002", vendor=""),
            _item(ic="003", vendor="XYZ"),
        ]
        shell.bulk_tab.set_data(items, {}, {})
        # Navigate to Review (index 3)
        shell._on_nav_changed(3)
        # Should have 2 assigned items
        self.assertEqual(shell.review_tab._table.rowCount(), 2)

    def test_export_helpers_exist(self):
        from ui_qt.shell import POBuilderShell
        shell = POBuilderShell(app_version="test")
        self.assertTrue(callable(shell._show_export_preview_dialog))
        self.assertTrue(callable(shell._choose_output_dir))
        self.assertTrue(callable(shell._export_vendor_po))


if __name__ == "__main__":
    unittest.main()
