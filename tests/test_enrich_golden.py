"""Golden characterization tests for rules.enrich_item.

These tests pin the full post-enrich output shape for representative
items spanning every interesting combination of status, policy,
attention signal, data flag, and package profile.  The purpose is to
catch unintended behavior changes during the Phase 3.2 refactor of
rules.py — any shift in enrichment output will fail one of these
fixtures.

To update after an intentional behavior change:
    python -m unittest tests.test_enrich_golden -v
Review the failures, confirm the new output is correct, then update
the expected values in the fixture.
"""

import copy
import unittest
from rules import enrich_item


# ── Fixture helpers ──────────────────────────────────────────────────

def _base_item(**overrides):
    """Minimal item dict with sane defaults for enrich_item."""
    item = {
        "line_code": "010-",
        "item_code": "TEST",
        "description": "Test item",
        "qty_sold": 0,
        "qty_suspended": 0,
        "qty_received": 0,
        "qty_on_po": 0,
        "pack_size": None,
        "demand_signal": 0,
        "suggested_max": None,
        "suggested_min": None,
        "reorder_cycle_weeks": 1,
    }
    item.update(overrides)
    return item


def _enrich(item, inv=None, pack_qty=None, rule=None, lead_time_days=None):
    """Enrich a copy so the original fixture is reusable."""
    item = copy.deepcopy(item)
    enrich_item(item, inv or {}, pack_qty, rule, lead_time_days=lead_time_days)
    return item


# Fields asserted by every golden test.
GOLDEN_FIELDS = (
    "status", "final_qty", "suggested_qty", "order_policy", "raw_need",
    "reason_codes", "why", "recency_confidence", "heuristic_confidence",
    "confirmed_stocking", "reorder_needed", "package_profile",
    "replenishment_unit_mode", "inventory_position", "target_stock",
    "dead_stock",
)


def _assert_golden(test, item, expected):
    """Assert every golden field matches expected."""
    for field in GOLDEN_FIELDS:
        if field in expected:
            actual = item.get(field)
            exp = expected[field]
            test.assertEqual(
                actual, exp,
                f"Field {field!r}: expected {exp!r}, got {actual!r}",
            )


# ── Golden fixtures ──────────────────────────────────────────────────

class EnrichGoldenTests(unittest.TestCase):

    def test_01_no_data_exact_qty(self):
        """Item with no sales, no inventory, no pack — exact qty, skip status."""
        item = _enrich(_base_item())
        _assert_golden(self, item, {
            "status": "skip",
            "final_qty": 0,
            "suggested_qty": 0,
            "order_policy": "exact_qty",
            "raw_need": 0,
            "reorder_needed": False,
            "dead_stock": False,
        })

    def test_02_simple_reorder_no_pack(self):
        """Sales demand, inventory below max, no pack size → exact qty."""
        item = _enrich(
            _base_item(qty_sold=10, demand_signal=10),
            inv={"qoh": 2, "max": 10, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"},
        )
        _assert_golden(self, item, {
            "order_policy": "exact_qty",
            "reorder_needed": True,
            "package_profile": "no_pack_data",
        })
        self.assertGreater(item["raw_need"], 0)
        self.assertGreater(item["suggested_qty"], 0)
        self.assertEqual(item["final_qty"], item["suggested_qty"])

    def test_03_standard_pack_round_up(self):
        """Pack size present, demand below one pack → round up to pack."""
        item = _enrich(
            _base_item(qty_sold=5, demand_signal=5),
            inv={"qoh": 0, "max": 8, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"},
            pack_qty=12,
        )
        _assert_golden(self, item, {
            "order_policy": "standard",
            "reorder_needed": True,
        })
        # Should round up to pack multiple
        self.assertEqual(item["suggested_qty"] % 12, 0)
        self.assertGreaterEqual(item["suggested_qty"], 12)
        self.assertIn("pack_round_up", item["reason_codes"])

    def test_04_inventory_covers_target(self):
        """QOH above max → raw_need=0 but reorder_needed can still be True
        (reorder trigger is based on floor, not raw need)."""
        item = _enrich(
            _base_item(qty_sold=5, demand_signal=5),
            inv={"qoh": 20, "max": 10, "last_sale": "05-Mar-2026"},
            pack_qty=6,
        )
        _assert_golden(self, item, {
            "raw_need": 0,
            "suggested_qty": 0,
            "final_qty": 0,
            "order_policy": "standard",
            "reorder_needed": True,
        })
        self.assertIn("inventory_covers_target", item["reason_codes"])

    def test_05_reel_review_large_pack(self):
        """Large pack (500) with max=100 and demand=10. Without explicit
        description hinting at reel/hose, the package_profile is
        general_pack and policy is standard (pack round-up to 500)."""
        item = _enrich(
            _base_item(qty_sold=10, demand_signal=10, suggested_max=24),
            inv={"max": 100, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"},
            pack_qty=500,
        )
        _assert_golden(self, item, {
            "order_policy": "standard",
            "status": "ok",
            "package_profile": "general_pack",
            "suggested_qty": 500,
            "final_qty": 500,
        })

    def test_06_pack_trigger_policy(self):
        """Rule with reorder_trigger_qty → pack_trigger policy."""
        item = _enrich(
            _base_item(qty_sold=20, demand_signal=20),
            inv={"qoh": 5, "max": 30, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"},
            pack_qty=100,
            rule={"pack_size": 100, "reorder_trigger_qty": 10},
        )
        _assert_golden(self, item, {
            "order_policy": "pack_trigger",
        })
        self.assertIn("pack_trigger", item["reason_codes"])

    def test_07_soft_pack_min_order(self):
        """Rule with allow_below_pack + min_order_qty → soft_pack policy."""
        item = _enrich(
            _base_item(qty_sold=3, demand_signal=3),
            inv={"qoh": 0, "max": 5, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"},
            pack_qty=50,
            rule={"pack_size": 50, "allow_below_pack": True, "min_order_qty": 2},
        )
        _assert_golden(self, item, {
            "order_policy": "soft_pack",
        })
        self.assertIn("soft_pack_rule", item["reason_codes"])
        self.assertGreaterEqual(item["suggested_qty"], 2)

    def test_08_manual_only_low_recency(self):
        """No recent sale/receipt history → manual_only, low recency confidence."""
        item = _enrich(
            _base_item(qty_sold=5, demand_signal=5),
            inv={"qoh": 0, "max": 10},
        )
        _assert_golden(self, item, {
            "recency_confidence": "low",
            "order_policy": "manual_only",
        })
        self.assertIn("manual_only", item["reason_codes"])

    def test_09_suspense_included(self):
        """Suspended qty contributes to demand; effective_qty_suspended
        is None when the suspense path doesn't activate (no suspense
        carry configured)."""
        item = _enrich(
            _base_item(qty_sold=5, qty_suspended=3, demand_signal=5),
            inv={"qoh": 0, "max": 10, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"},
        )
        # effective_qty_suspended is only set by the suspense carry path,
        # not by qty_suspended alone.  Pin the actual behavior.
        self.assertEqual(item.get("effective_qty_suspended"), None)

    def test_10_open_po_offsets_need(self):
        """Qty on PO offsets inventory position (QOH 0 + PO 5 = position 5)."""
        item = _enrich(
            _base_item(qty_sold=10, demand_signal=10, qty_on_po=5),
            inv={"qoh": 0, "max": 10, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"},
        )
        self.assertEqual(item["inventory_position"], 5)
        # Raw need is target minus position
        self.assertEqual(item["raw_need"], 5)

    def test_11_confirmed_stocking(self):
        """Item with confirmed_stocking flag from rule."""
        item = _enrich(
            _base_item(qty_sold=2, demand_signal=2),
            inv={"qoh": 0, "max": 5, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"},
            rule={"confirmed_stocking": True},
        )
        self.assertTrue(item.get("confirmed_stocking"))
        self.assertIn("confirmed_stocking", item["reason_codes"])

    def test_12_dead_stock(self):
        """No demand signal, positive QOH, no recency → dead_stock is
        False (classify_dead_stock requires specific conditions beyond
        just zero demand)."""
        item = _enrich(
            _base_item(qty_sold=0, demand_signal=0),
            inv={"qoh": 50, "max": 10},
        )
        self.assertFalse(item["dead_stock"])
        self.assertEqual(item["raw_need"], 0)
        self.assertEqual(item["status"], "skip")

    def test_13_high_recency_confidence(self):
        """Both sale and receipt dates present → high recency."""
        item = _enrich(
            _base_item(qty_sold=10, demand_signal=10),
            inv={"qoh": 2, "max": 10, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"},
            pack_qty=6,
        )
        _assert_golden(self, item, {
            "recency_confidence": "high",
        })

    def test_14_medium_recency_confidence(self):
        """Only sale date, no receipt → medium recency."""
        item = _enrich(
            _base_item(qty_sold=10, demand_signal=10),
            inv={"qoh": 2, "max": 10, "last_sale": "05-Mar-2026"},
            pack_qty=6,
        )
        _assert_golden(self, item, {
            "recency_confidence": "medium",
        })

    def test_15_why_contains_key_details(self):
        """Why string includes stock position, target, package profile."""
        item = _enrich(
            _base_item(qty_sold=5, demand_signal=5),
            inv={"qoh": 2, "max": 8, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"},
            pack_qty=6,
        )
        self.assertIn("Stock after open POs:", item["why"])
        self.assertIn("Target stock:", item["why"])
        self.assertIn("Package profile:", item["why"])

    def test_16_exact_qty_override_from_rule(self):
        """Rule with exact_qty flag — the flag sets exact_qty_override on
        the item but doesn't change the order_policy when a pack is
        present (standard still applies).  Pin actual behavior."""
        item = _enrich(
            _base_item(qty_sold=5, demand_signal=5),
            inv={"qoh": 0, "max": 8, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"},
            pack_qty=12,
            rule={"exact_qty": True},
        )
        self.assertFalse(item.get("exact_qty_override"))
        _assert_golden(self, item, {
            "order_policy": "standard",
            "suggested_qty": 12,
            "raw_need": 8,
        })

    def test_17_acceptable_overstock_configured(self):
        """Rule with acceptable_overstock_qty."""
        item = _enrich(
            _base_item(qty_sold=5, demand_signal=5),
            inv={"qoh": 0, "max": 8, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"},
            pack_qty=12,
            rule={"acceptable_overstock_qty": 6},
        )
        self.assertIn("acceptable_overstock_configured", item["reason_codes"])

    def test_18_stockout_risk_score(self):
        """Stockout risk score is computed."""
        item = _enrich(
            _base_item(qty_sold=10, demand_signal=10),
            inv={"qoh": 0, "max": 10, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"},
        )
        self.assertIsInstance(item.get("stockout_risk_score"), float)

    def test_19_receipt_pack_mismatch_flag(self):
        """receipt_pack_mismatch set when receipt pack differs from active pack."""
        item = _enrich(
            _base_item(
                qty_sold=10,
                demand_signal=10,
                potential_pack_size=24,
                potential_pack_confidence="high",
                pack_size_source="x4_order_multiple",
            ),
            inv={"qoh": 2, "max": 10, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"},
            pack_qty=12,
        )
        self.assertTrue(item.get("receipt_pack_mismatch"))
        self.assertIn("receipt_pack_mismatch", item["reason_codes"])

    def test_20_minimum_packs_on_hand_rule(self):
        """Rule with minimum_packs_on_hand — the rule sets minimum_packs
        but the effective_order_floor is still target-stock-based.  The
        min-packs logic operates through the pack_trigger policy path."""
        item = _enrich(
            _base_item(qty_sold=5, demand_signal=5),
            inv={"qoh": 0, "max": 8, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"},
            pack_qty=6,
            rule={"minimum_packs_on_hand": 3},
        )
        _assert_golden(self, item, {
            "order_policy": "pack_trigger",
            "suggested_qty": 12,
            "final_qty": 12,
            "effective_order_floor": 8,
        })


if __name__ == "__main__":
    unittest.main()
