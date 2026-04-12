"""Headless Qt tests for the PO Builder shell.

Uses ``QT_QPA_PLATFORM=offscreen`` so the tests work in CI/build
environments without a display.  These tests exercise the shell's widget
hierarchy but don't assert pixel-level layout — that's the job of manual
visual QA on a real monitor.
"""

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Force Qt to run without a display before any PySide6 import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    _PYSIDE6_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PYSIDE6_AVAILABLE = False


@unittest.skipUnless(_PYSIDE6_AVAILABLE, "PySide6 not installed")
class POBuilderShellTests(unittest.TestCase):
    """Headless smoke tests for ui_qt.shell.POBuilderShell."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _build_shell(self):
        from ui_qt.shell import POBuilderShell
        return POBuilderShell(app_version="0.10.0-test")

    def test_shell_instantiates(self):
        shell = self._build_shell()
        self.assertIsNotNone(shell)
        self.assertIn("0.10.0-test", shell.windowTitle())

    def test_sidebar_has_five_nav_items(self):
        shell = self._build_shell()
        labels = [shell.sidebar.item(i).text() for i in range(shell.sidebar.count())]
        self.assertEqual(labels, ["Load", "Filter", "Bulk", "Review", "Help"])

    def test_stack_mirrors_sidebar_item_count(self):
        shell = self._build_shell()
        self.assertEqual(shell.stack.count(), shell.sidebar.count())

    def test_initial_selection_is_load(self):
        shell = self._build_shell()
        self.assertEqual(shell.sidebar.currentRow(), 0)
        self.assertEqual(shell.stack.currentIndex(), 0)

    def test_selection_navigates_stack(self):
        shell = self._build_shell()
        shell.sidebar.setCurrentRow(2)  # Bulk
        self.assertEqual(shell.stack.currentIndex(), 2)
        shell.sidebar.setCurrentRow(4)  # Help
        self.assertEqual(shell.stack.currentIndex(), 4)

    def test_sidebar_has_fixed_width(self):
        shell = self._build_shell()
        # Matches Tuner's 160px sidebar convention.
        self.assertEqual(shell.sidebar.width(), 170)

    def test_ctrl_k_action_registered(self):
        shell = self._build_shell()
        # Action exists with the Ctrl+K shortcut so the keystroke is a
        # known no-op rather than dropping through to the sidebar.
        shortcuts = [a.shortcut().toString() for a in shell.actions()]
        self.assertIn("Ctrl+K", shortcuts)

    def test_placeholder_pages_have_banner(self):
        from PySide6.QtWidgets import QLabel
        shell = self._build_shell()
        for i in range(shell.stack.count()):
            page = shell.stack.widget(i)
            # Each placeholder has at least one QLabel with rich-text banner.
            labels = page.findChildren(QLabel)
            self.assertTrue(labels, f"page {i} has no QLabel")


if __name__ == "__main__":
    unittest.main()
