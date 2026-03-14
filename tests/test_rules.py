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
    has_pack_trigger_fields,
    infer_minimum_packs_on_hand,
    looks_like_hardware_pack_item,
    looks_like_reel_item,
    should_large_pack_review,
)


class RulesTests(unittest.TestCase):
    def test_get_rule_pack_size_parses_numeric_strings(self):
        self.assertEqual(get_rule_pack_size({"pack_size": "500"}), 500)
        self.assertEqual(get_rule_pack_size({"pack_size": 12.0}), 12)
        self.assertIsNone(get_rule_pack_size({"pack_size": ""}))
        self.assertIsNone(get_rule_pack_size({"pack_size": "abc"}))

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

    def test_infer_minimum_packs_on_hand_skips_stale_hardware(self):
        item = {
            "description": "5/16 HEX NUT",
            "sales_health_signal": "dormant",
            "performance_profile": "legacy",
            "days_since_last_sale": 500,
        }
        self.assertIsNone(infer_minimum_packs_on_hand(item, {"max": 20}, 100))

    def test_reel_review_when_pack_far_exceeds_max(self):
        policy = determine_order_policy({"description": '1/4" 2WIRE 6500PSI HOSE'}, {"max": 100}, 500, None)
        self.assertEqual(policy, "reel_review")

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
        self.assertEqual(item["status"], "review")
        self.assertTrue(item["reorder_needed"])
        self.assertIn("reel_review", item["data_flags"])
        self.assertIn("Target stock", item["why"])

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
        self.assertEqual(item["effective_target_stock"], 60)
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
        self.assertEqual(item["effective_target_stock"], 45)
        self.assertIn("Minimum cover days: 21", item["why"])

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
        self.assertEqual(item["effective_target_stock"], 200)
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
        self.assertEqual(item["order_policy"], "large_pack_review")
        self.assertTrue(item["review_required"])
        self.assertEqual(item["status"], "review")
        self.assertIn("large_pack_review", item["reason_codes"])
        self.assertIn("large_pack_review", item["data_flags"])

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
            "qty_on_po": 0,
            "pack_size": 1,
            "demand_signal": 1,
        }

        enrich_item(item, {"qoh": 0, "min": 0, "max": 1}, 1, None)
        self.assertEqual(item["recency_confidence"], "low")
        self.assertEqual(item["data_completeness"], "missing_recency")
        self.assertEqual(item["recency_review_bucket"], "new_or_sparse")
        self.assertEqual(item["order_policy"], "manual_only")
        self.assertEqual(item["suggested_qty"], 0)
        self.assertIn("may be new or too sparse", item["why"])

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


if __name__ == "__main__":
    unittest.main()
