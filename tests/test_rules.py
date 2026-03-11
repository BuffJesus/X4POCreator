import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rules import (
    calculate_raw_need,
    calculate_suggested_qty,
    determine_order_policy,
    enrich_item,
    evaluate_item_status,
    get_buy_rule_summary,
    get_rule_pack_size,
    looks_like_reel_item,
)


class RulesTests(unittest.TestCase):
    def test_get_rule_pack_size_parses_numeric_strings(self):
        self.assertEqual(get_rule_pack_size({"pack_size": "500"}), 500)
        self.assertEqual(get_rule_pack_size({"pack_size": 12.0}), 12)
        self.assertIsNone(get_rule_pack_size({"pack_size": ""}))
        self.assertIsNone(get_rule_pack_size({"pack_size": "abc"}))

    def test_reel_review_when_pack_far_exceeds_max(self):
        policy = determine_order_policy({"description": '1/4" 2WIRE 6500PSI HOSE'}, {"max": 100}, 500, None)
        self.assertEqual(policy, "reel_review")

    def test_boxed_hardware_pack_is_not_auto_marked_reel_review(self):
        policy = determine_order_policy({"description": "1/4 X 1 ELEVATOR BOLT"}, {"max": 20}, 100, None)
        self.assertEqual(policy, "standard")

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

    def test_calculate_raw_need_returns_zero_when_qoh_and_on_po_cover_target(self):
        item = {
            "inventory": {"qoh": 12, "max": 20},
            "qty_on_po": 10,
            "demand_signal": 4,
            "suggested_max": 18,
        }
        self.assertEqual(calculate_raw_need(item), 0)

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
        enrich_item(item, {"max": 100}, 500, None)
        self.assertEqual(item["order_policy"], "reel_review")
        self.assertEqual(item["status"], "review")
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
        self.assertIn("↓OK", summary)


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


if __name__ == "__main__":
    unittest.main()
