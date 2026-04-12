"""Headless Qt tests for ``ui_qt.load_tab.LoadTab``.

Tests only exercise the widget-level behavior — file picker state,
load button enable/disable, worker plumbing via a mocked parse
callable.  The heavy ``load_flow.parse_all_files`` logic is not invoked
here; it has its own ~100-test coverage under ``test_load_flow.py``.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    _PYSIDE6_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PYSIDE6_AVAILABLE = False


@unittest.skipUnless(_PYSIDE6_AVAILABLE, "PySide6 not installed")
class LoadTabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _build_tab(self, app_settings=None):
        from ui_qt.load_tab import LoadTab
        return LoadTab(app_settings=app_settings)

    def test_picker_rows_match_load_file_sections(self):
        from ui_load import LOAD_FILE_SECTIONS
        tab = self._build_tab()
        expected_keys = set()
        for section in LOAD_FILE_SECTIONS:
            for row in section["rows"]:
                expected_keys.add(row["browse_key"])
        self.assertEqual(set(tab._pickers.keys()), expected_keys)

    def test_required_keys_present(self):
        tab = self._build_tab()
        for key in ("detailedsales", "receivedparts"):
            self.assertIn(key, tab._pickers)

    def test_load_button_disabled_until_required_paths_set(self):
        tab = self._build_tab()
        self.assertFalse(tab._load_button.isEnabled())
        tab._pickers["detailedsales"].set_path("/tmp/sales.csv")
        self.assertFalse(tab._load_button.isEnabled())
        tab._pickers["receivedparts"].set_path("/tmp/rec.csv")
        self.assertTrue(tab._load_button.isEnabled())

    def test_load_button_disables_when_required_path_cleared(self):
        tab = self._build_tab()
        tab._pickers["detailedsales"].set_path("/a/b/c.csv")
        tab._pickers["receivedparts"].set_path("/a/b/d.csv")
        self.assertTrue(tab._load_button.isEnabled())
        tab._pickers["detailedsales"].set_path("")
        self.assertFalse(tab._load_button.isEnabled())

    def test_current_paths_returns_parser_keys(self):
        tab = self._build_tab()
        tab._pickers["detailedsales"].set_path("sales.csv")
        tab._pickers["receivedparts"].set_path("rec.csv")
        tab._pickers["po"].set_path("po.csv")
        paths = tab.current_paths()
        self.assertEqual(paths["detailedsales"], "sales.csv")
        self.assertEqual(paths["receivedparts"], "rec.csv")
        self.assertEqual(paths["po"], "po.csv")

    def test_quick_start_card_shown_when_last_scan_folder_valid(self):
        # Point last_scan_folder at a real temp dir so the tab renders
        # the quick-start card.
        with tempfile.TemporaryDirectory() as tmp:
            tab = self._build_tab({"last_scan_folder": tmp})
            # Crude: walk children and check for a label containing "Quick Start"
            from PySide6.QtWidgets import QLabel
            labels = [w.text() for w in tab.findChildren(QLabel) if hasattr(w, "text")]
            joined = " | ".join(labels)
            self.assertIn("Quick Start", joined)

    def test_quick_start_card_hidden_when_no_last_folder(self):
        tab = self._build_tab({})
        from PySide6.QtWidgets import QLabel
        labels = [w.text() for w in tab.findChildren(QLabel)]
        self.assertNotIn("Quick Start", " | ".join(labels))

    def test_quick_start_card_hidden_when_last_folder_missing(self):
        # Point at a path that doesn't exist → card should be suppressed
        # rather than rendering a broken "Scan folder that isn't there"
        # button.
        tab = self._build_tab({"last_scan_folder": "/no/such/path/ever"})
        from PySide6.QtWidgets import QLabel
        labels = [w.text() for w in tab.findChildren(QLabel)]
        self.assertNotIn("Quick Start", " | ".join(labels))


@unittest.skipUnless(_PYSIDE6_AVAILABLE, "PySide6 not installed")
class ParseWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_worker_emits_finished_with_result(self):
        from ui_qt.load_tab import ParseWorker

        captured = {}

        def fake_parse(paths, **kwargs):
            captured["paths"] = paths
            captured["kwargs"] = kwargs
            if callable(kwargs.get("progress_callback")):
                kwargs["progress_callback"]("step A")
                kwargs["progress_callback"]("step B")
            return {"sales_items": [{"line_code": "GR1-", "item_code": "A"}], "warnings": []}

        worker = ParseWorker(
            paths={"detailedsales": "x.csv", "receivedparts": "y.csv"},
            stored_schema_hashes={},
            parse_callable=fake_parse,
        )

        results = {"progress": [], "finished": None, "failed": None}
        worker.progress.connect(lambda m: results["progress"].append(m))
        worker.finished.connect(lambda r: results.update(finished=r))
        worker.failed.connect(lambda e: results.update(failed=e))

        worker.run()  # synchronous for the test

        self.assertIsNone(results["failed"])
        self.assertIsNotNone(results["finished"])
        self.assertEqual(results["finished"]["sales_items"][0]["item_code"], "A")
        # Progress messages marshaled through the signal
        self.assertIn("step A", results["progress"])
        self.assertIn("step B", results["progress"])
        # Parser got the paths and expected kwargs
        self.assertEqual(captured["paths"]["detailedsales"], "x.csv")
        self.assertIn("old_po_warning_days", captured["kwargs"])
        self.assertIn("stored_schema_hashes", captured["kwargs"])

    def test_worker_emits_failed_on_exception(self):
        from ui_qt.load_tab import ParseWorker

        def boom(paths, **kwargs):
            raise RuntimeError("bang")

        worker = ParseWorker(paths={}, parse_callable=boom)
        errors = []
        worker.failed.connect(errors.append)
        worker.run()
        self.assertEqual(errors, ["bang"])


if __name__ == "__main__":
    unittest.main()
