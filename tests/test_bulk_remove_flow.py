import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bulk_remove_flow


class BulkRemoveFlowTests(unittest.TestCase):
    def test_remove_filtered_rows_updates_payload_and_history_once(self):
        events = []
        app = SimpleNamespace(
            filtered_items=[
                {"item_code": "A"},
                {"item_code": "B"},
                {"item_code": "C"},
            ],
            last_removed_bulk_items=[],
            _capture_bulk_history_state=lambda: {"before": True},
            _finalize_bulk_history_action=lambda label, before: events.append((label, before)),
        )

        removed = bulk_remove_flow.remove_filtered_rows(
            app,
            [2, 1, 1],
            lambda value: dict(value),
            history_label="remove:selected_rows",
        )

        self.assertEqual(app.filtered_items, [{"item_code": "A"}])
        self.assertEqual(removed, [(2, {"item_code": "C"}), (1, {"item_code": "B"})])
        self.assertEqual(app.last_removed_bulk_items, removed)
        self.assertEqual(events, [("remove:selected_rows", {"before": True})])

    def test_remove_filtered_rows_skips_history_when_nothing_removed(self):
        events = []
        app = SimpleNamespace(
            filtered_items=[{"item_code": "A"}],
            last_removed_bulk_items=[],
            _capture_bulk_history_state=lambda: {"before": True},
            _finalize_bulk_history_action=lambda label, before: events.append((label, before)),
        )

        removed = bulk_remove_flow.remove_filtered_rows(
            app,
            [9],
            lambda value: dict(value),
            history_label="remove:selected_rows",
        )

        self.assertEqual(removed, [])
        self.assertEqual(app.filtered_items, [{"item_code": "A"}])
        self.assertEqual(app.last_removed_bulk_items, [])
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
