"""Tests for Qt command palette and shortcut overlay."""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from PySide6.QtWidgets import QApplication
    HAS_QT = True
except ImportError:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestCommandPalette(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def _make(self):
        from ui_qt.shell import POBuilderShell
        from ui_qt.command_palette import CommandPaletteDialog
        shell = POBuilderShell(app_version="test")
        # Load some items into bulk grid
        items = [
            {"line_code": "A", "item_code": f"{i:03d}", "description": f"Widget {i}",
             "vendor": "VND" if i % 2 == 0 else "", "status": "", "qty_sold": 10,
             "qty_suspended": 0, "pack_size": None, "order_qty": 0,
             "raw_need": 0, "suggested_qty": 0, "final_qty": 0,
             "why": "", "notes": "", "order_policy": ""}
            for i in range(20)
        ]
        shell.bulk_tab.set_data(items, {}, {})
        shell.controller.vendor_codes_used = ["VND", "ABC", "XYZ"]
        palette = CommandPaletteDialog(shell, parent=shell)
        return shell, palette

    def test_initial_results(self):
        _, palette = self._make()
        # Should show actions on empty query
        self.assertGreater(palette._list.count(), 0)

    def test_search_filters(self):
        _, palette = self._make()
        palette._input.setText("help")
        palette._do_search()
        # Should find the "Go to Help" action
        found = any("Help" in palette._results[i].get("label", "")
                     for i in range(len(palette._results)))
        self.assertTrue(found)

    def test_search_items(self):
        _, palette = self._make()
        palette._input.setText("A005")
        palette._do_search()
        found = any("005" in r.get("label", "") for r in palette._results)
        self.assertTrue(found)

    def test_search_vendor(self):
        _, palette = self._make()
        palette._input.setText("XYZ")
        palette._do_search()
        found = any("XYZ" in r.get("label", "") for r in palette._results)
        self.assertTrue(found)

    def test_empty_query_shows_actions(self):
        _, palette = self._make()
        palette._input.setText("")
        palette._do_search()
        kinds = {r.get("kind") for r in palette._results}
        self.assertIn("action", kinds)


@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestShortcutOverlay(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_construct(self):
        from ui_qt.shortcut_overlay import ShortcutOverlayDialog
        dialog = ShortcutOverlayDialog()
        self.assertEqual(dialog.windowTitle(), "Keyboard Shortcuts")

    def test_shortcut_groups_loaded(self):
        from shortcut_data import SHORTCUT_GROUPS
        self.assertGreater(len(SHORTCUT_GROUPS), 0)
        # Each group is (name, list_of_tuples)
        for name, shortcuts in SHORTCUT_GROUPS:
            self.assertIsInstance(name, str)
            self.assertGreater(len(shortcuts), 0)


@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestShellShortcuts(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_ctrl_k_action_exists(self):
        from ui_qt.shell import POBuilderShell
        shell = POBuilderShell(app_version="test")
        self.assertIsNotNone(shell._ctrl_k_action)

    def test_shortcut_action_exists(self):
        from ui_qt.shell import POBuilderShell
        shell = POBuilderShell(app_version="test")
        self.assertIsNotNone(shell._shortcut_action)


if __name__ == "__main__":
    unittest.main()
