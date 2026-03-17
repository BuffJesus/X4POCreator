import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_load


class UILoadTests(unittest.TestCase):
    def test_load_file_sections_prioritize_core_pair_and_demote_legacy(self):
        sections = ui_load.load_file_sections()

        self.assertEqual([section["title"] for section in sections], [
            "Core Files",
            "Optional Support Files",
            "Legacy Compatibility",
        ])
        self.assertEqual(
            [row["browse_key"] for row in sections[0]["rows"]],
            ["detailedsales", "receivedparts", "minmax", "packsize"],
        )
        self.assertEqual(
            [row["browse_key"] for row in sections[1]["rows"]],
            ["onhand", "po", "susp"],
        )
        self.assertEqual(
            [row["browse_key"] for row in sections[2]["rows"]],
            ["sales"],
        )


if __name__ == "__main__":
    unittest.main()
