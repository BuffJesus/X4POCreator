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
    def test_release_bucket_classifies_release_states(self):
        self.assertEqual(shipping_flow.release_bucket({"release_decision": "release_now"}), "release_now")
        self.assertEqual(
            shipping_flow.release_bucket({"release_decision": "export_next_business_day_for_free_day"}),
            "planned_today",
        )
        self.assertEqual(shipping_flow.release_bucket({"release_decision": "hold_for_threshold"}), "held")

    def test_build_vendor_release_plan_aggregates_counts_and_values(self):
        rows = shipping_flow.build_vendor_release_plan([
            {
                "vendor": "MOTION",
                "final_qty": 2,
                "estimated_order_value": 20.0,
                "release_decision": "release_now",
                "vendor_order_value_total": 45.0,
                "vendor_threshold_shortfall": 55.0,
                "vendor_threshold_progress_pct": 45.0,
                "vendor_value_coverage": "partial",
                "next_free_ship_date": "2026-03-13",
                "planned_export_date": "2026-03-12",
                "shipping_policy": "hybrid_free_day_threshold",
            },
            {
                "vendor": "MOTION",
                "final_qty": 1,
                "estimated_order_value": 15.0,
                "release_decision": "export_next_business_day_for_free_day",
                "vendor_order_value_total": 45.0,
                "vendor_threshold_shortfall": 55.0,
                "vendor_threshold_progress_pct": 45.0,
                "vendor_value_coverage": "partial",
                "next_free_ship_date": "2026-03-13",
                "planned_export_date": "2026-03-12",
                "shipping_policy": "hybrid_free_day_threshold",
            },
            {
                "vendor": "MOTION",
                "final_qty": 1,
                "estimated_order_value": 10.0,
                "release_decision": "hold_for_threshold",
                "vendor_order_value_total": 45.0,
                "vendor_threshold_shortfall": 55.0,
                "vendor_threshold_progress_pct": 45.0,
                "vendor_value_coverage": "partial",
                "next_free_ship_date": "2026-03-13",
                "planned_export_date": "2026-03-12",
                "shipping_policy": "hybrid_free_day_threshold",
            },
        ])

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["vendor"], "MOTION")
        self.assertEqual(row["release_now_count"], 1)
        self.assertEqual(row["planned_today_count"], 1)
        self.assertEqual(row["held_count"], 1)
        self.assertEqual(row["release_now_value"], 20.0)
        self.assertEqual(row["planned_today_value"], 15.0)
        self.assertEqual(row["held_value"], 10.0)
        self.assertEqual(row["vendor_order_value_total"], 45.0)
        self.assertEqual(row["vendor_threshold_shortfall"], 55.0)
        self.assertEqual(row["next_free_ship_date"], "2026-03-13")

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
        self.assertEqual(item["vendor_value_coverage"], "complete")
        self.assertEqual(item["vendor_threshold_progress_pct"], 100.0)
        self.assertEqual(item["next_free_ship_date"], "2026-03-13")
        self.assertEqual(item["planned_export_date"], "2026-03-12")
        self.assertEqual(item["target_order_date"], "2026-03-12")
        self.assertEqual(item["target_release_date"], "2026-03-13")
        self.assertIn("Release:", item["why"])
        self.assertIn("Target order date: 2026-03-12", item["why"])
        self.assertIn("Target release date: 2026-03-13", item["why"])

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
        self.assertEqual(first["vendor_threshold_shortfall"], 0.0)
        self.assertEqual(first["vendor_threshold_progress_pct"], 100.0)

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

    def test_annotate_release_decisions_exports_on_previous_business_day_for_free_day(self):
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

        shipping_flow.annotate_release_decisions(session, now=datetime(2026, 3, 12, 12, 0, 0))

        item = session.filtered_items[0]
        self.assertEqual(item["release_decision"], "export_next_business_day_for_free_day")
        self.assertIn("ready for vendor free-shipping day", item["release_reason"])
        self.assertEqual(item["next_free_ship_date"], "2026-03-13")
        self.assertEqual(item["planned_export_date"], "2026-03-12")
        self.assertEqual(item["target_order_date"], "2026-03-12")
        self.assertEqual(item["target_release_date"], "2026-03-13")

    def test_annotate_release_decisions_marks_partial_value_coverage_and_threshold_shortfall(self):
        session = AppSessionState(
            inventory_lookup={
                ("AER-", "GH781-4"): {"repl_cost": 10.0},
                ("AER-", "GH781-5"): {"repl_cost": 0.0},
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
        self.assertEqual(first["release_decision"], "hold_for_threshold")
        self.assertEqual(first["vendor_order_value_total"], 100.0)
        self.assertEqual(first["vendor_threshold_shortfall"], 100.0)
        self.assertEqual(first["vendor_threshold_progress_pct"], 50.0)
        self.assertEqual(first["vendor_value_coverage"], "partial")
        self.assertIn("Vendor threshold progress: 100/200", first["why"])
        self.assertIn("Vendor value coverage: partial", first["why"])


if __name__ == "__main__":
    unittest.main()
