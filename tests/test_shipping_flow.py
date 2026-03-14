import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import shipping_flow
from models import AppSessionState


class ShippingFlowTests(unittest.TestCase):
    def test_annotate_release_decisions_holds_for_free_day_when_not_today(self):
        session = AppSessionState(
            inventory_lookup={("AER-", "GH781-4"): {"repl_cost": 2.0}},
            vendor_policies={
                "MOTION": {
                    "shipping_policy": "hold_for_free_day",
                    "preferred_free_ship_weekdays": ["Friday"],
                    "urgent_release_floor": 0,
                }
            },
            filtered_items=[{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "vendor": "MOTION",
                "final_qty": 10,
                "order_qty": 10,
                "inventory_position": 6,
                "core_why": "Base why",
                "why": "Base why",
            }],
        )

        shipping_flow.annotate_release_decisions(session, now=datetime(2026, 3, 11, 12, 0, 0))

        item = session.filtered_items[0]
        self.assertEqual(item["release_decision"], "hold_for_free_day")
        self.assertIn("free-shipping day", item["release_reason"])
        self.assertEqual(item["vendor_order_value_total"], 20.0)
        self.assertIn("Release:", item["why"])

    def test_annotate_release_decisions_releases_when_threshold_reached(self):
        session = AppSessionState(
            inventory_lookup={
                ("AER-", "GH781-4"): {"repl_cost": 10.0},
                ("AER-", "GH781-5"): {"repl_cost": 20.0},
            },
            vendor_policies={
                "MOTION": {
                    "shipping_policy": "hold_for_threshold",
                    "free_freight_threshold": 200,
                }
            },
            assigned_items=[
                {
                    "line_code": "AER-",
                    "item_code": "GH781-4",
                    "vendor": "MOTION",
                    "final_qty": 10,
                    "order_qty": 10,
                    "inventory_position": 8,
                    "core_why": "Base why 1",
                    "why": "Base why 1",
                },
                {
                    "line_code": "AER-",
                    "item_code": "GH781-5",
                    "vendor": "MOTION",
                    "final_qty": 6,
                    "order_qty": 6,
                    "inventory_position": 5,
                    "core_why": "Base why 2",
                    "why": "Base why 2",
                },
            ],
        )

        shipping_flow.annotate_release_decisions(session, now=datetime(2026, 3, 11, 12, 0, 0))

        first = session.assigned_items[0]
        self.assertEqual(first["vendor_order_value_total"], 220.0)
        self.assertEqual(first["release_decision"], "release_now")
        self.assertIn("threshold 200", first["release_reason"])

    def test_annotate_release_decisions_urgent_floor_bypasses_hold(self):
        session = AppSessionState(
            inventory_lookup={("AER-", "GH781-4"): {"repl_cost": 1.0}},
            vendor_policies={
                "SOURCE": {
                    "shipping_policy": "hold_for_free_day",
                    "preferred_free_ship_weekdays": ["Friday"],
                    "urgent_release_floor": 5,
                }
            },
            filtered_items=[{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "vendor": "SOURCE",
                "final_qty": 12,
                "order_qty": 12,
                "inventory_position": 3,
                "core_why": "Base why",
                "why": "Base why",
            }],
        )

        shipping_flow.annotate_release_decisions(session, now=datetime(2026, 3, 11, 12, 0, 0))

        item = session.filtered_items[0]
        self.assertEqual(item["release_decision"], "release_now")
        self.assertIn("urgent floor 5", item["release_reason"])


if __name__ == "__main__":
    unittest.main()
