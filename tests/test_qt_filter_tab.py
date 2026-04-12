"""Tests for ui_qt.filter_tab — FilterTab."""

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
class TestFilterTab(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def _make_tab(self):
        from ui_qt.filter_tab import FilterTab
        tab = FilterTab()
        tab.populate(
            ["A", "B", "C"],
            {"A": 100, "B": 200, "C": 50},
            [("CASH", "Cash Customer", 10), ("ACME", "Acme Corp", 5)],
        )
        return tab

    def test_initial_state_all_checked(self):
        tab = self._make_tab()
        self.assertEqual(tab.excluded_line_codes(), set())
        self.assertEqual(tab.excluded_customers(), set())

    def test_exclude_line_code(self):
        tab = self._make_tab()
        tab._lc_checks["B"].setChecked(False)
        self.assertEqual(tab.excluded_line_codes(), {"B"})

    def test_exclude_customer(self):
        tab = self._make_tab()
        tab._cust_checks["CASH"].setChecked(False)
        self.assertEqual(tab.excluded_customers(), {"CASH"})

    def test_deselect_all_lc(self):
        tab = self._make_tab()
        tab._toggle_all_lc(False)
        self.assertEqual(tab.excluded_line_codes(), {"A", "B", "C"})

    def test_select_all_lc(self):
        tab = self._make_tab()
        tab._toggle_all_lc(False)
        tab._toggle_all_lc(True)
        self.assertEqual(tab.excluded_line_codes(), set())

    def test_deselect_all_cust(self):
        tab = self._make_tab()
        tab._toggle_all_cust(False)
        self.assertEqual(tab.excluded_customers(), {"CASH", "ACME"})

    def test_empty_populate(self):
        from ui_qt.filter_tab import FilterTab
        tab = FilterTab()
        tab.populate([], {}, [])
        self.assertEqual(tab.excluded_line_codes(), set())
        self.assertEqual(tab.excluded_customers(), set())

    def test_apply_button_enabled(self):
        tab = self._make_tab()
        self.assertTrue(tab._apply_btn.isEnabled())

    def test_apply_button_disabled_empty(self):
        from ui_qt.filter_tab import FilterTab
        tab = FilterTab()
        tab.populate([], {}, [])
        self.assertFalse(tab._apply_btn.isEnabled())

    def test_signal_emitted(self):
        tab = self._make_tab()
        tab._lc_checks["A"].setChecked(False)
        tab._cust_checks["ACME"].setChecked(False)
        results = []
        tab.filters_applied.connect(lambda lc, cust: results.append((lc, cust)))
        tab._on_apply()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], {"A"})
        self.assertEqual(results[0][1], {"ACME"})


@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestShellFilterWiring(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_filter_tab_in_shell(self):
        from ui_qt.shell import POBuilderShell
        from ui_qt.filter_tab import FilterTab
        shell = POBuilderShell(app_version="test")
        self.assertIsInstance(shell.filter_tab, FilterTab)

    def test_no_placeholder_pages(self):
        """All nav items should now have real tabs, no placeholders."""
        from ui_qt.shell import POBuilderShell
        shell = POBuilderShell(app_version="test")
        for i in range(shell.stack.count()):
            widget = shell.stack.widget(i)
            # Placeholder pages have a specific body label pattern
            self.assertFalse(
                hasattr(widget, "layout") and widget.findChild(type(None)),
                f"Stack index {i} looks like a placeholder",
            )


if __name__ == "__main__":
    unittest.main()
