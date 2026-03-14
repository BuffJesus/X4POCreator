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
    def test_get_vendor_policy_preset_returns_normalized_common_template(self):
        preset = shipping_flow.get_vendor_policy_preset("hybrid_friday_2000")

        self.assertEqual(preset["label"], "Friday + 2000")
        self.assertEqual(preset["shipping_policy"], "hybrid_free_day_threshold")
        self.assertEqual(preset["preferred_free_ship_weekdays"], ["Friday"])
        self.assertEqual(preset["free_freight_threshold"], 2000.0)
        self.assertEqual(preset["urgent_release_floor"], 0.0)
        self.assertEqual(preset["urgent_release_mode"], "release_now")
        self.assertEqual(preset["release_lead_business_days"], 1)

    def test_vendor_policy_preset_options_expose_labels_for_ui(self):
        options = shipping_flow.vendor_policy_preset_options()

        self.assertIn(("release_now", "Release Now"), options)
        self.assertIn(("free_day_friday", "Free Day Friday"), options)
        self.assertIn(("threshold_2000", "Threshold 2000"), options)
        self.assertIn(("hybrid_friday_2000", "Friday + 2000"), options)
        self.assertIn(("paid_urgent_friday_2000", "Friday + 2000 + Paid Urgent"), options)

    def test_resolve_vendor_policy_prefers_saved_policy_over_default_preset(self):
        policy, source, label = shipping_flow.resolve_vendor_policy(
            "motion",
            {"MOTION": {"shipping_policy": "hold_for_threshold", "free_freight_threshold": 2000}},
            "free_day_friday",
        )

        self.assertEqual(policy["shipping_policy"], "hold_for_threshold")
        self.assertEqual(source, "saved_policy")
        self.assertEqual(label, "")

    def test_resolve_vendor_policy_can_use_default_preset_when_vendor_has_no_saved_policy(self):
        policy, source, label = shipping_flow.resolve_vendor_policy("motion", {}, "free_day_friday")

        self.assertEqual(policy["shipping_policy"], "hold_for_free_day")
        self.assertEqual(policy["preferred_free_ship_weekdays"], ["Friday"])
        self.assertEqual(source, "default_preset")
        self.assertEqual(label, "Free Day Friday")

    def test_normalize_vendor_policy_defaults_unknown_urgent_mode_to_release_now(self):
        policy = shipping_flow.normalize_vendor_policy({
            "shipping_policy": "hold_for_free_day",
            "urgent_release_mode": "something_else",
        })

        self.assertEqual(policy["urgent_release_mode"], "release_now")

    def test_normalize_vendor_policy_clamps_invalid_values_and_irrelevant_fields(self):
        policy = shipping_flow.normalize_vendor_policy({
            "shipping_policy": "not_real",
            "preferred_free_ship_weekdays": "Fri, Noday",
            "free_freight_threshold": "-200",
            "urgent_release_floor": "-5",
            "urgent_release_mode": "also_bad",
            "release_lead_business_days": "-2",
        })

        self.assertEqual(policy["shipping_policy"], "release_immediately")
        self.assertEqual(policy["preferred_free_ship_weekdays"], [])
        self.assertEqual(policy["free_freight_threshold"], 0.0)
        self.assertEqual(policy["urgent_release_floor"], 0.0)
        self.assertEqual(policy["urgent_release_mode"], "release_now")
        self.assertEqual(policy["release_lead_business_days"], 1)

    def test_normalize_vendor_policy_clears_unused_fields_for_specific_policy_types(self):
        free_day = shipping_flow.normalize_vendor_policy({
            "shipping_policy": "hold_for_free_day",
            "preferred_free_ship_weekdays": "Fri",
            "free_freight_threshold": 2000,
        })
        threshold = shipping_flow.normalize_vendor_policy({
            "shipping_policy": "hold_for_threshold",
            "preferred_free_ship_weekdays": "Fri",
            "free_freight_threshold": 2000,
            "release_lead_business_days": 3,
        })

        self.assertEqual(free_day["preferred_free_ship_weekdays"], ["Friday"])
        self.assertEqual(free_day["free_freight_threshold"], 0.0)
        self.assertEqual(free_day["release_lead_business_days"], 1)
        self.assertEqual(threshold["preferred_free_ship_weekdays"], [])
        self.assertEqual(threshold["free_freight_threshold"], 2000.0)
        self.assertEqual(threshold["release_lead_business_days"], 1)

    def test_normalize_vendor_policy_keeps_configured_lead_days_for_free_day_policies(self):
        policy = shipping_flow.normalize_vendor_policy({
            "shipping_policy": "hold_for_free_day",
            "preferred_free_ship_weekdays": "Fri",
            "release_lead_business_days": 2,
        })

        self.assertEqual(policy["release_lead_business_days"], 2)

    def test_release_bucket_classifies_release_states(self):
        self.assertEqual(shipping_flow.release_bucket({"release_decision": "release_now"}), "release_now")
        self.assertEqual(
            shipping_flow.release_bucket({"release_decision": "export_next_business_day_for_free_day"}),
            "planned_today",
        )
        self.assertEqual(shipping_flow.release_bucket({"release_decision": "hold_for_threshold"}), "held")

    def test_item_recommended_action_distinguishes_export_review_and_hold_states(self):
        self.assertEqual(
            shipping_flow.item_recommended_action({"release_decision": "release_now"}),
            "Export Now",
        )
        self.assertEqual(
            shipping_flow.item_recommended_action({"release_decision": "release_now", "status": "review"}),
            "Review Before Export",
        )
        self.assertEqual(
            shipping_flow.item_recommended_action({"release_decision": "export_next_business_day_for_free_day"}),
            "Export Planned Today",
        )
        self.assertEqual(
            shipping_flow.item_recommended_action({"release_decision": "hold_for_threshold", "target_order_date": "2026-03-20"}),
            "Hold Until 2026-03-20",
        )
        self.assertEqual(
            shipping_flow.item_recommended_action({"release_decision": "hold_for_threshold", "status": "review"}),
            "Review Critical Hold",
        )

    def test_release_timing_mode_maps_policy_shapes(self):
        self.assertEqual(
            shipping_flow.release_timing_mode({"shipping_policy": "release_immediately"}),
            "same_day_release",
        )
        self.assertEqual(
            shipping_flow.release_timing_mode({"shipping_policy": "hold_for_threshold"}),
            "release_on_threshold",
        )
        self.assertEqual(
            shipping_flow.release_timing_mode({"shipping_policy": "hold_for_free_day", "release_lead_business_days": 0}),
            "release_on_target_ship_day",
        )
        self.assertEqual(
            shipping_flow.release_timing_mode({"shipping_policy": "hold_for_free_day", "release_lead_business_days": 1}),
            "release_one_business_day_before_ship_day",
        )
        self.assertEqual(
            shipping_flow.release_timing_mode({"shipping_policy": "hybrid_free_day_threshold", "release_lead_business_days": 2}),
            "vendor_specific_lead_days",
        )

    def test_vendor_release_plan_status_distinguishes_release_postures(self):
        self.assertEqual(
            shipping_flow.vendor_release_plan_status({
                "release_now_count": 1,
                "planned_today_count": 0,
                "held_count": 0,
            }),
            "release_now",
        )
        self.assertEqual(
            shipping_flow.vendor_release_plan_status({
                "shipping_policy": "hold_for_threshold",
                "release_now_count": 0,
                "planned_today_count": 0,
                "held_count": 2,
                "vendor_threshold_shortfall": 50,
            }),
            "hold_accumulating_to_threshold",
        )
        self.assertEqual(
            shipping_flow.vendor_release_plan_status({
                "shipping_policy": "hold_for_free_day",
                "release_now_count": 0,
                "planned_today_count": 1,
                "held_count": 0,
                "release_timing_mode": "release_on_target_ship_day",
            }),
            "release_on_next_free_ship_day",
        )
        self.assertEqual(
            shipping_flow.vendor_release_plan_status({
                "shipping_policy": "hold_for_free_day",
                "release_now_count": 0,
                "planned_today_count": 1,
                "held_count": 0,
                "release_timing_mode": "release_one_business_day_before_ship_day",
            }),
            "release_on_order_ahead_date",
        )

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
                "release_timing_mode": "same_day_release",
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
                "release_timing_mode": "release_one_business_day_before_ship_day",
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
                "release_timing_mode": "release_on_threshold",
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
        self.assertEqual(row["release_timing_mode"], "same_day_release")
        self.assertEqual(row["release_plan_status"], "release_now")
        self.assertEqual(row["release_plan_label"], "Release Now")
        self.assertEqual(row["recommended_action"], "Export All Due")

    def test_vendor_recommended_action_prefers_critical_holds_and_threshold_waiting(self):
        self.assertEqual(
            shipping_flow.vendor_recommended_action({
                "critical_held_count": 1,
                "release_now_count": 0,
                "planned_today_count": 0,
                "held_count": 1,
                "release_plan_status": "hold_accumulating_to_threshold",
            }),
            "Review Critical Holds",
        )
        self.assertEqual(
            shipping_flow.vendor_recommended_action({
                "critical_held_count": 0,
                "release_now_count": 0,
                "planned_today_count": 0,
                "held_count": 2,
                "release_plan_status": "hold_accumulating_to_threshold",
            }),
            "Wait for Threshold",
        )

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
        self.assertEqual(item["recommended_action"], "Hold Until 2026-03-12")
        self.assertIn("Release:", item["why"])
        self.assertIn("Release lead days: 1", item["why"])
        self.assertIn("Timing mode: release_one_business_day_before_ship_day", item["why"])
        self.assertIn("Target order date: 2026-03-12", item["why"])
        self.assertIn("Target release date: 2026-03-13", item["why"])

    def test_annotate_release_decisions_can_apply_user_default_vendor_policy_preset(self):
        session = AppSessionState(
            default_vendor_policy_preset="free_day_friday",
            inventory_lookup={("AER-", "GH781-4"): {"repl_cost": 2.0}},
            vendor_policies={},
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
        self.assertEqual(item["shipping_policy"], "hold_for_free_day")
        self.assertEqual(item["shipping_policy_source"], "default_preset")
        self.assertEqual(item["shipping_policy_preset_label"], "Free Day Friday")
        self.assertEqual(item["release_decision"], "hold_for_free_day")
        self.assertEqual(item["recommended_action"], "Hold Until 2026-03-12")
        self.assertIn("Shipping policy source: default vendor preset (Free Day Friday)", item["why"])

    def test_annotate_release_decisions_saved_vendor_policy_beats_default_preset(self):
        session = AppSessionState(
            default_vendor_policy_preset="free_day_friday",
            inventory_lookup={("AER-", "GH781-4"): {"repl_cost": 2.0}},
            vendor_policies={
                "MOTION": {
                    "shipping_policy": "hold_for_threshold",
                    "free_freight_threshold": 2000,
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
        self.assertEqual(item["shipping_policy"], "hold_for_threshold")
        self.assertEqual(item["shipping_policy_source"], "saved_policy")
        self.assertEqual(item["shipping_policy_preset_label"], "")

    def test_annotate_release_decisions_uses_vendor_release_lead_days_for_planned_export(self):
        session = AppSessionState(
            inventory_lookup={("AER-", "GH781-4"): {"repl_cost": 2.0}},
            vendor_policies={
                "MOTION": {
                    "shipping_policy": "hold_for_free_day",
                    "preferred_free_ship_weekdays": ["Friday"],
                    "release_lead_business_days": 2,
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
        self.assertEqual(item["release_decision"], "export_next_business_day_for_free_day")
        self.assertEqual(item["release_lead_business_days"], 2)
        self.assertEqual(item["next_free_ship_date"], "2026-03-13")
        self.assertEqual(item["planned_export_date"], "2026-03-11")
        self.assertEqual(item["target_order_date"], "2026-03-11")
        self.assertEqual(item["target_release_date"], "2026-03-13")
        self.assertEqual(item["release_timing_mode"], "vendor_specific_lead_days")
        self.assertIn("Release lead days: 2", item["why"])

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
        self.assertEqual(item["release_trigger"], "urgent_floor")

    def test_annotate_release_decisions_can_use_paid_urgent_freight_override(self):
        session = AppSessionState(
            inventory_lookup={("AER-", "GH781-4"): {"repl_cost": 1.0}},
            vendor_policies={
                "SOURCE": {
                    "shipping_policy": "hold_for_free_day",
                    "preferred_free_ship_weekdays": ["Friday"],
                    "urgent_release_floor": 5,
                    "urgent_release_mode": "paid_urgent_freight",
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
        self.assertEqual(item["release_decision"], "release_now_paid_urgent_freight")
        self.assertEqual(item["release_trigger"], "urgent_floor")
        self.assertEqual(item["urgent_release_mode"], "paid_urgent_freight")
        self.assertIn("paid urgent freight", item["release_reason"])
        self.assertIn("Urgent override: paid_urgent_freight", item["why"])

    def test_annotate_release_decisions_consolidates_vendor_when_one_item_is_urgent(self):
        session = AppSessionState(
            inventory_lookup={
                ("AER-", "GH781-4"): {"repl_cost": 1.0},
                ("AER-", "GH781-5"): {"repl_cost": 1.0},
            },
            vendor_policies={
                "SOURCE": {
                    "shipping_policy": "hold_for_free_day",
                    "preferred_free_ship_weekdays": ["Friday"],
                    "urgent_release_floor": 5,
                }
            },
            filtered_items=[
                {
                    "line_code": "AER-",
                    "item_code": "GH781-4",
                    "vendor": "SOURCE",
                    "final_qty": 12,
                    "order_qty": 12,
                    "inventory_position": 3,
                    "core_why": "Urgent item",
                    "why": "Urgent item",
                },
                {
                    "line_code": "AER-",
                    "item_code": "GH781-5",
                    "vendor": "SOURCE",
                    "final_qty": 8,
                    "order_qty": 8,
                    "inventory_position": 20,
                    "core_why": "Held sibling",
                    "why": "Held sibling",
                },
            ],
        )

        shipping_flow.annotate_release_decisions(session, now=datetime(2026, 3, 11, 12, 0, 0))

        urgent = session.filtered_items[0]
        sibling = session.filtered_items[1]
        self.assertEqual(urgent["release_decision"], "release_now")
        self.assertEqual(urgent["release_trigger"], "urgent_floor")
        self.assertEqual(sibling["release_decision"], "release_now")
        self.assertEqual(sibling["release_trigger"], "vendor_urgent_consolidation")
        self.assertIn("urgent vendor item", sibling["release_reason"])
        self.assertEqual(sibling["target_order_date"], "2026-03-11")
        self.assertEqual(sibling["target_release_date"], "2026-03-11")
        self.assertIn("vendor PO stays consolidated", sibling["why"])

    def test_annotate_release_decisions_consolidates_vendor_into_paid_urgent_freight_when_configured(self):
        session = AppSessionState(
            inventory_lookup={
                ("AER-", "GH781-4"): {"repl_cost": 1.0},
                ("AER-", "GH781-5"): {"repl_cost": 1.0},
            },
            vendor_policies={
                "SOURCE": {
                    "shipping_policy": "hold_for_threshold",
                    "free_freight_threshold": 2000,
                    "urgent_release_floor": 5,
                    "urgent_release_mode": "paid_urgent_freight",
                }
            },
            filtered_items=[
                {
                    "line_code": "AER-",
                    "item_code": "GH781-4",
                    "vendor": "SOURCE",
                    "final_qty": 12,
                    "order_qty": 12,
                    "inventory_position": 3,
                    "core_why": "Urgent item",
                    "why": "Urgent item",
                },
                {
                    "line_code": "AER-",
                    "item_code": "GH781-5",
                    "vendor": "SOURCE",
                    "final_qty": 8,
                    "order_qty": 8,
                    "inventory_position": 20,
                    "core_why": "Held sibling",
                    "why": "Held sibling",
                },
            ],
        )

        shipping_flow.annotate_release_decisions(session, now=datetime(2026, 3, 11, 12, 0, 0))

        sibling = session.filtered_items[1]
        self.assertEqual(sibling["release_decision"], "release_now_paid_urgent_freight")
        self.assertEqual(sibling["release_trigger"], "vendor_urgent_consolidation")
        self.assertIn("paid urgent freight", sibling["release_reason"])

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
