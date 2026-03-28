import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_load


class UILoadTests(unittest.TestCase):
    class DummyVar:
        def __init__(self, value=""):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    def test_load_file_sections_hide_legacy_by_default(self):
        sections = ui_load.load_file_sections()

        self.assertEqual([section["title"] for section in sections], [
            "Core Files",
            "Optional Support Files",
        ])
        self.assertEqual(
            [row["browse_key"] for row in sections[0]["rows"]],
            ["detailedsales", "receivedparts", "minmax", "packsize"],
        )
        self.assertEqual(
            [row["browse_key"] for row in sections[1]["rows"]],
            ["onhand", "po", "susp"],
        )

    def test_load_file_sections_include_legacy_when_requested(self):
        sections = ui_load.load_file_sections(include_legacy=True)

        self.assertEqual([section["title"] for section in sections], [
            "Core Files",
            "Optional Support Files",
            "Legacy Compatibility",
        ])
        self.assertEqual(
            [row["browse_key"] for row in sections[2]["rows"]],
            ["sales"],
        )

    def test_ensure_load_file_vars_creates_all_file_path_vars_even_when_legacy_is_hidden(self):
        fake_app = SimpleNamespace()

        vars_by_attr = ui_load.ensure_load_file_vars(
            fake_app,
            var_factory=self.DummyVar,
        )

        self.assertIn("var_sales_path", vars_by_attr)
        self.assertIn("var_detailed_sales_path", vars_by_attr)
        self.assertIn("var_received_parts_path", vars_by_attr)
        self.assertIsInstance(getattr(fake_app, "var_sales_path"), self.DummyVar)
        self.assertIsInstance(getattr(fake_app, "var_packsize_path"), self.DummyVar)

    def test_ensure_load_file_vars_preserves_existing_selected_paths(self):
        fake_app = type("FakeApp", (), {})()
        fake_app.var_detailed_sales_path = self.DummyVar("C:\\Reports\\detailed.csv")
        fake_app.var_received_parts_path = self.DummyVar("C:\\Reports\\received.csv")

        vars_by_attr = ui_load.ensure_load_file_vars(
            fake_app,
            var_factory=self.DummyVar,
        )

        self.assertEqual(vars_by_attr["var_detailed_sales_path"].get(), "C:\\Reports\\detailed.csv")
        self.assertEqual(vars_by_attr["var_received_parts_path"].get(), "C:\\Reports\\received.csv")
        self.assertEqual(fake_app.var_detailed_sales_path.get(), "C:\\Reports\\detailed.csv")
        self.assertEqual(fake_app.var_received_parts_path.get(), "C:\\Reports\\received.csv")


if __name__ == "__main__":
    unittest.main()
