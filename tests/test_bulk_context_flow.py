import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bulk_context_flow


class BulkContextFlowTests(unittest.TestCase):
    def test_dismiss_duplicate_persists_and_refreshes(self):
        events = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(flush_pending_edit=lambda: events.append("flush")),
            dup_whitelist=set(),
            duplicate_ic_lookup={"ABC123": {"AER-", "MOT-"}},
            _save_duplicate_whitelist=lambda: events.append("save"),
            _apply_bulk_filter=lambda: events.append("filter"),
        )

        bulk_context_flow.dismiss_duplicate(fake_app, "ABC123")

        self.assertIn("ABC123", fake_app.dup_whitelist)
        self.assertNotIn("ABC123", fake_app.duplicate_ic_lookup)
        self.assertEqual(events, ["flush", "save", "filter"])

    def test_ignore_from_bulk_uses_right_click_snapshot_selection_when_available(self):
        events = []
        fake_app = SimpleNamespace(
            _right_click_bulk_context={"row_id": "1"},
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: events.append("flush"),
                snapshot_row_ids=lambda: ("0", "1"),
                explicit_selected_row_ids=lambda: ("0",),
                selected_row_ids=lambda: ("0",),
                current_row_id=lambda: "0",
            ),
            filtered_items=[
                {"line_code": "AER-", "item_code": "GH781-4"},
                {"line_code": "MOT-", "item_code": "ABC123"},
            ],
            _ignore_key=lambda lc, ic: f"{lc}:{ic}",
            _ignore_items_by_keys=lambda keys: events.append(("ignore", keys)) or len(keys),
        )

        bulk_context_flow.ignore_from_bulk(
            fake_app,
            lambda title, message: events.append(("ask", title)) or True,
            lambda title, message: events.append(("info", title, message)),
        )

        self.assertEqual(events[0], "flush")
        self.assertEqual(events[1], ("ask", "Ignore Item"))
        self.assertEqual(events[2], ("ignore", {"AER-:GH781-4", "MOT-:ABC123"}))
        self.assertEqual(events[3], ("info", "Ignored", "Ignored 2 item(s)."))

    def test_ignore_from_bulk_falls_back_to_single_right_click_row_when_outside_snapshot(self):
        events = []
        fake_app = SimpleNamespace(
            _right_click_bulk_context={"row_id": "1"},
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: events.append("flush"),
                snapshot_row_ids=lambda: ("0",),
                explicit_selected_row_ids=lambda: ("0",),
                selected_row_ids=lambda: ("0",),
                current_row_id=lambda: "0",
            ),
            filtered_items=[
                {"line_code": "AER-", "item_code": "GH781-4"},
                {"line_code": "MOT-", "item_code": "ABC123"},
            ],
            _ignore_key=lambda lc, ic: f"{lc}:{ic}",
            _ignore_items_by_keys=lambda keys: events.append(("ignore", keys)) or len(keys),
        )

        bulk_context_flow.ignore_from_bulk(
            fake_app,
            lambda title, message: events.append(("ask", title)) or True,
            lambda title, message: events.append(("info", title, message)),
        )

        self.assertEqual(events[0], "flush")
        self.assertEqual(events[2], ("ignore", {"MOT-:ABC123"}))


if __name__ == "__main__":
    unittest.main()
