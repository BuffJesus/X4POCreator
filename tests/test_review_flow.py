import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import po_builder
import review_flow


class ReviewFlowTests(unittest.TestCase):
    def test_review_refresh_editor_row_renders_current_values(self):
        calls = []
        fake_app = SimpleNamespace(
            assigned_items=[{"item_code": "ABC123"}],
            _review_row_values=lambda item: ("row", item["item_code"]),
            tree=SimpleNamespace(item=lambda row_id, values: calls.append((row_id, values))),
        )

        review_flow.review_refresh_editor_row(fake_app, "0")

        self.assertEqual(calls, [("0", ("row", "ABC123"))])

    def test_review_apply_vendor_updates_summary_and_syncs(self):
        events = []
        fake_app = SimpleNamespace(
            assigned_items=[{"vendor": "OLD"}],
            _remember_vendor_code=lambda value: events.append(("remember", value)),
            _sync_review_item_to_filtered=lambda item: events.append(("sync", item["vendor"])),
            _update_review_summary=lambda: events.append(("summary", None)),
        )

        review_flow.review_apply_editor_value(fake_app, "0", "vendor", "source", po_builder.get_rule_key)

        self.assertEqual(fake_app.assigned_items[0]["vendor"], "SOURCE")
        self.assertEqual(events, [("remember", "SOURCE"), ("sync", "SOURCE"), ("summary", None)])


if __name__ == "__main__":
    unittest.main()
