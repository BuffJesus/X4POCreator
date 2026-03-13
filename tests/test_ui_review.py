import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_review


class UIReviewTests(unittest.TestCase):
    def test_apply_review_filter_honors_vendor_performance_and_attention(self):
        events = []

        class Tree:
            def get_children(self):
                return ("old",)
            def delete(self, item_id):
                events.append(("delete", item_id))
            def insert(self, parent, where, iid, values):
                events.append(("insert", iid, values))

        fake_app = SimpleNamespace(
            tree=Tree(),
            assigned_items=[
                {
                    "vendor": "MOTION",
                    "line_code": "AER-",
                    "item_code": "A",
                    "description": "Item A",
                    "order_qty": 1,
                    "status": "ok",
                    "why": "",
                    "pack_size": 6,
                    "performance_profile": "steady",
                    "reorder_attention_signal": "review_missed_reorder",
                },
                {
                    "vendor": "SOURCE",
                    "line_code": "AER-",
                    "item_code": "B",
                    "description": "Item B",
                    "order_qty": 1,
                    "status": "ok",
                    "why": "",
                    "pack_size": 6,
                    "performance_profile": "steady",
                    "reorder_attention_signal": "normal",
                },
            ],
            var_vendor_filter=SimpleNamespace(get=lambda: "MOTION"),
            var_review_performance_filter=SimpleNamespace(get=lambda: "Steady"),
            var_review_attention_filter=SimpleNamespace(get=lambda: "Missed Reorder"),
        )

        ui_review.apply_review_filter(fake_app)

        self.assertEqual(events[0], ("delete", "old"))
        self.assertEqual(events[1][0], "insert")
        self.assertEqual(events[1][1], "0")
        self.assertEqual(events[1][2][2], "A")
        self.assertEqual(len(events), 2)


if __name__ == "__main__":
    unittest.main()
