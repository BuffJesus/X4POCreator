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

    def test_release_decision_detail_label_maps_known_values(self):
        self.assertEqual(
            shipping_flow.release_decision_detail_label("release_now_threshold_reached"),
            "Release now: threshold reached",
        )
        self.assertEqual(
            shipping_flow.release_decision_detail_label("hold_until_free_day"),
            "Hold until free-ship day",
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

    def test_shipping_planning_dates_returns_next_free_day_and_previous_business_day(self):
        result = shipping_flow.shipping_planning_dates(
            {"shipping_policy": "hold_for_free_day", "preferred_free_ship_weekdays": ["Friday"], "release_lead_business_days": 1},
            now=datetime(2026, 3, 11, 12, 0, 0),
        )

        self.assertEqual(result["next_free_ship_date"].isoformat(), "2026-03-13")
        self.assertEqual(result["planned_export_date"].isoformat(), "2026-03-12")
        self.assertEqual(result["release_lead_business_days"], 1)
        self.assertEqual(result["release_timing_mode"], "release_one_business_day_before_ship_day")

    def test_shipping_planning_dates_skips_weekend_for_monday_free_day(self):
        result = shipping_flow.shipping_planning_dates(
            {"shipping_policy": "hold_for_free_day", "preferred_free_ship_weekdays": ["Monday"], "release_lead_business_days": 1},
            now=datetime(2026, 3, 13, 12, 0, 0),
        )

        self.assertEqual(result["next_free_ship_date"].isoformat(), "2026-03-16")
        self.assertEqual(result["planned_export_date"].isoformat(), "2026-03-13")

    def test_shipping_planning_dates_handles_two_business_day_lead_across_weekend(self):
        result = shipping_flow.shipping_planning_dates(
            {"shipping_policy": "hold_for_free_day", "preferred_free_ship_weekdays": ["Monday"], "release_lead_business_days": 2},
            now=datetime(2026, 3, 12, 12, 0, 0),
        )

        self.assertEqual(result["next_free_ship_date"].isoformat(), "2026-03-16")
        self.assertEqual(result["planned_export_date"].isoformat(), "2026-03-12")
        self.assertEqual(result["release_timing_mode"], "vendor_specific_lead_days")

    def test_shipping_planning_dates_returns_none_dates_without_free_day(self):
        result = shipping_flow.shipping_planning_dates(
            {"shipping_policy": "hold_for_threshold", "preferred_free_ship_weekdays": [], "release_lead_business_days": 1},
            now=datetime(2026, 3, 11, 12, 0, 0),
        )

        self.assertIsNone(result["next_free_ship_date"])
        self.assertIsNone(result["planned_export_date"])
        self.assertEqual(result["release_timing_mode"], "release_on_threshold")

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
        self.assertEqual(
            shipping_flow.vendor_release_plan_status({
                "release_now_count": 2,
                "planned_today_count": 0,
                "held_count": 0,
                "paid_urgent_count": 1,
            }),
            "release_now_paid_urgent",
        )
        self.assertEqual(
            shipping_flow.vendor_release_plan_status({
                "release_now_count": 2,
                "planned_today_count": 0,
                "held_count": 0,
                "urgent_release_count": 1,
                "vendor_urgent_consolidation_count": 1,
            }),
            "release_now_urgent",
        )

    def test_vendor_release_detail_label_summarizes_urgent_vendor_state(self):
        self.assertEqual(
            shipping_flow.vendor_release_detail_label({
                "paid_urgent_count": 1,
                "vendor_urgent_consolidation_count": 2,
            }),
            "Paid urgent freight + vendor consolidation",
        )
        self.assertEqual(
            shipping_flow.vendor_release_detail_label({
                "urgent_release_count": 1,
                "vendor_urgent_consolidation_count": 2,
            }),
            "Urgent floor + vendor consolidation",
        )
        self.assertEqual(
            shipping_flow.vendor_release_detail_label({
                "release_decision_detail_label": "Release now: threshold reached",
            }),
            "Release now: threshold reached",
        )

    def test_item_cost_data_classifies_inventory_cost_source(self):
        inventory_lookup = {("AER-", "GH781-4"): {"repl_cost": 2.5}}

        result = shipping_flow.item_cost_data(
            {"line_code": "AER-", "item_code": "GH781-4", "final_qty": 4},
            inventory_lookup,
        )

        self.assertEqual(result["source"], "inventory_repl_cost")
        self.assertEqual(result["source_label"], "Inventory repl_cost")
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["unit_cost"], 2.5)
        self.assertEqual(result["estimated_order_value"], 10.0)

    def test_item_cost_data_distinguishes_missing_zero_and_invalid_costs(self):
        inventory_lookup = {
            ("AER-", "MISS"): {},
            ("AER-", "ZERO"): {"repl_cost": 0},
            ("AER-", "BAD"): {"repl_cost": "oops"},
        }

        missing = shipping_flow.item_cost_data(
            {"line_code": "AER-", "item_code": "MISS", "final_qty": 4},
            inventory_lookup,
        )
        zero = shipping_flow.item_cost_data(
            {"line_code": "AER-", "item_code": "ZERO", "final_qty": 4},
            inventory_lookup,
        )
        invalid = shipping_flow.item_cost_data(
            {"line_code": "AER-", "item_code": "BAD", "final_qty": 4},
            inventory_lookup,
        )

        self.assertEqual(missing["source"], "missing_repl_cost")
        self.assertEqual(zero["source"], "zero_repl_cost")
        self.assertEqual(invalid["source"], "invalid_repl_cost")
        self.assertEqual(missing["estimated_order_value"], 0.0)
        self.assertEqual(zero["estimated_order_value"], 0.0)
        self.assertEqual(invalid["estimated_order_value"], 0.0)
        self.assertEqual(zero["source_label"], "Zero inventory repl_cost")
        self.assertEqual(invalid["source_label"], "Invalid inventory repl_cost")

    def test_item_cost_data_classifies_suspicious_cost(self):
        # Costs above $500k or below $0.0001 are suspicious (possible stale/data-entry error)
        inventory_lookup = {
            ("AER-", "HUGE"): {"repl_cost": 500_001.0},
            ("AER-", "TINY"): {"repl_cost": 0.00005},
            ("AER-", "EDGE_HI"): {"repl_cost": 500_000.0},
            ("AER-", "EDGE_LO"): {"repl_cost": 0.0001},
        }

        huge = shipping_flow.item_cost_data(
            {"line_code": "AER-", "item_code": "HUGE", "final_qty": 1},
            inventory_lookup,
        )
        tiny = shipping_flow.item_cost_data(
            {"line_code": "AER-", "item_code": "TINY", "final_qty": 1},
            inventory_lookup,
        )
        edge_hi = shipping_flow.item_cost_data(
            {"line_code": "AER-", "item_code": "EDGE_HI", "final_qty": 1},
            inventory_lookup,
        )
        edge_lo = shipping_flow.item_cost_data(
            {"line_code": "AER-", "item_code": "EDGE_LO", "final_qty": 1},
            inventory_lookup,
        )

        self.assertEqual(huge["source"], "suspicious_repl_cost")
        self.assertEqual(tiny["source"], "suspicious_repl_cost")
        # Boundary values are not suspicious
        self.assertEqual(edge_hi["source"], "inventory_repl_cost")
        self.assertEqual(edge_lo["source"], "inventory_repl_cost")
        # Suspicious costs yield zero estimated value (not usable for shipping calculations)
        self.assertEqual(huge["estimated_order_value"], 0.0)
        self.assertEqual(tiny["estimated_order_value"], 0.0)

    def test_build_vendor_value_coverage_tracks_suspicious_cost(self):
        coverage = shipping_flow.build_vendor_value_coverage(
            [
                {"vendor": "MOTION", "line_code": "AER-", "item_code": "GOOD", "final_qty": 2},
                {"vendor": "MOTION", "line_code": "AER-", "item_code": "HUGE", "final_qty": 2},
                {"vendor": "MOTION", "line_code": "AER-", "item_code": "TINY", "final_qty": 2},
            ],
            {
                ("AER-", "GOOD"): {"repl_cost": 5.0},
                ("AER-", "HUGE"): {"repl_cost": 999_999.0},
                ("AER-", "TINY"): {"repl_cost": 0.000001},
            },
        )

        entry = coverage["MOTION"]
        self.assertEqual(entry["suspicious_cost"], 2)
        self.assertEqual(entry["known"], 1)
        self.assertEqual(entry["unknown"], 2)

    def test_build_vendor_value_coverage_tracks_confidence_and_cost_issue_counts(self):
        coverage = shipping_flow.build_vendor_value_coverage(
            [
                {"vendor": "MOTION", "line_code": "AER-", "item_code": "GOOD", "final_qty": 2},
                {"vendor": "MOTION", "line_code": "AER-", "item_code": "ZERO", "final_qty": 2},
                {"vendor": "MOTION", "line_code": "AER-", "item_code": "BAD", "final_qty": 2},
                {"vendor": "MOTION", "line_code": "AER-", "item_code": "MISS", "final_qty": 2},
            ],
            {
                ("AER-", "GOOD"): {"repl_cost": 5.0},
                ("AER-", "ZERO"): {"repl_cost": 0.0},
                ("AER-", "BAD"): {"repl_cost": "oops"},
                ("AER-", "MISS"): {},
            },
        )

        entry = coverage["MOTION"]
        self.assertEqual(entry["label"], "partial")
        self.assertEqual(entry["confidence"], "medium")
        self.assertEqual(entry["known"], 1)
        self.assertEqual(entry["unknown"], 3)
        self.assertEqual(entry["missing_cost"], 1)
        self.assertEqual(entry["zero_cost"], 1)
        self.assertEqual(entry["invalid_cost"], 1)
        self.assertEqual(entry["known_value_total"], 10.0)
        self.assertEqual(entry["known_pct"], 25.0)

    def test_build_vendor_release_plan_aggregates_counts_and_values(self):
        rows = shipping_flow.build_vendor_release_plan([
            {
                "vendor": "MOTION",
                "final_qty": 2,
                "estimated_order_value": 20.0,
                "release_decision": "release_now",
                "vendor_order_value_total": 45.0,
                "vendor_threshold_current_total": 45.0,
                "vendor_threshold_shortfall": 55.0,
                "vendor_threshold_progress_pct": 45.0,
                "vendor_value_coverage": "partial",
                "vendor_value_confidence": "medium",
                "vendor_value_known_pct": 50.0,
                "vendor_value_known_items": 1,
                "vendor_value_unknown_items": 1,
                "vendor_value_missing_cost_items": 0,
                "vendor_value_zero_cost_items": 1,
                "vendor_value_invalid_cost_items": 0,
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
                "vendor_threshold_current_total": 45.0,
                "vendor_threshold_shortfall": 55.0,
                "vendor_threshold_progress_pct": 45.0,
                "vendor_value_coverage": "partial",
                "vendor_value_confidence": "medium",
                "vendor_value_known_pct": 50.0,
                "vendor_value_known_items": 1,
                "vendor_value_unknown_items": 1,
                "vendor_value_missing_cost_items": 0,
                "vendor_value_zero_cost_items": 1,
                "vendor_value_invalid_cost_items": 0,
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
                "vendor_threshold_current_total": 45.0,
                "vendor_threshold_shortfall": 55.0,
                "vendor_threshold_progress_pct": 45.0,
                "vendor_value_coverage": "partial",
                "vendor_value_confidence": "medium",
                "vendor_value_known_pct": 50.0,
                "vendor_value_known_items": 1,
                "vendor_value_unknown_items": 1,
                "vendor_value_missing_cost_items": 0,
                "vendor_value_zero_cost_items": 1,
                "vendor_value_invalid_cost_items": 0,
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
        self.assertEqual(row["vendor_threshold_current_total"], 45.0)
        self.assertEqual(row["vendor_threshold_shortfall"], 55.0)
        self.assertEqual(row["vendor_value_confidence"], "medium")
        self.assertEqual(row["vendor_value_known_pct"], 50.0)
        self.assertEqual(row["vendor_value_zero_cost_items"], 1)
        self.assertEqual(row["next_free_ship_date"], "2026-03-13")
        self.assertEqual(row["release_timing_mode"], "same_day_release")
        self.assertEqual(row["release_plan_status"], "release_now")
        self.assertEqual(row["release_plan_label"], "Release Now")
        self.assertEqual(row["recommended_action"], "Review Value Coverage")

    def test_build_vendor_release_plan_summarizes_urgent_vendor_consolidation(self):
        rows = shipping_flow.build_vendor_release_plan([
            {
                "vendor": "MOTION",
                "final_qty": 1,
                "estimated_order_value": 20.0,
                "release_decision": "release_now_paid_urgent_freight",
                "release_decision_detail": "release_now_paid_urgent_freight",
                "release_trigger": "urgent_floor",
                "vendor_order_value_total": 30.0,
                "vendor_value_coverage": "complete",
                "vendor_value_confidence": "high",
            },
            {
                "vendor": "MOTION",
                "final_qty": 1,
                "estimated_order_value": 10.0,
                "release_decision": "release_now_paid_urgent_freight",
                "release_decision_detail": "release_now_paid_urgent_vendor_consolidation",
                "release_trigger": "vendor_urgent_consolidation",
                "vendor_order_value_total": 30.0,
                "vendor_value_coverage": "complete",
                "vendor_value_confidence": "high",
            },
        ])

        row = rows[0]
        self.assertEqual(row["urgent_release_count"], 1)
        self.assertEqual(row["vendor_urgent_consolidation_count"], 1)
        self.assertEqual(row["paid_urgent_count"], 2)
        self.assertEqual(row["release_plan_status"], "release_now_paid_urgent")
        self.assertEqual(row["release_plan_label"], "Release Now: Paid Urgent")
        self.assertEqual(row["release_decision_detail_label"], "Paid urgent freight + vendor consolidation")
        self.assertEqual(row["recommended_action"], "Review Paid Urgent Freight")

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

    def test_vendor_recommended_action_prefers_value_coverage_review_before_export(self):
        self.assertEqual(
            shipping_flow.vendor_recommended_action({
                "critical_held_count": 0,
                "release_now_count": 1,
                "planned_today_count": 0,
                "held_count": 0,
                "vendor_value_coverage": "partial",
                "vendor_value_confidence": "medium",
                "vendor_value_unknown_items": 1,
            }),
            "Review Value Coverage",
        )

    def test_vendor_recommended_action_prioritizes_urgent_vendor_workflow(self):
        self.assertEqual(
            shipping_flow.vendor_recommended_action({
                "critical_held_count": 0,
                "release_now_count": 2,
                "planned_today_count": 0,
                "held_count": 0,
                "paid_urgent_count": 1,
                "vendor_value_coverage": "partial",
                "vendor_value_confidence": "medium",
                "vendor_value_unknown_items": 1,
            }),
            "Review Paid Urgent Freight",
        )
        self.assertEqual(
            shipping_flow.vendor_recommended_action({
                "critical_held_count": 0,
                "release_now_count": 2,
                "planned_today_count": 0,
                "held_count": 0,
                "vendor_urgent_consolidation_count": 1,
                "urgent_release_count": 1,
            }),
            "Export Urgent Consolidated Now",
        )
        self.assertEqual(
            shipping_flow.vendor_recommended_action({
                "critical_held_count": 0,
                "release_now_count": 1,
                "planned_today_count": 0,
                "held_count": 0,
                "urgent_release_count": 1,
            }),
            "Export Urgent Now",
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
        self.assertEqual(item["release_decision_detail"], "hold_until_free_day")
        self.assertEqual(item["release_decision_detail_label"], "Hold until free-ship day")
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
        self.assertEqual(item["release_decision_detail"], "export_next_business_day_for_free_day")
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
        self.assertEqual(first["release_decision_detail"], "release_now_threshold_reached")
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
        self.assertEqual(item["release_decision_detail"], "release_now_urgent_floor")
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
        self.assertEqual(item["release_decision_detail"], "release_now_paid_urgent_freight")
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
        self.assertEqual(sibling["release_decision_detail"], "release_now_vendor_urgent_consolidation")
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
        self.assertEqual(sibling["release_decision_detail"], "release_now_paid_urgent_vendor_consolidation")
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

    def test_annotate_release_decisions_monday_free_day_uses_previous_friday_export(self):
        session = AppSessionState(
            inventory_lookup={("AER-", "GH781-4"): {"repl_cost": 2.0}},
            vendor_policies={
                "MOTION": {
                    "shipping_policy": "hold_for_free_day",
                    "preferred_free_ship_weekdays": ["Monday"],
                    "release_lead_business_days": 1,
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

        shipping_flow.annotate_release_decisions(session, now=datetime(2026, 3, 13, 12, 0, 0))

        item = session.filtered_items[0]
        self.assertEqual(item["release_decision"], "export_next_business_day_for_free_day")
        self.assertEqual(item["next_free_ship_date"], "2026-03-16")
        self.assertEqual(item["planned_export_date"], "2026-03-13")
        self.assertEqual(item["target_order_date"], "2026-03-13")
        self.assertEqual(item["target_release_date"], "2026-03-16")

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
        self.assertEqual(first["estimated_order_value_source"], "inventory_repl_cost")
        self.assertEqual(first["estimated_order_value_confidence"], "high")
        self.assertEqual(first["vendor_order_value_total"], 100.0)
        self.assertEqual(first["vendor_threshold_current_total"], 100.0)
        self.assertEqual(first["vendor_threshold_shortfall"], 100.0)
        self.assertEqual(first["vendor_threshold_progress_pct"], 50.0)
        self.assertEqual(first["vendor_value_coverage"], "partial")
        self.assertEqual(first["vendor_value_confidence"], "medium")
        self.assertEqual(first["vendor_value_known_pct"], 50.0)
        self.assertEqual(first["vendor_value_zero_cost_items"], 1)
        self.assertIn("Vendor threshold progress: 100/200", first["why"])
        self.assertIn("Vendor value coverage: partial (medium confidence; 1 known, 1 unknown, zero cost 1)", first["why"])

        second = session.assigned_items[1]
        self.assertEqual(second["estimated_order_value_source"], "zero_repl_cost")
        self.assertEqual(second["estimated_order_value_confidence"], "low")
        self.assertIn("Estimated value source: Zero inventory repl_cost", second["why"])


if __name__ == "__main__":
    unittest.main()
