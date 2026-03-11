import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_filters


class UiFiltersTests(unittest.TestCase):
    def test_column_count_expands_for_large_lists(self):
        self.assertEqual(ui_filters._column_count(132, 18, min_cols=4), 8)
        self.assertEqual(ui_filters._column_count(30, 14, min_cols=2), 3)
        self.assertEqual(ui_filters._column_count(30, 14, min_cols=1, max_cols=2), 2)

    def test_column_count_respects_minimum_columns(self):
        self.assertEqual(ui_filters._column_count(4, 18, min_cols=4), 4)
        self.assertEqual(ui_filters._column_count(0, 18, min_cols=2), 2)


if __name__ == "__main__":
    unittest.main()
