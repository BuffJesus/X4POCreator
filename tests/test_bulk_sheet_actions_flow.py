import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bulk_sheet_actions_flow


class BulkSheetActionsFlowTests(unittest.TestCase):
    def test_bulk_copy_selection_returns_break_only_when_sheet_copies(self):
        app_true = SimpleNamespace(bulk_sheet=SimpleNamespace(copy_selection_to_clipboard=lambda: True))
        app_false = SimpleNamespace(bulk_sheet=SimpleNamespace(copy_selection_to_clipboard=lambda: False))

        self.assertEqual(bulk_sheet_actions_flow.bulk_copy_selection(app_true), "break")
        self.assertIsNone(bulk_sheet_actions_flow.bulk_copy_selection(app_false))

    def test_bulk_clear_selection_resets_context(self):
        events = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(clear_selection=lambda: events.append("clear")),
            _right_click_bulk_context={"row_id": "1"},
        )

        result = bulk_sheet_actions_flow.bulk_clear_selection(fake_app)

        self.assertEqual(result, "break")
        self.assertEqual(events, ["clear"])
        self.assertIsNone(fake_app._right_click_bulk_context)


if __name__ == "__main__":
    unittest.main()
