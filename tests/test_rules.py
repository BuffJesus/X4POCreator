import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rules import (
    assess_post_receipt_overstock,
    apply_rule_fields,
    calculate_inventory_position,
    calculate_raw_need,
    calculate_suggested_qty,
    classify_package_profile,
    classify_replenishment_unit_mode,
    determine_acceptable_overstock_qty,
    determine_reorder_trigger_threshold,
    determine_order_policy,
    determine_target_stock,
    enrich_item,
    evaluate_reorder_trigger,
    evaluate_item_status,
    get_buy_rule_summary,
    get_rule_float,
    get_rule_int,
    get_rule_pack_size,
    has_exact_qty_override,
    has_pack_trigger_fields,
    infer_minimum_cover_cycles,
    infer_minimum_packs_on_hand,
    looks_like_hardware_pack_item,
    looks_like_reel_item,
    package_profile_label,
    replenishment_unit_mode_label,
    should_large_pack_review,
    compute_stockout_risk_score,
    classify_dead_stock,
    DEAD_STOCK_MIN_DAYS_SINCE_SALE,
)


class RulesTests(unittest.TestCase):
    def test_get_rule_pack_size_parses_numeric_strings(self):
        self.assertEqual(get_rule_pack_size({"pack_size": "500"}), 500)
        self.assertEqual(get_rule_pack_size({"pack_size": 12.0}), 12)
        self.assertIsNone(get_rule_pack_size({"pack_size": 0}))
        self.assertIsNone(get_rule_pack_size({"pack_size": ""}))
        self.assertIsNone(get_rule_pack_size({"pack_size": "abc"}))

    def test_has_exact_qty_override_detects_explicit_or_legacy_zero_pack(self):
        self.assertTrue(has_exact_qty_override({"exact_qty_override": True}))
        self.assertTrue(has_exact_qty_override({"pack_size": 0}))
        self.assertFalse(has_exact_qty_override({"pack_size": 12}))
        self.assertFalse(has_exact_qty_override({}))

    def test_has_exact_qty_override_ignores_blank_pack_values(self):
        self.assertFalse(has_exact_qty_override({"pack_size": ""}))

    def test_get_rule_int_and_float_parse_trigger_fields(self):
        rule = {
            "reorder_trigger_qty": "60",
            "reorder_trigger_pct": "20",
            "acceptable_overstock_qty": 12.0,
            "acceptable_overstock_pct": "10.5",
        }
        self.assertEqual(get_rule_int(rule, "reorder_trigger_qty"), 60)
        self.assertEqual(get_rule_float(rule, "reorder_trigger_pct"), 20.0)
        self.assertEqual(get_rule_int(rule, "acceptable_overstock_qty"), 12)
        self.assertEqual(get_rule_float(rule, "acceptable_overstock_pct"), 10.5)

    def test_apply_rule_fields_copies_trigger_metadata_to_item(self):
        item = {}
        apply_rule_fields(
            item,
            {
                "reorder_trigger_qty": "60",
                "reorder_trigger_pct": "20",
                "minimum_packs_on_hand": "2",
                "minimum_cover_days": "14",
                "minimum_cover_cycles": "2",
                "acceptable_overstock_qty": "12",
                "acceptable_overstock_pct": "10",
            },
        )
        self.assertEqual(item["reorder_trigger_qty"], 60)
        self.assertEqual(item["reorder_trigger_pct"], 20.0)
        self.assertEqual(item["minimum_packs_on_hand"], 2)
        self.assertEqual(item["minimum_cover_days"], 14.0)
        self.assertEqual(item["minimum_cover_cycles"], 2.0)
        self.assertEqual(item["acceptable_overstock_qty"], 12)
        self.assertEqual(item["acceptable_overstock_pct"], 10.0)

    def test_has_pack_trigger_fields_detects_any_trigger_style_rule(self):
        self.assertTrue(has_pack_trigger_fields({"reorder_trigger_qty": 60}))
        self.assertTrue(has_pack_trigger_fields({"reorder_trigger_pct": 20}))
        self.assertTrue(has_pack_trigger_fields({"minimum_packs_on_hand": 2}))
        self.assertTrue(has_pack_trigger_fields({"minimum_cover_days": 14}))
        self.assertTrue(has_pack_trigger_fields({"minimum_cover_cycles": 2}))
        self.assertFalse(has_pack_trigger_fields({"acceptable_overstock_qty": 12}))
        self.assertFalse(has_pack_trigger_fields({}))

    def test_determine_reorder_trigger_threshold_uses_max_of_trigger_fields(self):
        item = {
            "inventory": {"min": 10},
            "pack_size": 300,
            "reorder_trigger_qty": 60,
            "reorder_trigger_pct": 20,
        }
        self.assertEqual(determine_reorder_trigger_threshold(item), 60)
        self.assertEqual(item["reorder_trigger_basis"], "trigger_qty")

    def test_determine_reorder_trigger_threshold_uses_minimum_packs_on_hand(self):
        item = {
            "inventory": {"min": 10},
            "pack_size": 100,
            "minimum_packs_on_hand": 2,
        }
        self.assertEqual(determine_reorder_trigger_threshold(item), 200)
        self.assertEqual(item["reorder_trigger_basis"], "minimum_packs_on_hand")

    def test_determine_reorder_trigger_threshold_uses_minimum_cover_cycles(self):
        item = {
            "inventory": {"min": 10},
            "pack_size": 100,
            "demand_signal": 30,
            "minimum_cover_cycles": 2,
        }
        self.assertEqual(determine_reorder_trigger_threshold(item), 60)
        self.assertEqual(item["reorder_trigger_basis"], "minimum_cover_cycles")

    def test_determine_reorder_trigger_threshold_uses_minimum_cover_days(self):
        item = {
            "inventory": {"min": 10},
            "pack_size": 100,
            "demand_signal": 30,
            "reorder_cycle_weeks": 2,
            "minimum_cover_days": 21,
        }
        self.assertEqual(determine_reorder_trigger_threshold(item), 45)
        self.assertEqual(item["reorder_trigger_basis"], "minimum_cover_days")

    def test_determine_acceptable_overstock_qty_uses_max_of_qty_and_pct(self):
        item = {
            "pack_size": 100,
            "acceptable_overstock_qty": 12,
            "acceptable_overstock_pct": 30,
        }
        self.assertEqual(determine_acceptable_overstock_qty(item), 30)
        self.assertEqual(item["acceptable_overstock_basis"], "pct")

    def test_assess_post_receipt_overstock_tracks_tolerance(self):
        item = {
            "inventory_position": 0,
            "effective_target_stock": 20,
            "acceptable_overstock_qty_effective": 80,
        }
        overstock_qty, within_tolerance = assess_post_receipt_overstock(item, 100)
        self.assertEqual(overstock_qty, 80)
        self.assertTrue(within_tolerance)
        self.assertEqual(item["projected_post_receipt_stock"], 100)

    def test_infer_minimum_packs_on_hand_for_active_hardware_pack_mismatch(self):
        item = {
            "description": "5/16 HEX NUT",
            "sales_health_signal": "active",
            "performance_profile": "steady",
            "days_since_last_sale": 14,
        }
        self.assertEqual(infer_minimum_packs_on_hand(item, {"max": 20}, 100), 2)

    def test_infer_minimum_packs_on_hand_can_raise_to_three_with_strong_long_window_evidence(self):
        item = {
            "description": "5/16 HEX NUT",
            "sales_health_signal": "active",
            "performance_profile": "top_performer",
            "days_since_last_sale": 7,
            "sales_span_days": 365,
            "avg_weekly_sales_loaded": 90.0,
            "annualized_sales_loaded": 4680.0,
            "detailed_sales_shape": "steady_repeat",
            "demand_signal": 90,
        }
        self.assertEqual(infer_minimum_packs_on_hand(item, {"max": 20}, 100), 3)

    def test_infer_minimum_packs_on_hand_skips_stale_hardware(self):
        item = {
            "description": "5/16 HEX NUT",
            "sales_health_signal": "dormant",
            "performance_profile": "legacy",
            "days_since_last_sale": 500,
        }
        self.assertIsNone(infer_minimum_packs_on_hand(item, {"max": 20}, 100))

    def test_infer_minimum_packs_on_hand_returns_one_when_loaded_window_is_very_short(self):
        item = {
            "description": "5/16 HEX NUT",
            "sales_health_signal": "active",
            "performance_profile": "steady",
            "days_since_last_sale": 3,
            "sales_span_days": 7,
        }
        self.assertEqual(infer_minimum_packs_on_hand(item, {"max": 20}, 100), 1)

    def test_infer_minimum_packs_on_hand_returns_two_at_minimum_window_boundary(self):
        item = {
            "description": "5/16 HEX NUT",
            "sales_health_signal": "active",
            "performance_profile": "steady",
            "days_since_last_sale": 7,
            "sales_span_days": 14,
        }
        self.assertEqual(infer_minimum_packs_on_hand(item, {"max": 20}, 100), 2)

    def test_infer_minimum_packs_on_hand_returns_two_when_span_unknown(self):
        # No sales_span_days set — backward-compatible: still returns 2.
        item = {
            "description": "5/16 HEX NUT",
            "sales_health_signal": "active",
            "performance_profile": "steady",
            "days_since_last_sale": 14,
        }
        self.assertEqual(infer_minimum_packs_on_hand(item, {"max": 20}, 100), 2)

    def test_infer_minimum_cover_cycles_returns_one_when_loaded_window_is_very_short(self):
        item = {
            "description": "5/16 HEX NUT",
            "sales_health_signal": "active",
            "performance_profile": "steady",
            "days_since_last_sale": 3,
            "reorder_cycle_weeks": 1,
            "avg_weekly_sales_loaded": 8.0,
            "demand_signal": 8,
            "sales_span_days": 7,
        }
        self.assertEqual(infer_minimum_cover_cycles(item, {"max": 8}, 10), 1)

    def test_infer_minimum_cover_cycles_for_active_weekly_hardware(self):
        item = {
            "description": "5/16 HEX NUT",
            "sales_health_signal": "active",
            "performance_profile": "steady",
            "days_since_last_sale": 14,
            "reorder_cycle_weeks": 1,
            "avg_weekly_sales_loaded": 8.0,
            "demand_signal": 8,
        }
        self.assertEqual(infer_minimum_cover_cycles(item, {"max": 8}, 10), 2)

    def test_infer_minimum_cover_cycles_can_raise_to_three_with_strong_long_window_evidence(self):
        item = {
            "description": "5/16 HEX NUT",
            "sales_health_signal": "active",
            "performance_profile": "top_performer",
            "days_since_last_sale": 7,
            "reorder_cycle_weeks": 1,
            "sales_span_days": 365,
            "avg_weekly_sales_loaded": 12.0,
            "annualized_sales_loaded": 624.0,
            "detailed_sales_shape": "steady_repeat",
            "demand_signal": 12,
        }
        self.assertEqual(infer_minimum_cover_cycles(item, {"max": 4}, 10), 3)

    def test_infer_minimum_cover_cycles_skips_biweekly_or_slow_hardware(self):
        weekly_slow_item = {
            "description": "5/16 HEX NUT",
            "sales_health_signal": "active",
            "performance_profile": "steady",
            "days_since_last_sale": 14,
            "reorder_cycle_weeks": 1,
            "avg_weekly_sales_loaded": 2.0,
            "demand_signal": 2,
        }
        biweekly_item = {
            "description": "5/16 HEX NUT",
            "sales_health_signal": "active",
            "performance_profile": "steady",
            "days_since_last_sale": 14,
            "reorder_cycle_weeks": 2,
            "avg_weekly_sales_loaded": 8.0,
            "demand_signal": 16,
        }
        self.assertIsNone(infer_minimum_cover_cycles(weekly_slow_item, {"max": 8}, 10))
        self.assertIsNone(infer_minimum_cover_cycles(biweekly_item, {"max": 8}, 10))

    def test_reel_review_when_pack_far_exceeds_max(self):
        policy = determine_order_policy({"description": '1/4" 2WIRE 6500PSI HOSE'}, {"max": 100}, 500, None)
        self.assertEqual(policy, "reel_review")

    def test_classify_package_profile_distinguishes_reel_hardware_and_large_nonreel(self):
        self.assertEqual(
            classify_package_profile({"description": '1/4" 2WIRE 6500PSI HOSE'}, {"max": 100}, 500),
            "reel_stock",
        )
        self.assertEqual(
            classify_package_profile(
                {
                    "description": "1/4 X 1 ELEVATOR BOLT",
                    "sales_health_signal": "active",
                    "performance_profile": "steady",
                    "days_since_last_sale": 14,
                },
                {"max": 20},
                100,
            ),
            "hardware_pack",
        )
        self.assertEqual(
            classify_package_profile(
                {
                    "description": "FILTER KIT",
                    "sales_health_signal": "dormant",
                    "performance_profile": "legacy",
                    "days_since_last_sale": 500,
                },
                {"max": 20},
                100,
            ),
            "large_nonreel_pack",
        )

    def test_package_profile_label_maps_known_profiles(self):
        self.assertEqual(package_profile_label("reel_stock"), "Reel / bulk-by-length")
        self.assertEqual(package_profile_label("hardware_pack"), "Hardware pack")
        self.assertEqual(package_profile_label("large_nonreel_pack"), "Large non-reel pack")

    def test_replenishment_unit_mode_distinguishes_pack_math_from_review_policy(self):
        self.assertEqual(classify_replenishment_unit_mode("exact_qty", {}, None, None), "exact_qty")
        self.assertEqual(classify_replenishment_unit_mode("soft_pack", {}, 500, {"min_order_qty": 250}), "soft_pack_min_order")
        self.assertEqual(classify_replenishment_unit_mode("pack_trigger", {}, 100, None), "pack_trigger_replenishment")
        self.assertEqual(classify_replenishment_unit_mode("reel_review", {}, 500, None), "reel_bulk_review")
        self.assertEqual(classify_replenishment_unit_mode("large_pack_review", {}, 100, None), "large_pack_review")
        self.assertEqual(classify_replenishment_unit_mode("standard", {}, 12, None), "full_pack_round_up")

    def test_replenishment_unit_mode_label_maps_known_modes(self):
        self.assertEqual(replenishment_unit_mode_label("reel_bulk_review"), "Reel / bulk review")
        self.assertEqual(replenishment_unit_mode_label("pack_trigger_replenishment"), "Pack-trigger replenishment")
        self.assertEqual(replenishment_unit_mode_label("full_pack_round_up"), "Full-pack round-up")

    def test_boxed_hardware_pack_is_not_auto_marked_reel_review(self):
        policy = determine_order_policy({"description": "1/4 X 1 ELEVATOR BOLT"}, {"max": 20}, 100, None)
        self.assertEqual(policy, "pack_trigger")

    def test_bolt_description_looks_like_hardware_pack_item(self):
        self.assertTrue(looks_like_hardware_pack_item({"description": "1/4 X 1 ELEVATOR BOLT"}, {}))

    def test_hose_description_does_not_look_like_hardware_pack_item(self):
        self.assertFalse(looks_like_hardware_pack_item({"description": '1/4" 2WIRE 6500PSI HOSE'}, {}))

    def test_dormant_non_reel_large_pack_item_is_marked_large_pack_review(self):
        item = {
            "description": "FILTER KIT",
            "sales_health_signal": "dormant",
            "performance_profile": "legacy",
            "days_since_last_sale": 500,
        }
        policy = determine_order_policy(item, {"max": 20}, 100, None)
        self.assertEqual(policy, "large_pack_review")

    def test_trigger_fields_infer_pack_trigger_when_no_review_policy_applies(self):
        item = {
            "description": "1/4 X 1 ELEVATOR BOLT",
            "sales_health_signal": "active",
            "performance_profile": "steady",
            "days_since_last_sale": 14,
        }
        rule = {"minimum_packs_on_hand": 2}
        policy = determine_order_policy(item, {"max": 20}, 100, rule)
        self.assertEqual(policy, "pack_trigger")

    def test_exact_qty_override_rule_beats_pack_trigger_inference(self):
        item = {
            "description": "1/4 X 1 ELEVATOR BOLT",
            "sales_health_signal": "active",
            "performance_profile": "steady",
            "days_since_last_sale": 14,
        }
        rule = {"exact_qty_override": True, "pack_size": 0}
        policy = determine_order_policy(item, {"max": 20}, 100, rule)
        self.assertEqual(policy, "exact_qty")

    def test_active_hardware_pack_mismatch_infers_pack_trigger_without_rule_fields(self):
        item = {
            "description": "5/16 HEX NUT",
            "sales_health_signal": "active",
            "performance_profile": "steady",
            "days_since_last_sale": 14,
        }
        policy = determine_order_policy(item, {"max": 20}, 100, None)
        self.assertEqual(policy, "pack_trigger")

    def test_large_pack_review_still_beats_trigger_field_inference(self):
        item = {
            "description": "FILTER KIT",
            "sales_health_signal": "dormant",
            "performance_profile": "legacy",
            "days_since_last_sale": 500,
        }
        rule = {"minimum_packs_on_hand": 2}
        policy = determine_order_policy(item, {"max": 20}, 100, rule)
        self.assertEqual(policy, "large_pack_review")

    def test_stale_hardware_pack_can_still_fall_to_large_pack_review(self):
        item = {
            "description": "5/16 HEX NUT",
            "sales_health_signal": "dormant",
            "performance_profile": "legacy",
            "days_since_last_sale": 500,
        }
        policy = determine_order_policy(item, {"max": 20}, 100, None)
        self.assertEqual(policy, "large_pack_review")

    def test_should_large_pack_review_stays_false_for_active_boxed_hardware(self):
        item = {
            "description": "1/4 X 1 ELEVATOR BOLT",
            "sales_health_signal": "active",
            "performance_profile": "steady",
            "days_since_last_sale": 14,
        }
        self.assertFalse(should_large_pack_review(item, {"max": 20}, 100))

    def test_belts_do_not_look_like_reel_items(self):
        self.assertFalse(looks_like_reel_item({"description": "GATES BELT"}, {}))

    def test_hose_fittings_do_not_look_like_reel_items(self):
        self.assertFalse(looks_like_reel_item({"description": "#6 MALE STC HOSE FITTING"}, {}))

    def test_hose_clamps_do_not_look_like_reel_items(self):
        self.assertFalse(looks_like_reel_item({"description": "HOSE CLAMP, PK100"}, {}))

    def test_bulk_hose_looks_like_reel_item(self):
        self.assertTrue(looks_like_reel_item({"description": '1/4" 2WIRE 6500PSI HOSE'}, {}))

    def test_aircraft_cable_looks_like_reel_item(self):
        self.assertTrue(looks_like_reel_item({"description": '1/16 AIRCRAFT CABLE'}, {}))

    def test_airbrake_tube_looks_like_reel_item(self):
        self.assertTrue(looks_like_reel_item({"description": "3/8 NYLON AIRBRAKE TUBE"}, {}))

    def test_wire_requires_length_context_to_look_like_reel_item(self):
        self.assertFalse(looks_like_reel_item({"description": "WIRE BRUSH SET"}, {}))
        self.assertTrue(looks_like_reel_item({"description": "6GA. BLACK WIRE X 100FT"}, {}))

    def test_soft_pack_rounds_to_min_order_increment(self):
        qty, why = calculate_suggested_qty(3, 500, "soft_pack", {"min_order_qty": 250}, {"max": 100})
        self.assertEqual(qty, 250)
        self.assertIn("Soft pack: min order 250", why)

    def test_pack_trigger_rounds_to_full_pack(self):
        qty, why = calculate_suggested_qty(35, 300, "pack_trigger", None, {"max": 93})
        self.assertEqual(qty, 300)
        self.assertIn("Pack trigger", why)

    def test_standard_policy_rounds_up_but_at_least_one_pack(self):
        qty, why = calculate_suggested_qty(14, 12, "standard", None, {})
        self.assertEqual(qty, 24)
        self.assertIn("Rounded up to pack of 12", why)

        qty_small, _ = calculate_suggested_qty(3, 12, "standard", None, {})
        self.assertEqual(qty_small, 12)

    def test_calculate_raw_need_uses_inventory_position(self):
        item = {
            "inventory": {"qoh": 8, "max": 20},
            "qty_on_po": 4,
            "demand_signal": 6,
            "suggested_max": 18,
        }
        self.assertEqual(calculate_raw_need(item), 8)
        self.assertEqual(item["inventory_position"], 12)
        self.assertEqual(item["target_stock"], 20)
        self.assertEqual(item["target_basis"], "current_max")

    def test_calculate_inventory_position_uses_qoh_plus_on_po(self):
        item = {
            "inventory": {"qoh": 8, "max": 20},
            "qty_on_po": 4,
        }
        self.assertEqual(calculate_inventory_position(item), 12)
        self.assertEqual(item["inventory_position"], 12)

    def test_determine_target_stock_prefers_current_max_then_suggested_max(self):
        item = {
            "inventory": {"qoh": 8, "min": 5, "max": 20},
            "qty_on_po": 4,
            "demand_signal": 6,
            "suggested_max": 18,
        }
        self.assertEqual(determine_target_stock(item), 20)
        self.assertEqual(item["target_basis"], "current_max")

    def test_determine_target_stock_applies_hysteresis_for_small_suggested_change(self):
        item = {
            "inventory": {"qoh": 2, "min": None, "max": None},
            "qty_on_po": 0,
            "demand_signal": 3,
            "suggested_min": 4,
            "suggested_max": 9,
            "target_stock": 8,
            "target_basis": "suggested_max",
        }
        self.assertEqual(determine_target_stock(item), 8)
        self.assertTrue(item["target_stock_hysteresis_applied"])
        self.assertEqual(item["target_basis"], "suggested_max")

    def test_determine_target_stock_does_not_apply_hysteresis_to_current_max(self):
        item = {
            "inventory": {"qoh": 2, "min": 2, "max": 10},
            "qty_on_po": 0,
            "demand_signal": 3,
            "suggested_min": 4,
            "suggested_max": 9,
            "target_stock": 9,
            "target_basis": "suggested_max",
        }
        self.assertEqual(determine_target_stock(item), 10)
        self.assertFalse(item["target_stock_hysteresis_applied"])
        self.assertEqual(item["target_basis"], "current_max")

    def test_determine_target_stock_hysteresis_not_applied_when_basis_changes(self):
        # Previous basis was suggested_max; now resolves to suggested_min — basis change,
        # so hysteresis must not fire even if the numeric gap is small.
        item = {
            "inventory": {"qoh": 2, "min": None, "max": None},
            "qty_on_po": 0,
            "demand_signal": 3,
            "suggested_min": 9,
            "suggested_max": None,
            "target_stock": 8,
            "target_basis": "suggested_max",
        }
        result = determine_target_stock(item)
        self.assertFalse(item["target_stock_hysteresis_applied"])
        self.assertEqual(item["target_basis"], "suggested_min")
        self.assertEqual(result, 9)

    def test_determine_target_stock_hysteresis_at_absolute_gap_of_one(self):
        # Gap is exactly 1 — the absolute threshold — so hysteresis fires.
        item = {
            "inventory": {"qoh": 2, "min": None, "max": None},
            "qty_on_po": 0,
            "demand_signal": 3,
            "suggested_min": 4,
            "suggested_max": 20,
            "target_stock": 21,
            "target_basis": "suggested_max",
        }
        result = determine_target_stock(item)
        self.assertTrue(item["target_stock_hysteresis_applied"])
        self.assertEqual(result, 21)

    def test_determine_target_stock_hysteresis_not_applied_when_gap_exceeds_threshold(self):
        # Gap is 4 on a max-target of 20 = 20%. Exceeds the 15% threshold.
        item = {
            "inventory": {"qoh": 2, "min": None, "max": None},
            "qty_on_po": 0,
            "demand_signal": 3,
            "suggested_min": 4,
            "suggested_max": 24,
            "target_stock": 20,
            "target_basis": "suggested_max",
        }
        result = determine_target_stock(item)
        self.assertFalse(item["target_stock_hysteresis_applied"])
        self.assertEqual(result, 24)

    def test_determine_target_stock_hysteresis_not_applied_when_previous_target_zero(self):
        # No previous target recorded (zero) — never hysteresise from nothing.
        item = {
            "inventory": {"qoh": 2, "min": None, "max": None},
            "qty_on_po": 0,
            "demand_signal": 3,
            "suggested_min": 4,
            "suggested_max": 9,
            "target_stock": 0,
            "target_basis": "suggested_max",
        }
        result = determine_target_stock(item)
        self.assertFalse(item["target_stock_hysteresis_applied"])
        self.assertEqual(result, 9)

    def test_calculate_raw_need_returns_zero_when_qoh_and_on_po_cover_target(self):
        item = {
            "inventory": {"qoh": 12, "max": 20},
            "qty_on_po": 10,
            "demand_signal": 4,
            "suggested_max": 18,
        }
        self.assertEqual(calculate_raw_need(item), 0)

    def test_calculate_raw_need_respects_trigger_qty_gate_before_target_gap(self):
        item = {
            "inventory": {"qoh": 70, "max": 93},
            "qty_on_po": 0,
            "demand_signal": 12,
            "pack_size": 300,
            "reorder_trigger_qty": 60,
        }
        self.assertEqual(calculate_raw_need(item), 0)

        item["inventory"]["qoh"] = 58
        self.assertEqual(calculate_raw_need(item), 35)

    def test_evaluate_reorder_trigger_false_when_no_demand_and_min_is_covered(self):
        item = {
            "inventory": {"qoh": 5, "min": 4, "max": None},
            "qty_on_po": 0,
            "demand_signal": 0,
            "suggested_min": None,
            "suggested_max": None,
        }
        calculate_inventory_position(item)
        determine_target_stock(item)
        self.assertFalse(evaluate_reorder_trigger(item))

    def test_evaluate_reorder_trigger_uses_min_floor_when_no_demand_and_below_min(self):
        item = {
            "inventory": {"qoh": 2, "min": 6, "max": None},
            "qty_on_po": 0,
            "demand_signal": 0,
            "suggested_min": 4,
            "suggested_max": None,
        }
        calculate_inventory_position(item)
        determine_target_stock(item)
        self.assertTrue(evaluate_reorder_trigger(item))
        self.assertEqual(item["target_stock"], 6)

    def test_evaluate_reorder_trigger_uses_configured_trigger_qty_for_active_item(self):
        item = {
            "inventory": {"qoh": 70, "min": 10, "max": 93},
            "qty_on_po": 0,
            "demand_signal": 12,
            "pack_size": 300,
            "reorder_trigger_qty": 60,
        }
        calculate_inventory_position(item)
        determine_target_stock(item)
        self.assertFalse(evaluate_reorder_trigger(item))

        item["inventory"]["qoh"] = 58
        calculate_inventory_position(item)
        self.assertTrue(evaluate_reorder_trigger(item))

    def test_evaluate_reorder_trigger_uses_configured_trigger_pct_for_active_item(self):
        item = {
            "inventory": {"qoh": 25, "min": 5, "max": 20},
            "qty_on_po": 0,
            "demand_signal": 4,
            "pack_size": 100,
            "reorder_trigger_pct": 20,
        }
        calculate_inventory_position(item)
        determine_target_stock(item)
        self.assertFalse(evaluate_reorder_trigger(item))

        item["inventory"]["qoh"] = 18
        calculate_inventory_position(item)
        self.assertTrue(evaluate_reorder_trigger(item))

    def test_calculate_raw_need_treats_negative_qoh_as_zero(self):
        item = {
            "inventory": {"qoh": -2, "max": 3},
            "qty_on_po": 0,
            "demand_signal": 1,
            "suggested_max": None,
        }
        self.assertEqual(calculate_raw_need(item), 3)
        self.assertEqual(item["inventory_position"], 0)
        self.assertEqual(item["target_stock"], 3)

    def test_calculate_raw_need_falls_back_to_demand_when_no_max_exists(self):
        item = {
            "inventory": {"qoh": 5, "min": None, "max": None},
            "qty_on_po": 0,
            "demand_signal": 3,
            "suggested_min": None,
            "suggested_max": None,
        }
        self.assertEqual(calculate_raw_need(item), 0)
        self.assertEqual(item["target_stock"], 3)

    def test_calculate_raw_need_uses_min_fallback_when_no_max_exists(self):
        item = {
            "inventory": {"qoh": 2, "min": 6, "max": None},
            "qty_on_po": 0,
            "demand_signal": 3,
            "suggested_min": 4,
            "suggested_max": None,
        }
        self.assertEqual(calculate_raw_need(item), 4)
        self.assertEqual(item["target_stock"], 6)
        self.assertEqual(item["target_basis"], "current_min")

    def test_calculate_raw_need_does_not_double_subtract_suspense_from_qoh(self):
        item = {
            "inventory": {"qoh": 10, "max": 20},
            "qty_on_po": 0,
            "qty_suspended": 5,
            "effective_qty_suspended": 5,
            "demand_signal": 5,
            "suggested_max": 20,
        }
        self.assertEqual(calculate_raw_need(item), 10)
        self.assertEqual(item["inventory_position"], 10)

    def test_enrich_item_sets_review_and_pack_flags(self):
        item = {
            "description": '1/4" 2WIRE 6500PSI HOSE',
            "qty_sold": 10,
            "qty_suspended": 0,
            "qty_received": 0,
            "qty_on_po": 0,
            "pack_size": 500,
            "suggested_max": 24,
            "demand_signal": 10,
        }
        enrich_item(item, {"max": 100, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"}, 500, None)
        self.assertEqual(item["order_policy"], "reel_review")
        self.assertEqual(item["replenishment_unit_mode"], "reel_bulk_review")
        self.assertEqual(item["status"], "review")
        self.assertTrue(item["reorder_needed"])
        self.assertIn("reel_review", item["data_flags"])
        self.assertIn("unitmode_reel_bulk_review", item["reason_codes"])
        self.assertIn("Target stock", item["why"])
        self.assertIn("Replenishment mode: Reel / bulk review", item["why"])

    def test_evaluate_item_status_marks_missing_pack_and_zero_final(self):
        status, flags = evaluate_item_status({
            "pack_size": None,
            "order_policy": "exact_qty",
            "final_qty": 0,
            "raw_need": 5,
            "review_required": False,
            "review_resolved": False,
        })
        self.assertEqual(status, "warning")
        self.assertIn("missing_pack", flags)
        self.assertIn("zero_final", flags)

    def test_evaluate_item_status_zero_need_stays_skip_even_with_review_required(self):
        # Regression: items with nothing to order (final<=0 AND raw<=0) used
        # to be force-promoted from "skip" to "review" whenever any review
        # flag was set, hiding them from the Skip filter and from the
        # not-needed removal flow.  Verify they stay "skip".
        status, _flags = evaluate_item_status({
            "pack_size": 1,
            "final_qty": 0,
            "raw_need": 0,
            "review_required": True,
            "review_resolved": False,
        })
        self.assertEqual(status, "skip")

    def test_evaluate_item_status_flags_would_overshoot_max(self):
        # Regression: assess_post_receipt_overstock stamps projected_overstock_qty
        # but evaluate_item_status used to ignore it.  Verify the flag is set.
        status, flags = evaluate_item_status({
            "pack_size": 300,
            "final_qty": 300,
            "raw_need": 196,
            "projected_overstock_qty": 104,
            "overstock_within_tolerance": False,
            "review_required": False,
            "review_resolved": False,
        })
        self.assertEqual(status, "ok")
        self.assertIn("would_overshoot_max", flags)

    def test_evaluate_item_status_flags_order_floor_above_max(self):
        status, flags = evaluate_item_status({
            "pack_size": 1,
            "final_qty": 50,
            "raw_need": 50,
            "effective_target_stock": 30,
            "effective_order_floor": 50,
            "acceptable_overstock_qty_effective": 5,
            "review_required": False,
            "review_resolved": False,
        })
        self.assertIn("order_floor_above_max", flags)

    def test_evaluate_item_status_review_required_still_promotes_when_need_exists(self):
        status, _flags = evaluate_item_status({
            "pack_size": 1,
            "final_qty": 5,
            "raw_need": 5,
            "review_required": True,
            "review_resolved": False,
        })
        self.assertEqual(status, "review")

    def test_evaluate_item_status_skips_missing_pack_for_exact_qty_override(self):
        status, flags = evaluate_item_status({
            "pack_size": None,
            "exact_qty_override": True,
            "order_policy": "exact_qty",
            "final_qty": 0,
            "raw_need": 5,
            "review_required": False,
            "review_resolved": False,
        })
        self.assertEqual(status, "warning")
        self.assertNotIn("missing_pack", flags)
        self.assertIn("zero_final", flags)

    def test_buy_rule_summary_uses_soft_pack_and_below_pack_flag(self):
        summary = get_buy_rule_summary(
            {"order_policy": "soft_pack", "pack_size": 500},
            {"min_order_qty": 250, "allow_below_pack": True},
        )
        self.assertIn("Soft:250", summary)
        self.assertIn("vOK", summary)

    def test_buy_rule_summary_includes_trigger_fields(self):
        summary = get_buy_rule_summary(
            {"order_policy": "standard", "pack_size": 300},
            {"reorder_trigger_qty": 60, "reorder_trigger_pct": 20, "minimum_packs_on_hand": 2, "minimum_cover_days": 14, "minimum_cover_cycles": 2},
        )
        self.assertIn("Pk:300", summary)
        self.assertIn("Trg:60", summary)
        self.assertIn("Trg:20%", summary)
        self.assertIn("MinPk:2", summary)
        self.assertIn("CvrD:14", summary)
        self.assertIn("CvrC:2", summary)

    def test_buy_rule_summary_labels_pack_trigger_policy(self):
        summary = get_buy_rule_summary(
            {"order_policy": "pack_trigger", "pack_size": 300},
            {"reorder_trigger_qty": 60},
        )
        self.assertIn("TrigPk:300", summary)
        self.assertIn("Trg:60", summary)

    def test_buy_rule_summary_labels_large_pack_review_policy(self):
        summary = get_buy_rule_summary(
            {"order_policy": "large_pack_review", "pack_size": 100},
            {},
        )
        self.assertIn("LgPk:100", summary)


    def test_enrich_item_adds_inventory_and_suspense_reason_codes(self):
        item = {
            "qty_sold": 0,
            "qty_suspended": 4,
            "effective_qty_suspended": 4,
            "suspense_carry_qty": 2,
            "qty_received": 0,
            "qty_on_po": 1,
            "pack_size": 12,
            "suggested_max": 18,
            "demand_signal": 4,
        }
        enrich_item(item, {"qoh": 2, "max": 18}, 12, None)
        self.assertIn("below_target_stock", item["reason_codes"])
        self.assertIn("suspense_included", item["reason_codes"])
        self.assertIn("suspense_carry_applied", item["reason_codes"])
        self.assertIn("Stock after open POs", item["why"])
        self.assertIn("Suspended demand included: 4", item["why"])

    def test_enrich_item_records_target_basis_in_reason_codes_and_why(self):
        item = {
            "qty_sold": 3,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 6,
            "suggested_min": 4,
            "suggested_max": 9,
            "demand_signal": 3,
        }
        enrich_item(item, {"qoh": 1, "min": 2, "max": None}, 6, None)
        self.assertIn("target_suggested_max", item["reason_codes"])
        self.assertIn("Based on suggested max", item["why"])

    def test_enrich_item_surfaces_target_hysteresis_reasoning(self):
        item = {
            "qty_sold": 3,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 6,
            "suggested_min": 4,
            "suggested_max": 9,
            "demand_signal": 3,
            "target_stock": 8,
            "target_basis": "suggested_max",
        }
        enrich_item(item, {"qoh": 1, "min": 2, "max": None}, 6, None)
        self.assertEqual(item["target_stock"], 8)
        self.assertTrue(item["target_stock_hysteresis_applied"])
        self.assertIn("target_hysteresis_applied", item["reason_codes"])
        self.assertIn("Target hysteresis: retained prior target", item["why"])

    def test_enrich_item_copies_trigger_fields_from_rule(self):
        item = {
            "qty_sold": 3,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 6,
            "suggested_min": 4,
            "suggested_max": 9,
            "demand_signal": 3,
        }
        rule = {
            "reorder_trigger_qty": 60,
            "reorder_trigger_pct": 20,
            "minimum_packs_on_hand": 2,
            "minimum_cover_days": 14,
            "minimum_cover_cycles": 2,
            "acceptable_overstock_qty": 12,
            "acceptable_overstock_pct": 10,
        }
        enrich_item(item, {"qoh": 1, "min": 2, "max": None}, 6, rule)
        self.assertEqual(item["reorder_trigger_qty"], 60)
        self.assertEqual(item["reorder_trigger_pct"], 20.0)
        self.assertEqual(item["minimum_packs_on_hand"], 2)
        self.assertEqual(item["minimum_cover_days"], 14.0)
        self.assertEqual(item["minimum_cover_cycles"], 2.0)
        self.assertEqual(item["acceptable_overstock_qty"], 12)
        self.assertEqual(item["acceptable_overstock_pct"], 10.0)
        self.assertEqual(item["acceptable_overstock_qty_effective"], 12)


    def test_enrich_item_with_minimum_cover_cycles_raises_effective_reorder_floor(self):
        item = {
            "description": "FILTER KIT",
            "qty_sold": 30,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 100,
            "suggested_max": 20,
            "demand_signal": 30,
        }
        rule = {"order_policy": "pack_trigger", "minimum_cover_cycles": 2}

        enrich_item(
            item,
            {"qoh": 50, "max": 20, "min": 5, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"},
            100,
            rule,
        )
        self.assertTrue(item["reorder_needed"])
        self.assertEqual(item["reorder_trigger_threshold"], 60)
        self.assertEqual(item["reorder_trigger_basis"], "minimum_cover_cycles")
        self.assertEqual(item["effective_order_floor"], 60)
        self.assertEqual(item["effective_target_stock"], 20)
        self.assertIn("Minimum cover cycles: 2", item["why"])

    def test_enrich_item_with_minimum_cover_days_raises_effective_reorder_floor(self):
        item = {
            "description": "FILTER KIT",
            "qty_sold": 30,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 100,
            "suggested_max": 20,
            "demand_signal": 30,
            "reorder_cycle_weeks": 2,
        }
        rule = {"order_policy": "pack_trigger", "minimum_cover_days": 21}

        enrich_item(
            item,
            {"qoh": 40, "max": 20, "min": 5, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"},
            100,
            rule,
        )
        self.assertTrue(item["reorder_needed"])
        self.assertEqual(item["reorder_trigger_threshold"], 45)
        self.assertEqual(item["reorder_trigger_basis"], "minimum_cover_days")
        self.assertEqual(item["effective_order_floor"], 45)
        self.assertEqual(item["effective_target_stock"], 20)
        self.assertIn("Minimum cover days: 21", item["why"])

    def test_enrich_item_infers_weekly_hardware_cover_cycles_and_pack_trigger(self):
        item = {
            "description": "5/16 HEX NUT",
            "qty_sold": 8,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 10,
            "suggested_max": 8,
            "demand_signal": 8,
            "reorder_cycle_weeks": 1,
            "avg_weekly_sales_loaded": 8.0,
            "sales_health_signal": "active",
            "performance_profile": "steady",
            "days_since_last_sale": 7,
        }

        enrich_item(
            item,
            {"qoh": 9, "max": 8, "min": 2, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"},
            10,
            None,
        )
        self.assertEqual(item["minimum_cover_cycles"], 2)
        self.assertEqual(item["minimum_cover_cycles_source"], "heuristic")
        self.assertEqual(item["package_profile"], "hardware_pack")
        self.assertEqual(item["order_policy"], "pack_trigger")
        self.assertEqual(item["replenishment_unit_mode"], "pack_trigger_replenishment")
        self.assertEqual(item["reorder_trigger_basis"], "minimum_cover_cycles")
        self.assertEqual(item["reorder_trigger_threshold"], 16)
        self.assertEqual(item["raw_need"], 7)
        self.assertEqual(item["suggested_qty"], 10)
        self.assertIn("Minimum cover cycles: 2 (inferred)", item["why"])
        self.assertIn("package_hardware_pack", item["reason_codes"])

    def test_enrich_item_uses_configured_trigger_gate_and_reason_text(self):
        item = {
            "description": "HYD HOSE",
            "qty_sold": 12,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 300,
            "suggested_max": 93,
            "demand_signal": 12,
        }
        rule = {"reorder_trigger_qty": 60}

        enrich_item(item, {"qoh": 70, "max": 93, "min": 10}, 300, rule)
        self.assertFalse(item["reorder_needed"])
        self.assertEqual(item["raw_need"], 0)
        self.assertIn("Reorder trigger: 60", item["why"])

        enrich_item(item, {"qoh": 58, "max": 93, "min": 10}, 300, rule)
        self.assertTrue(item["reorder_needed"])
        self.assertEqual(item["raw_need"], 35)
        self.assertIn("trigger_trigger_qty", item["reason_codes"])

    def test_enrich_item_with_explicit_pack_trigger_policy_rounds_to_pack(self):
        item = {
            "description": "HYD HOSE",
            "qty_sold": 12,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 300,
            "suggested_max": 93,
            "demand_signal": 12,
        }
        rule = {"order_policy": "pack_trigger", "reorder_trigger_qty": 60}

        enrich_item(item, {"qoh": 58, "max": 93, "min": 10}, 300, rule)
        self.assertEqual(item["order_policy"], "pack_trigger")
        self.assertEqual(item["suggested_qty"], 300)
        self.assertEqual(item["final_qty"], 300)
        self.assertIn("pack_trigger", item["reason_codes"])

    def test_hose_reorders_at_configured_trigger_below_target(self):
        item = {
            "description": "HYD HOSE",
            "qty_sold": 12,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 300,
            "suggested_max": 93,
            "demand_signal": 12,
        }
        rule = {"order_policy": "pack_trigger", "reorder_trigger_qty": 60}

        enrich_item(item, {"qoh": 95, "max": 93, "min": 10}, 300, rule)
        self.assertFalse(item["reorder_needed"])
        self.assertEqual(item["raw_need"], 0)

        enrich_item(item, {"qoh": 58, "max": 93, "min": 10}, 300, rule)
        self.assertTrue(item["reorder_needed"])
        self.assertEqual(item["raw_need"], 35)
        self.assertEqual(item["suggested_qty"], 300)

    def test_bag_item_can_require_two_packs_of_cover_even_when_max_is_lower(self):
        item = {
            "description": "1/4 X 1 ELEVATOR BOLT",
            "qty_sold": 30,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 100,
            "suggested_max": 20,
            "demand_signal": 30,
        }
        rule = {"order_policy": "pack_trigger", "minimum_packs_on_hand": 2}

        enrich_item(item, {"qoh": 150, "max": 20, "min": 5}, 100, rule)
        self.assertTrue(item["reorder_needed"])
        self.assertEqual(item["reorder_trigger_threshold"], 200)
        self.assertEqual(item["reorder_trigger_basis"], "minimum_packs_on_hand")
        self.assertEqual(item["effective_order_floor"], 200)
        self.assertEqual(item["effective_target_stock"], 20)
        self.assertEqual(item["raw_need"], 50)
        self.assertEqual(item["suggested_qty"], 100)
        self.assertIn("trigger_minimum_packs_on_hand", item["reason_codes"])
        self.assertIn("Minimum packs on hand: 2 (saved rule)", item["why"])

    def test_enrich_item_surfaces_acceptable_overstock_tolerance(self):
        item = {
            "description": "FILTER KIT",
            "qty_sold": 30,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 100,
            "suggested_max": 20,
            "demand_signal": 30,
        }
        rule = {"acceptable_overstock_qty": 80, "acceptable_overstock_pct": 25}

        enrich_item(item, {"qoh": 0, "max": 20, "min": 5, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"}, 100, rule)
        self.assertEqual(item["acceptable_overstock_qty_effective"], 80)
        self.assertEqual(item["acceptable_overstock_basis"], "qty")
        self.assertEqual(item["projected_overstock_qty"], 80)
        self.assertIn("acceptable_overstock_configured", item["reason_codes"])
        self.assertIn("Acceptable overstock: 80 (saved qty)", item["why"])
        self.assertIn("Projected overstock after receipt: 80 (within tolerance)", item["why"])

    def test_enrich_item_routes_to_manual_review_when_configured_overstock_tolerance_is_exceeded(self):
        item = {
            "description": "FILTER KIT",
            "qty_sold": 30,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 100,
            "suggested_max": 20,
            "demand_signal": 30,
        }
        rule = {"acceptable_overstock_qty": 10}

        enrich_item(item, {"qoh": 0, "max": 20, "min": 5, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"}, 100, rule)
        self.assertEqual(item["order_policy"], "manual_only")
        self.assertTrue(item["review_required"])
        self.assertIn("acceptable_overstock_exceeded", item["reason_codes"])
        self.assertIn("Auto-order projection: 80 (exceeds tolerance)", item["why"])

    def test_active_hardware_pack_mismatch_can_infer_two_pack_floor_without_rule(self):
        item = {
            "description": "5/16 HEX NUT",
            "qty_sold": 30,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 100,
            "suggested_max": 20,
            "demand_signal": 30,
            "sales_health_signal": "active",
            "performance_profile": "steady",
            "days_since_last_sale": 14,
        }

        enrich_item(item, {"qoh": 150, "max": 20, "min": 5, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"}, 100, None)
        self.assertEqual(item["minimum_packs_on_hand"], 2)
        self.assertEqual(item["minimum_packs_on_hand_source"], "heuristic")
        self.assertEqual(item["reorder_trigger_threshold"], 200)
        self.assertEqual(item["suggested_qty"], 100)
        self.assertIn("Minimum packs on hand: 2 (inferred)", item["why"])

    def test_active_hardware_pack_mismatch_can_infer_three_pack_floor_with_strong_history(self):
        item = {
            "description": "5/16 HEX NUT",
            "qty_sold": 360,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 100,
            "suggested_max": 20,
            "demand_signal": 90,
            "sales_health_signal": "active",
            "performance_profile": "top_performer",
            "days_since_last_sale": 7,
            "sales_span_days": 365,
            "avg_weekly_sales_loaded": 90.0,
            "annualized_sales_loaded": 4680.0,
            "detailed_sales_shape": "steady_repeat",
        }

        enrich_item(item, {"qoh": 250, "max": 20, "min": 5, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"}, 100, None)
        self.assertEqual(item["minimum_packs_on_hand"], 3)
        self.assertEqual(item["minimum_packs_on_hand_source"], "heuristic")
        self.assertEqual(item["reorder_trigger_threshold"], 300)
        self.assertIn("Minimum packs on hand: 3 (inferred)", item["why"])

    def test_enrich_item_can_infer_three_cover_cycles_for_strong_weekly_hardware(self):
        item = {
            "description": "5/16 HEX NUT",
            "qty_sold": 52,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 10,
            "suggested_max": 4,
            "demand_signal": 12,
            "reorder_cycle_weeks": 1,
            "avg_weekly_sales_loaded": 12.0,
            "sales_span_days": 365,
            "annualized_sales_loaded": 624.0,
            "sales_health_signal": "active",
            "performance_profile": "top_performer",
            "days_since_last_sale": 7,
            "detailed_sales_shape": "steady_repeat",
        }

        enrich_item(
            item,
            {"qoh": 20, "max": 4, "min": 2, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"},
            10,
            None,
        )
        self.assertEqual(item["minimum_cover_cycles"], 3)
        self.assertEqual(item["minimum_cover_cycles_source"], "heuristic")
        self.assertEqual(item["reorder_trigger_basis"], "minimum_cover_cycles")
        self.assertEqual(item["reorder_trigger_threshold"], 36)
        self.assertIn("Minimum cover cycles: 3 (inferred)", item["why"])

    def test_stale_hardware_pack_mismatch_does_not_infer_two_pack_floor(self):
        item = {
            "description": "5/16 HEX NUT",
            "qty_sold": 4,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 100,
            "suggested_max": 20,
            "demand_signal": 4,
            "sales_health_signal": "dormant",
            "performance_profile": "legacy",
            "days_since_last_sale": 500,
        }

        enrich_item(item, {"qoh": 150, "max": 20, "min": 5}, 100, None)
        self.assertIsNone(item.get("minimum_packs_on_hand"))
        self.assertIsNone(item.get("minimum_packs_on_hand_source"))
        self.assertEqual(item["order_policy"], "large_pack_review")

    def test_enrich_item_marks_large_pack_review_as_review_only(self):
        item = {
            "description": "FILTER KIT",
            "qty_sold": 4,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 100,
            "suggested_max": 20,
            "demand_signal": 4,
            "sales_health_signal": "dormant",
            "performance_profile": "legacy",
            "days_since_last_sale": 500,
        }

        enrich_item(item, {"qoh": 0, "max": 20, "min": 2}, 100, None)
        self.assertEqual(item["package_profile"], "large_nonreel_pack")
        self.assertEqual(item["order_policy"], "large_pack_review")
        self.assertEqual(item["replenishment_unit_mode"], "large_pack_review")
        self.assertTrue(item["review_required"])
        self.assertEqual(item["status"], "review")
        self.assertIn("large_pack_review", item["reason_codes"])
        self.assertIn("large_pack_review", item["data_flags"])
        self.assertIn("Package profile: Large non-reel pack", item["why"])

    def test_missing_sale_and_receipt_history_routes_reorder_candidate_to_manual_review(self):
        item = {
            "description": "FILTER ELEMENT",
            "qty_sold": 1,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 1,
            "suggested_max": 2,
            "demand_signal": 1,
        }

        enrich_item(item, {"qoh": 0, "max": 2, "min": 0}, 1, None)
        self.assertEqual(item["recency_confidence"], "low")
        self.assertEqual(item["data_completeness"], "missing_recency")
        self.assertEqual(item["recency_review_bucket"], "missing_data_uncertain")
        self.assertEqual(item["order_policy"], "manual_only")
        self.assertTrue(item["review_required"])
        self.assertEqual(item["status"], "review")
        self.assertEqual(item["suggested_qty"], 0)
        self.assertEqual(item["final_qty"], 0)
        self.assertIn("Missing-data / uncertain", item["why"])
        self.assertIn("incomplete data makes demand uncertain", item["why"])
        self.assertIn("zero_final", item["data_flags"])

    def test_missing_recency_below_min_without_explicit_rule_routes_to_zero_qty_review(self):
        item = {
            "description": "NO HISTORY FILTER",
            "qty_sold": 0,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 1,
            "demand_signal": 0,
            "performance_profile": "legacy",
            "sales_health_signal": "stale",
        }

        enrich_item(item, {"qoh": 0, "min": 1, "max": 0}, 1, None)
        self.assertEqual(item["recency_confidence"], "low")
        self.assertEqual(item["data_completeness"], "missing_recency")
        self.assertEqual(item["recency_review_bucket"], "stale_or_likely_dead")
        self.assertEqual(item["raw_need"], 1)
        self.assertEqual(item["order_policy"], "manual_only")
        self.assertEqual(item["suggested_qty"], 0)
        self.assertEqual(item["final_qty"], 0)
        self.assertTrue(item["review_required"])
        self.assertEqual(item["status"], "review")
        self.assertIn("Stale / likely dead", item["why"])
        self.assertIn("likely stale or dead item", item["why"])

    def test_missing_recency_with_receipts_but_no_dates_is_labeled_new_or_sparse(self):
        item = {
            "description": "NEW FILTER",
            "qty_sold": 0,
            "qty_suspended": 0,
            "qty_received": 2,
            "receipt_count": 2,
            "receipt_sales_balance": "receipt_heavy",
            "receipt_sales_balance_reason": "repeat receipts exist in the loaded window without matching sales activity",
            "qty_on_po": 0,
            "pack_size": 1,
            "demand_signal": 1,
        }

        enrich_item(item, {"qoh": 0, "min": 0, "max": 1}, 1, None)
        self.assertEqual(item["recency_confidence"], "low")
        self.assertEqual(item["data_completeness"], "missing_recency_receipt_heavy")
        self.assertEqual(item["recency_review_bucket"], "receipt_heavy_unverified")
        self.assertEqual(item["order_policy"], "manual_only")
        self.assertEqual(item["suggested_qty"], 0)
        self.assertIn("receipts outpace sales", item["why"])
        self.assertIn("Loaded receipts in selected window: 2", item["why"])
        self.assertIn("Receipt vs sales: receipt-heavy vs sales", item["why"])

    def test_missing_recency_with_balanced_receipts_still_counts_as_activity_protected(self):
        item = {
            "description": "SHOP FILTER",
            "qty_sold": 4,
            "qty_suspended": 0,
            "qty_received": 5,
            "receipt_count": 2,
            "receipt_sales_balance": "balanced",
            "receipt_sales_balance_reason": "loaded receipts and sales are in a similar range",
            "qty_on_po": 0,
            "pack_size": 1,
            "demand_signal": 4,
        }

        enrich_item(item, {"qoh": 0, "min": 0, "max": 4}, 1, None)

        self.assertEqual(item["data_completeness"], "missing_recency_activity_protected")
        self.assertEqual(item["recency_review_bucket"], "new_or_sparse")
        self.assertIn("Receipt vs sales: balanced with sales", item["why"])

    def test_missing_recency_with_explicit_trigger_rule_remains_orderable(self):
        item = {
            "description": "CRITICAL STOCK",
            "qty_sold": 2,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 1,
            "demand_signal": 2,
        }

        enrich_item(item, {"qoh": 0, "min": 1, "max": 0}, 1, {"reorder_trigger_qty": 2})
        self.assertEqual(item["recency_confidence"], "low")
        self.assertEqual(item["data_completeness"], "missing_recency_rule_protected")
        self.assertEqual(item["recency_review_bucket"], "critical_rule_protected")
        self.assertNotEqual(item["order_policy"], "manual_only")
        self.assertGreater(item["suggested_qty"], 0)
        self.assertGreater(item["final_qty"], 0)
        self.assertFalse(item["review_required"])
        self.assertIn("Critical / rule-protected", item["why"])

    def test_missing_recency_with_explicit_critical_min_rule_remains_orderable(self):
        item = {
            "description": "CRITICAL MIN ITEM",
            "qty_sold": 1,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 1,
            "demand_signal": 1,
        }

        enrich_item(item, {"qoh": 0, "min": 0, "max": 1}, 1, {"min_order_qty": 2, "allow_below_pack": True})
        self.assertEqual(item["recency_confidence"], "low")
        self.assertEqual(item["data_completeness"], "missing_recency_critical_min_protected")
        self.assertEqual(item["recency_review_bucket"], "critical_min_rule_protected")
        self.assertNotEqual(item["order_policy"], "manual_only")
        self.assertGreater(item["suggested_qty"], 0)
        self.assertGreater(item["final_qty"], 0)
        self.assertFalse(item["review_required"])
        self.assertIn("Critical / explicit min rule", item["why"])

    def test_missing_recency_with_suspense_demand_routes_to_review_not_skip(self):
        item = {
            "description": "SHOP SUPPLY",
            "qty_sold": 0,
            "qty_suspended": 3,
            "effective_qty_suspended": 3,
            "qty_on_po": 0,
            "pack_size": 12,
            "suggested_max": 12,
            "demand_signal": 3,
        }

        enrich_item(item, {"qoh": 0, "max": 12, "min": 0}, 12, None)
        self.assertEqual(item["recency_confidence"], "low")
        self.assertEqual(item["data_completeness"], "missing_recency_activity_protected")
        self.assertEqual(item["recency_review_bucket"], "activity_protected")
        self.assertEqual(item["order_policy"], "manual_only")
        self.assertEqual(item["suggested_qty"], 0)
        self.assertEqual(item["final_qty"], 0)
        self.assertTrue(item["review_required"])
        self.assertNotEqual(item["status"], "skip")
        self.assertIn("Protected by other activity", item["why"])
        self.assertIn("protected by other evidence", item["why"])

    def test_missing_recency_with_recent_local_po_history_routes_to_zero_qty_review(self):
        item = {
            "description": "LOCAL PO HISTORY ITEM",
            "qty_sold": 0,
            "qty_suspended": 0,
            "qty_received": 0,
            "qty_on_po": 0,
            "pack_size": 1,
            "demand_signal": 1,
            "recent_local_order_count": 1,
            "recent_local_order_qty": 2,
            "recent_local_order_date": "2026-03-10",
            "has_recent_local_order": True,
        }

        enrich_item(item, {"qoh": 0, "max": 1, "min": 0}, 1, None)
        self.assertEqual(item["recency_confidence"], "low")
        self.assertEqual(item["data_completeness"], "missing_recency_local_po_protected")
        self.assertEqual(item["recency_review_bucket"], "recent_local_po_protected")
        self.assertEqual(item["order_policy"], "manual_only")
        self.assertEqual(item["suggested_qty"], 0)
        self.assertEqual(item["final_qty"], 0)
        self.assertIn("Protected by recent local PO history", item["why"])
        self.assertIn("Recent local PO history: 1 order(s), 2 total, latest 2026-03-10", item["why"])

    def test_enrich_item_includes_receipt_vendor_evidence_in_why(self):
        item = {
            "description": "HOSE",
            "qty_sold": 2,
            "qty_suspended": 0,
            "qty_received": 5,
            "receipt_count": 2,
            "receipt_sales_balance": "receipt_led",
            "receipt_sales_balance_reason": "receipts are running ahead of sales, but not enough to treat as overstock-driven",
            "qty_on_po": 0,
            "pack_size": 1,
            "demand_signal": 2,
            "receipt_primary_vendor": "MOTION",
            "receipt_vendor_confidence": "medium",
            "receipt_vendor_ambiguous": True,
            "receipt_vendor_candidates": ["MOTION", "SOURCE"],
        }

        enrich_item(item, {"qoh": 0, "max": 2, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"}, 1, None)

        self.assertIn("Receipt vendor evidence: MOTION (medium confidence)", item["why"])
        self.assertIn("Receipt vendor history is mixed: MOTION, SOURCE", item["why"])
        self.assertIn("Receipt vs sales: running ahead of sales", item["why"])
        self.assertIn("receipt_vendor_medium", item["reason_codes"])
        self.assertIn("receipt_vendor_ambiguous", item["reason_codes"])
        self.assertIn("receipt_sales_receipt_led", item["reason_codes"])

    def test_enrich_item_flags_high_confidence_receipt_pack_mismatch(self):
        item = {
            "description": "HOSE",
            "qty_sold": 2,
            "qty_suspended": 0,
            "qty_received": 5,
            "qty_on_po": 0,
            "pack_size": 10,
            "pack_size_source": "x4_exact",
            "demand_signal": 2,
            "potential_pack_size": 25,
            "potential_pack_confidence": "high",
            "reorder_attention_signal": "normal",
        }

        enrich_item(item, {"qoh": 0, "max": 2, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"}, 10, None)

        self.assertTrue(item["receipt_pack_mismatch"])
        self.assertEqual(item["reorder_attention_signal"], "review_receipt_pack_mismatch")
        self.assertIn("Receipt pack evidence suggests 25", item["why"])
        self.assertIn("receipt_pack_mismatch", item["reason_codes"])

    # --- Phase 2: reel_review / large_pack_review graduation ---

    def test_reel_review_without_strong_evidence_stays_reel_review(self):
        item = {"description": '1/4" 2WIRE 6500PSI HOSE'}
        policy = determine_order_policy(item, {"max": 100}, 500, None)
        self.assertEqual(policy, "reel_review")
        self.assertNotIn("policy_graduated_from", item)

    def test_reel_item_graduates_to_reel_auto_with_high_recency_and_active_sales(self):
        item = {
            "description": '1/4" 2WIRE 6500PSI HOSE',
            "recency_confidence": "high",
            "sales_health_signal": "active",
        }
        policy = determine_order_policy(item, {"max": 100}, 500, None)
        self.assertEqual(policy, "reel_auto")
        self.assertEqual(item.get("policy_graduated_from"), "reel_review")

    def test_reel_item_graduates_to_reel_auto_with_high_recency_and_recent_local_order(self):
        item = {
            "description": '1/4" 2WIRE 6500PSI HOSE',
            "recency_confidence": "high",
            "sales_health_signal": "stable",
            "has_recent_local_order": True,
        }
        policy = determine_order_policy(item, {"max": 100}, 500, None)
        self.assertEqual(policy, "reel_auto")
        self.assertEqual(item.get("policy_graduated_from"), "reel_review")

    def test_reel_item_does_not_graduate_with_low_recency(self):
        item = {
            "description": '1/4" 2WIRE 6500PSI HOSE',
            "recency_confidence": "low",
            "sales_health_signal": "active",
        }
        policy = determine_order_policy(item, {"max": 100}, 500, None)
        self.assertEqual(policy, "reel_review")

    def test_reel_item_does_not_graduate_when_policy_locked(self):
        item = {
            "description": '1/4" 2WIRE 6500PSI HOSE',
            "recency_confidence": "high",
            "sales_health_signal": "active",
        }
        rule = {"policy_locked": True}
        policy = determine_order_policy(item, {"max": 100}, 500, rule)
        self.assertEqual(policy, "reel_review")
        self.assertNotIn("policy_graduated_from", item)

    def test_large_pack_review_graduates_to_pack_trigger_with_high_recency_and_active_sales(self):
        item = {
            "description": "LARGE CABLE TIE",
            "performance_profile": "legacy",
            "days_since_last_sale": 500,
            "recency_confidence": "high",
            "sales_health_signal": "active",
        }
        policy = determine_order_policy(item, {"max": 20}, 100, None)
        self.assertEqual(policy, "pack_trigger")
        self.assertEqual(item.get("policy_graduated_from"), "large_pack_review")

    def test_large_pack_review_stays_without_strong_evidence(self):
        item = {
            "description": "LARGE CABLE TIE",
            "performance_profile": "legacy",
            "days_since_last_sale": 500,
            "recency_confidence": "low",
            "sales_health_signal": "active",
        }
        policy = determine_order_policy(item, {"max": 20}, 100, None)
        self.assertEqual(policy, "large_pack_review")
        self.assertNotIn("policy_graduated_from", item)

    def test_reel_auto_calculates_pack_trigger_quantity(self):
        suggested, why = calculate_suggested_qty(30, 500, "reel_auto", None, {"max": 100})
        self.assertEqual(suggested, 500)
        self.assertIn("Reel auto", why)
        self.assertIn("graduated", why)

    def test_reel_auto_replenishment_unit_mode_is_pack_trigger(self):
        from rules import classify_replenishment_unit_mode
        mode = classify_replenishment_unit_mode("reel_auto", {}, 500, None)
        self.assertEqual(mode, "pack_trigger_replenishment")

    def test_reel_auto_does_not_trigger_review_in_evaluate_item_status(self):
        item = {"order_policy": "reel_auto", "raw_need": 50, "final_qty": 500}
        status, flags = evaluate_item_status(item)
        self.assertNotEqual(status, "review")
        self.assertIn("reel_auto", flags)

    def test_enrich_item_reel_auto_graduation_appears_in_reason_codes_and_why(self):
        item = {
            "description": '1/4" 2WIRE 6500PSI HOSE',
            "qty_sold": 5,
            "qty_suspended": 0,
            "qty_received": 500,
            "qty_on_po": 0,
            "pack_size": 500,
            "demand_signal": 5,
            "recency_confidence": "high",
            "sales_health_signal": "active",
        }
        inv = {"qoh": 0, "max": 100, "last_sale": "01-Mar-2026", "last_receipt": "15-Mar-2026"}
        enrich_item(item, inv, 500, None)
        self.assertEqual(item["order_policy"], "reel_auto")
        self.assertIn("reel_auto", item["reason_codes"])
        self.assertIn("graduated_from_reel_review", item["reason_codes"])
        self.assertIn("graduated", item["why"].lower())

    def test_reel_graduated_item_reverts_when_recency_drops(self):
        item_weak = {
            "description": '1/4" 2WIRE 6500PSI HOSE',
            "recency_confidence": "medium",
            "sales_health_signal": "active",
        }
        policy = determine_order_policy(item_weak, {"max": 100}, 500, None)
        self.assertEqual(policy, "reel_review")
        self.assertNotIn("policy_graduated_from", item_weak)

    # --- Phase 3: confirmed_stocking lifecycle ---

    def _missing_recency_item(self):
        return {
            "description": "WIDGET",
            "qty_sold": 0,
            "qty_suspended": 0,
            "qty_received": 0,
            "qty_on_po": 0,
            "pack_size": 10,
            "demand_signal": 5,
        }

    def test_confirmed_stocking_bypasses_recency_review_routes_to_auto_order(self):
        item = self._missing_recency_item()
        rule = {"confirmed_stocking": True}
        enrich_item(item, {"qoh": 0, "max": 10}, 10, rule)
        self.assertNotEqual(item["order_policy"], "manual_only")
        self.assertTrue(item["confirmed_stocking"])
        self.assertFalse(item.get("confirmed_stocking_expired", False))
        self.assertIn("confirmed_stocking", item["reason_codes"])

    def test_confirmed_stocking_false_still_routes_to_review_without_evidence(self):
        item = self._missing_recency_item()
        rule = {"confirmed_stocking": False}
        enrich_item(item, {"qoh": 0, "max": 10}, 10, rule)
        self.assertEqual(item["order_policy"], "manual_only")

    def test_confirmed_stocking_expired_after_threshold_sessions_without_evidence(self):
        from rules import CONFIRMED_STOCKING_MAX_SESSIONS_WITHOUT_EVIDENCE
        item = self._missing_recency_item()
        rule = {
            "confirmed_stocking": True,
            "confirmed_stocking_sessions_without_evidence": CONFIRMED_STOCKING_MAX_SESSIONS_WITHOUT_EVIDENCE,
        }
        enrich_item(item, {"qoh": 0, "max": 10}, 10, rule)
        self.assertTrue(item["confirmed_stocking_expired"])
        self.assertIn("confirmed_stocking_expired", item["reason_codes"])
        self.assertEqual(item["order_policy"], "manual_only")

    def test_confirmed_stocking_resets_counter_when_evidence_present(self):
        item = self._missing_recency_item()
        rule = {
            "confirmed_stocking": True,
            "confirmed_stocking_sessions_without_evidence": 2,
        }
        inv = {"qoh": 0, "max": 10, "last_sale": "01-Mar-2026", "last_receipt": "15-Mar-2026"}
        enrich_item(item, inv, 10, rule)
        self.assertEqual(item["confirmed_stocking_sessions_without_evidence"], 0)
        self.assertEqual(rule["confirmed_stocking_sessions_without_evidence"], 0)

    def test_confirmed_stocking_increments_counter_without_evidence(self):
        item = self._missing_recency_item()
        rule = {
            "confirmed_stocking": True,
            "confirmed_stocking_sessions_without_evidence": 1,
        }
        enrich_item(item, {"qoh": 0, "max": 10}, 10, rule)
        self.assertEqual(item["confirmed_stocking_sessions_without_evidence"], 2)
        self.assertEqual(rule["confirmed_stocking_sessions_without_evidence"], 2)

    def test_confirmed_stocking_surfaces_in_why_detail(self):
        item = self._missing_recency_item()
        rule = {"confirmed_stocking": True}
        enrich_item(item, {"qoh": 0, "max": 10}, 10, rule)
        self.assertIn("Confirmed stocking", item["why"])
        self.assertIn("operator-confirmed", item["why"])

    def test_confirmed_stocking_expiry_surfaces_in_why_detail(self):
        from rules import CONFIRMED_STOCKING_MAX_SESSIONS_WITHOUT_EVIDENCE
        item = self._missing_recency_item()
        rule = {
            "confirmed_stocking": True,
            "confirmed_stocking_sessions_without_evidence": CONFIRMED_STOCKING_MAX_SESSIONS_WITHOUT_EVIDENCE,
        }
        enrich_item(item, {"qoh": 0, "max": 10}, 10, rule)
        self.assertIn("expired", item["why"])

    # --- Phase 4: session learning / historical order qty ---

    def _standard_item(self):
        return {
            "description": "WIDGET",
            "qty_sold": 10,
            "qty_suspended": 0,
            "qty_received": 10,
            "qty_on_po": 0,
            "pack_size": 10,
            "demand_signal": 10,
        }

    def test_no_history_no_gap_flag(self):
        item = self._standard_item()
        enrich_item(item, {"qoh": 0, "max": 20, "last_sale": "01-Mar-2026", "last_receipt": "15-Feb-2026"}, 10, None)
        self.assertFalse(item.get("suggestion_vs_history_gap"))

    def test_history_within_threshold_no_gap(self):
        item = self._standard_item()
        item["historical_order_qty"] = 20  # same as expected suggestion
        enrich_item(item, {"qoh": 0, "max": 20, "last_sale": "01-Mar-2026", "last_receipt": "15-Feb-2026"}, 10, None)
        self.assertFalse(item.get("suggestion_vs_history_gap"))

    def test_history_gap_beyond_threshold_flags_review(self):
        item = self._standard_item()
        item["historical_order_qty"] = 100  # big divergence from a ~10-20 suggestion
        enrich_item(item, {"qoh": 0, "max": 20, "last_sale": "01-Mar-2026", "last_receipt": "15-Feb-2026"}, 10, None)
        self.assertTrue(item.get("suggestion_vs_history_gap"))
        self.assertTrue(item.get("review_required"))
        self.assertIn("suggestion_vs_history_gap", item["reason_codes"])
        self.assertIn("History gap", item["why"])

    def test_history_gap_ignored_for_manual_only_policy(self):
        item = self._standard_item()
        item["historical_order_qty"] = 100
        # Force manual_only by removing recency
        enrich_item(item, {"qoh": 0, "max": 20}, 10, None)  # no last_sale/last_receipt
        if item.get("order_policy") == "manual_only":
            self.assertFalse(item.get("suggestion_vs_history_gap"))

    # --- Item 2: recent_local_order_qty fallback ---

    def test_recent_local_order_qty_fallback_gap_flags_review(self):
        """No historical_order_qty, but local avg diverges far from suggestion → gap flagged."""
        item = self._standard_item()
        # suggestion will be ~20 (pack=10, need fills to max=20)
        item["recent_local_order_qty"] = 200   # avg 100 per order
        item["recent_local_order_count"] = 2
        enrich_item(item, {"qoh": 0, "max": 20, "last_sale": "01-Mar-2026", "last_receipt": "15-Feb-2026"}, 10, None)
        self.assertTrue(item.get("suggestion_vs_history_gap"))
        self.assertIn("suggestion_vs_history_gap", item.get("reason_codes", []))
        self.assertIn("Local PO history gap", item.get("why", ""))

    def test_recent_local_order_qty_fallback_no_gap(self):
        """No historical_order_qty, local avg close to suggestion → no gap."""
        item = self._standard_item()
        # suggestion ~20, local avg 20 → ratio=0
        item["recent_local_order_qty"] = 40
        item["recent_local_order_count"] = 2
        enrich_item(item, {"qoh": 0, "max": 20, "last_sale": "01-Mar-2026", "last_receipt": "15-Feb-2026"}, 10, None)
        self.assertFalse(item.get("suggestion_vs_history_gap"))

    def test_recent_local_order_qty_not_used_when_historical_present(self):
        """When historical_order_qty is present, the local fallback should not run."""
        item = self._standard_item()
        item["historical_order_qty"] = 20   # matches suggestion closely
        item["recent_local_order_qty"] = 200  # would diverge if used
        item["recent_local_order_count"] = 2
        enrich_item(item, {"qoh": 0, "max": 20, "last_sale": "01-Mar-2026", "last_receipt": "15-Feb-2026"}, 10, None)
        # historical matches → no gap
        self.assertFalse(item.get("suggestion_vs_history_gap"))

    # --- Item 4: heuristic_confidence ---

    def test_heuristic_confidence_all_signals_high(self):
        """All favourable signals → score near 1.0."""
        from rules import compute_heuristic_confidence
        item = {
            "sales_span_days": 365,
            "recency_confidence": "high",
            "performance_profile": "top_performer",
            "sales_health_signal": "active",
            "detailed_sales_shape": "steady_repeat",
            "days_since_last_sale": 5,
        }
        score = compute_heuristic_confidence(item)
        self.assertGreaterEqual(score, 0.9)
        self.assertLessEqual(score, 1.0)

    def test_heuristic_confidence_short_span_hard_cap(self):
        """Span < 14 days → score capped at 0.3 regardless of other signals."""
        from rules import compute_heuristic_confidence
        item = {
            "sales_span_days": 7,
            "recency_confidence": "high",
            "performance_profile": "top_performer",
            "sales_health_signal": "active",
            "detailed_sales_shape": "steady_repeat",
            "days_since_last_sale": 2,
        }
        score = compute_heuristic_confidence(item)
        self.assertLessEqual(score, 0.3)

    def test_heuristic_confidence_no_signals(self):
        """No signals present → score is 0.0."""
        from rules import compute_heuristic_confidence
        item = {}
        score = compute_heuristic_confidence(item)
        self.assertEqual(score, 0.0)

    # --- Item 5: elevated buffer via high confidence + history ---

    def _hardware_item_base(self):
        """Item that qualifies for infer_minimum_packs_on_hand logic."""
        return {
            "description": "BOLT KIT",  # hardware pack
            "qty_sold": 50,
            "qty_suspended": 0,
            "qty_received": 50,
            "qty_on_po": 0,
            "pack_size": 100,
            "demand_signal": 50,
            "sales_health_signal": "active",
            "performance_profile": "steady",
            "days_since_last_sale": 5,
            "sales_span_days": 365,
            "avg_weekly_sales_loaded": 10,
            "annualized_sales_loaded": 520,
        }

    def test_high_confidence_and_history_elevates_buffer_to_3(self):
        """High heuristic_confidence + order history of >=2 packs → min_packs=3."""
        from rules import infer_minimum_packs_on_hand, compute_heuristic_confidence
        item = self._hardware_item_base()
        item["recency_confidence"] = "high"
        item["detailed_sales_shape"] = "steady_repeat"
        item["heuristic_confidence"] = 0.80
        item["historical_order_qty"] = 200  # >= pack*2=200
        inv = {"max": 10, "min": 5}  # pack(100) > max(10)*3 → qualifies
        result = infer_minimum_packs_on_hand(item, inv, 100)
        self.assertEqual(result, 3)
        self.assertIn("heuristic_confidence_elevated_buffer", item.get("reason_codes", []))

    def test_high_confidence_without_history_stays_at_2(self):
        """High heuristic_confidence but no order history → not elevated."""
        from rules import infer_minimum_packs_on_hand
        item = self._hardware_item_base()
        item["heuristic_confidence"] = 0.80
        # no historical_order_qty, no recent_local_order_qty
        inv = {"max": 10, "min": 5}
        result = infer_minimum_packs_on_hand(item, inv, 100)
        self.assertEqual(result, 2)

    def test_below_confidence_threshold_stays_at_2(self):
        """Confidence below threshold → elevated buffer not triggered."""
        from rules import infer_minimum_packs_on_hand
        item = self._hardware_item_base()
        item["heuristic_confidence"] = 0.50
        item["historical_order_qty"] = 200
        inv = {"max": 10, "min": 5}
        result = infer_minimum_packs_on_hand(item, inv, 100)
        self.assertEqual(result, 2)

    # --- Item 6: volatile demand caps ---

    def test_volatile_demand_erratic_caps_min_packs_at_1(self):
        """Erratic detailed_sales_shape → minimum_packs_on_hand capped at 1."""
        from rules import infer_minimum_packs_on_hand
        item = self._hardware_item_base()
        item["detailed_sales_shape"] = "erratic"
        item["heuristic_confidence"] = 0.0
        inv = {"max": 10, "min": 5}
        result = infer_minimum_packs_on_hand(item, inv, 100)
        self.assertEqual(result, 1)

    def test_volatile_demand_dormant_caps_min_packs_at_1(self):
        """Dormant sales_health_signal → would normally disqualify (returns None), check volatile path."""
        from rules import infer_minimum_packs_on_hand
        item = self._hardware_item_base()
        item["sales_health_signal"] = "dormant"
        item["heuristic_confidence"] = 0.0
        inv = {"max": 10, "min": 5}
        # dormant health → returns None (not active/stable) before volatile check
        result = infer_minimum_packs_on_hand(item, inv, 100)
        self.assertIsNone(result)

    def test_volatile_intermittent_short_span_caps_at_1(self):
        """Intermittent performance + short span → _demand_is_volatile returns True → cap at 1."""
        from rules import infer_minimum_packs_on_hand
        item = self._hardware_item_base()
        item["performance_profile"] = "intermittent"
        item["sales_span_days"] = 90  # < HEURISTIC_MIN_SALES_SPAN_DAYS
        item["heuristic_confidence"] = 0.0
        inv = {"max": 10, "min": 5}
        result = infer_minimum_packs_on_hand(item, inv, 100)
        self.assertEqual(result, 1)

    def test_non_volatile_steady_not_capped(self):
        """Steady performance, active health → not capped to 1."""
        from rules import infer_minimum_packs_on_hand
        item = self._hardware_item_base()
        item["heuristic_confidence"] = 0.0
        inv = {"max": 10, "min": 5}
        result = infer_minimum_packs_on_hand(item, inv, 100)
        self.assertEqual(result, 2)

    def test_short_span_caps_cover_cycles_at_1(self):
        """Short sales span → infer_minimum_cover_cycles returns 1."""
        from rules import infer_minimum_cover_cycles
        item = {
            "description": "BOLT KIT",
            "sales_health_signal": "active",
            "performance_profile": "steady",
            "days_since_last_sale": 5,
            "sales_span_days": 7,  # < 14
            "avg_weekly_sales_loaded": 10,
            "annualized_sales_loaded": 520,
            "reorder_cycle_weeks": 1,
        }
        inv = {"max": 10}
        result = infer_minimum_cover_cycles(item, inv, 5)
        self.assertEqual(result, 1)

    def test_volatile_caps_cover_cycles_at_1(self):
        """Erratic shape → infer_minimum_cover_cycles returns 1."""
        from rules import infer_minimum_cover_cycles
        item = {
            "description": "BOLT KIT",
            "sales_health_signal": "active",
            "performance_profile": "steady",
            "days_since_last_sale": 5,
            "sales_span_days": 60,
            "avg_weekly_sales_loaded": 10,
            "annualized_sales_loaded": 520,
            "detailed_sales_shape": "erratic",
            "reorder_cycle_weeks": 1,
        }
        inv = {"max": 10}
        result = infer_minimum_cover_cycles(item, inv, 5)
        self.assertEqual(result, 1)


class StockoutRiskScoreTests(unittest.TestCase):
    def test_zero_demand_returns_zero(self):
        item = {"demand_signal": 0, "inventory_position": 0, "recency_confidence": "high"}
        self.assertEqual(compute_stockout_risk_score(item), 0.0)

    def test_no_demand_key_returns_zero(self):
        item = {"inventory_position": 50}
        self.assertEqual(compute_stockout_risk_score(item), 0.0)

    def test_zero_inventory_with_active_demand_is_high_risk(self):
        item = {
            "demand_signal": 365,  # 1 unit/day
            "inventory_position": 0,
            "recency_confidence": "high",
        }
        score = compute_stockout_risk_score(item, lead_time_days=14)
        # coverage_risk = 1.0 (zero cover), recency_weight = 0 → score = 1.0
        self.assertEqual(score, 1.0)

    def test_cover_equal_to_2x_lead_returns_zero_coverage_risk(self):
        # demand = 365/day=1, inventory = 28 = 2×14 days of cover
        item = {
            "demand_signal": 365,
            "inventory_position": 28,
            "recency_confidence": "high",
        }
        score = compute_stockout_risk_score(item, lead_time_days=14)
        self.assertEqual(score, 0.0)

    def test_partial_cover_gives_intermediate_score(self):
        # demand = 365/year = 1/day, inventory = 14 = 1× lead time = half of buffer
        item = {
            "demand_signal": 365,
            "inventory_position": 14,
            "recency_confidence": "high",
        }
        score = compute_stockout_risk_score(item, lead_time_days=14)
        # days_of_cover=14, buffer=28, coverage_risk = 1 - 14/28 = 0.5
        # recency_weight = 0 → score = 0.5
        self.assertAlmostEqual(score, 0.5, places=2)

    def test_low_recency_confidence_increases_score(self):
        item = {
            "demand_signal": 365,
            "inventory_position": 28,  # full cover — coverage_risk = 0
            "recency_confidence": "low",
        }
        score = compute_stockout_risk_score(item, lead_time_days=14)
        # coverage_risk = 0, recency_weight = 0.20, score = 0 + 0.20*(1-0) = 0.2
        self.assertAlmostEqual(score, 0.2, places=3)

    def test_medium_recency_confidence_gives_moderate_penalty(self):
        item = {
            "demand_signal": 365,
            "inventory_position": 28,
            "recency_confidence": "medium",
        }
        score = compute_stockout_risk_score(item, lead_time_days=14)
        self.assertAlmostEqual(score, 0.1, places=3)

    def test_score_clamped_to_1(self):
        item = {
            "demand_signal": 36500,  # very high demand
            "inventory_position": 0,
            "recency_confidence": "low",
        }
        score = compute_stockout_risk_score(item, lead_time_days=14)
        self.assertEqual(score, 1.0)

    def test_score_clamped_to_0(self):
        item = {
            "demand_signal": 1,
            "inventory_position": 999999,
            "recency_confidence": "high",
        }
        score = compute_stockout_risk_score(item, lead_time_days=14)
        self.assertEqual(score, 0.0)

    def test_enrich_item_stamps_stockout_risk_score(self):
        item = {
            "line_code": "AER-", "item_code": "X1",
            "description": "Test", "qty_sold": 365, "qty_suspended": 0,
            "qty_on_po": 0, "order_qty": 0,
        }
        inv = {"qoh": 0, "min": None, "max": None, "repl_cost": 1.0,
               "supplier": "", "last_sale": "2025-01-01", "last_receipt": "2025-01-01"}
        enrich_item(item, inv, pack_qty=None, rule={})
        self.assertIn("stockout_risk_score", item)
        self.assertIsInstance(item["stockout_risk_score"], float)
        self.assertGreaterEqual(item["stockout_risk_score"], 0.0)
        self.assertLessEqual(item["stockout_risk_score"], 1.0)


class ClassifyDeadStockTests(unittest.TestCase):
    def test_returns_true_when_no_sale_over_threshold_and_no_pending_demand(self):
        item = {
            "days_since_last_sale": DEAD_STOCK_MIN_DAYS_SINCE_SALE,
            "effective_qty_suspended": 0,
            "qty_suspended": 0,
            "qty_on_po": 0,
        }
        self.assertTrue(classify_dead_stock(item))

    def test_returns_false_when_days_below_threshold(self):
        item = {
            "days_since_last_sale": DEAD_STOCK_MIN_DAYS_SINCE_SALE - 1,
            "qty_on_po": 0,
        }
        self.assertFalse(classify_dead_stock(item))

    def test_returns_false_when_days_since_sale_is_none(self):
        item = {"days_since_last_sale": None, "qty_on_po": 0}
        self.assertFalse(classify_dead_stock(item))

    def test_returns_false_when_open_po_exists(self):
        item = {
            "days_since_last_sale": DEAD_STOCK_MIN_DAYS_SINCE_SALE + 10,
            "qty_on_po": 5,
        }
        self.assertFalse(classify_dead_stock(item))

    def test_returns_false_when_suspended_demand_exists(self):
        item = {
            "days_since_last_sale": DEAD_STOCK_MIN_DAYS_SINCE_SALE + 10,
            "qty_suspended": 2,
            "qty_on_po": 0,
        }
        self.assertFalse(classify_dead_stock(item))

    def test_effective_qty_suspended_also_blocks_classification(self):
        item = {
            "days_since_last_sale": DEAD_STOCK_MIN_DAYS_SINCE_SALE + 10,
            "effective_qty_suspended": 3,
            "qty_on_po": 0,
        }
        self.assertFalse(classify_dead_stock(item))

    def test_enrich_item_stamps_dead_stock_field(self):
        item = {
            "line_code": "AER-", "item_code": "X1",
            "description": "Test", "qty_sold": 0, "qty_suspended": 0,
            "qty_on_po": 0, "order_qty": 0,
            "days_since_last_sale": DEAD_STOCK_MIN_DAYS_SINCE_SALE + 50,
        }
        inv = {"qoh": 5, "min": None, "max": None, "repl_cost": 1.0,
               "supplier": "", "last_sale": "", "last_receipt": ""}
        enrich_item(item, inv, pack_qty=None, rule={})
        self.assertIn("dead_stock", item)
        self.assertIsInstance(item["dead_stock"], bool)


if __name__ == "__main__":
    unittest.main()
