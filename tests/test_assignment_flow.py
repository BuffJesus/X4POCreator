import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import assignment_flow
from models import AppSessionState


class AssignmentFlowTests(unittest.TestCase):
    def test_prepare_assignment_session_builds_filtered_items_and_duplicates(self):
        session = AppSessionState(
            sales_items=[{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_received": 0,
                "qty_sold": 9,
            }],
            po_items=[{"line_code": "AER-", "item_code": "GH781-4", "qty": 2}],
            inventory_lookup={
                ("AER-", "GH781-4"): {"qoh": 0, "max": 10},
                ("ALT-", "GH781-4"): {"qoh": 1, "max": 2},
            },
            order_rules={},
        )

        with patch("assignment_flow.storage.get_recent_orders", return_value={("AER-", "GH781-4"): [{"qty": 1}]}), \
             patch("assignment_flow.storage.load_vendor_codes", return_value=["MOTION"]):
            result = assignment_flow.prepare_assignment_session(
                session,
                excluded_line_codes=set(),
                excluded_customers=set(),
                dup_whitelist=set(),
                ignored_keys=set(),
                lookback_days=14,
                order_history_path=str(ROOT / "test_order_history.json"),
                vendor_codes_path=str(ROOT / "test_vendor_codes.txt"),
                known_vendors=["MOTION"],
                get_suspense_carry_qty=lambda key: 0,
                default_vendor_for_key=lambda key: "MOTION",
                resolve_pack_size=lambda key: 6,
                suggest_min_max=lambda key: (None, None),
                get_rule_key=lambda lc, ic: f"{lc}:{ic}",
            )

        self.assertTrue(result)
        self.assertEqual(len(session.filtered_items), 1)
        self.assertEqual(session.filtered_items[0]["vendor"], "MOTION")
        self.assertEqual(session.filtered_items[0]["qty_on_po"], 2)
        self.assertEqual(session.filtered_items[0]["performance_profile"], "legacy")
        self.assertEqual(session.filtered_items[0]["sales_health_signal"], "unknown")
        self.assertIn("GH781-4", session.duplicate_ic_lookup)
        self.assertEqual(session.recent_orders[("AER-", "GH781-4")][0]["qty"], 1)

    def test_prepare_assignment_session_returns_false_when_no_items_remain(self):
        session = AppSessionState(
            sales_items=[{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_received": 0,
                "qty_sold": 0,
            }],
            inventory_lookup={("AER-", "GH781-4"): {"qoh": 5, "min": 0, "max": 10}},
            order_rules={},
        )

        with patch("assignment_flow.storage.get_recent_orders", return_value={}), \
             patch("assignment_flow.storage.load_vendor_codes", return_value=[]):
            result = assignment_flow.prepare_assignment_session(
                session,
                excluded_line_codes={"AER-"},
                excluded_customers=set(),
                dup_whitelist=set(),
                ignored_keys=set(),
                lookback_days=14,
                order_history_path=str(ROOT / "test_order_history.json"),
                vendor_codes_path=str(ROOT / "test_vendor_codes.txt"),
                known_vendors=[],
                get_suspense_carry_qty=lambda key: 0,
                default_vendor_for_key=lambda key: "",
                resolve_pack_size=lambda key: None,
                suggest_min_max=lambda key: (None, None),
                get_rule_key=lambda lc, ic: f"{lc}:{ic}",
            )

        self.assertFalse(result)
        self.assertEqual(session.filtered_items, [])

    def test_prepare_assignment_session_skips_persistently_ignored_items(self):
        session = AppSessionState(
            sales_items=[{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_received": 0,
                "qty_sold": 9,
            }],
            inventory_lookup={
                ("AER-", "GH781-4"): {"qoh": 0, "max": 10},
            },
            order_rules={},
        )

        with patch("assignment_flow.storage.get_recent_orders", return_value={}), \
             patch("assignment_flow.storage.load_vendor_codes", return_value=[]):
            result = assignment_flow.prepare_assignment_session(
                session,
                excluded_line_codes=set(),
                excluded_customers=set(),
                dup_whitelist=set(),
                ignored_keys={"AER-:GH781-4"},
                lookback_days=14,
                order_history_path=str(ROOT / "test_order_history.json"),
                vendor_codes_path=str(ROOT / "test_vendor_codes.txt"),
                known_vendors=[],
                get_suspense_carry_qty=lambda key: 0,
                default_vendor_for_key=lambda key: "",
                resolve_pack_size=lambda key: None,
                suggest_min_max=lambda key: (None, None),
                get_rule_key=lambda lc, ic: f"{lc}:{ic}",
            )

        self.assertFalse(result)
        self.assertEqual(session.filtered_items, [])


if __name__ == "__main__":
    unittest.main()
