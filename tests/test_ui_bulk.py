import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_bulk


class BulkUiTests(unittest.TestCase):
    def test_autosize_bulk_tree_is_noop_without_legacy_tree_editor(self):
        app = SimpleNamespace(bulk_sheet=SimpleNamespace())

        result = ui_bulk.autosize_bulk_tree(app)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
