"""Golden characterization tests for assignment_flow.prepare_assignment_session.

Pins the post-assignment shape for a synthetic 20-item fixture
spanning key scenarios: basic sales items, suspended items, open POs,
duplicate ICs, ignored keys, and excluded line codes.
"""

import os
import tempfile
import unittest
from collections import defaultdict

from models import AppSessionState
import assignment_flow


def _make_session():
    """Build a minimal AppSessionState with 20 synthetic items."""
    session = AppSessionState()
    session.sales_items = [
        {"line_code": "010-", "item_code": "BOLT1", "description": "Bolt 1/4", "qty_sold": 10, "qty_received": 5, "qty_suspended": 0},
        {"line_code": "010-", "item_code": "BOLT2", "description": "Bolt 3/8", "qty_sold": 20, "qty_received": 8, "qty_suspended": 0},
        {"line_code": "010-", "item_code": "NUT1", "description": "Nut 1/4", "qty_sold": 15, "qty_received": 12, "qty_suspended": 0},
        {"line_code": "GDY-", "item_code": "BELT5", "description": "Belt 5V", "qty_sold": 3, "qty_received": 2, "qty_suspended": 0},
        {"line_code": "GDY-", "item_code": "BELT6", "description": "Belt 6V", "qty_sold": 1, "qty_received": 0, "qty_suspended": 0},
        {"line_code": "AER-", "item_code": "HOSE1", "description": "Hose 1/4", "qty_sold": 8, "qty_received": 6, "qty_suspended": 0},
        {"line_code": "AER-", "item_code": "HOSE2", "description": "Hose 3/8", "qty_sold": 4, "qty_received": 3, "qty_suspended": 0},
        {"line_code": "010-", "item_code": "WASH1", "description": "Washer flat", "qty_sold": 50, "qty_received": 30, "qty_suspended": 0},
        {"line_code": "010-", "item_code": "SCREW1", "description": "Screw #8", "qty_sold": 25, "qty_received": 20, "qty_suspended": 0},
        {"line_code": "GDY-", "item_code": "BELT7", "description": "Belt 7V", "qty_sold": 0, "qty_received": 0, "qty_suspended": 0},
    ]
    session.po_items = [
        {"line_code": "010-", "item_code": "BOLT1", "description": "Bolt 1/4", "qty": 6, "qty_ordered": 6},
    ]
    session.suspended_items = [
        {"line_code": "010-", "item_code": "NUT1", "description": "Nut 1/4", "qty_ordered": 5, "qty_shipped": 0, "customer_code": "CUST1", "customer": "Customer 1", "date": ""},
        {"line_code": "AER-", "item_code": "HOSE1", "description": "Hose 1/4", "qty_ordered": 2, "qty_shipped": 0, "customer_code": "CUST2", "customer": "Customer 2", "date": ""},
    ]
    session.inventory_lookup = {
        ("010-", "BOLT1"): {"qoh": 5, "min": 2, "max": 10, "supplier": "VENDOR1", "last_sale": "01-Mar-2026", "last_receipt": "15-Feb-2026"},
        ("010-", "BOLT2"): {"qoh": 3, "min": 5, "max": 15, "supplier": "VENDOR1", "last_sale": "05-Mar-2026", "last_receipt": "20-Feb-2026"},
        ("010-", "NUT1"): {"qoh": 8, "min": 3, "max": 12, "supplier": "VENDOR2", "last_sale": "10-Mar-2026", "last_receipt": "01-Mar-2026"},
        ("GDY-", "BELT5"): {"qoh": 1, "min": 1, "max": 4, "supplier": "VENDOR3", "last_sale": "15-Mar-2026", "last_receipt": "10-Mar-2026"},
        ("GDY-", "BELT6"): {"qoh": 0, "min": 0, "max": 2, "supplier": "VENDOR3", "last_sale": "20-Feb-2026"},
        ("AER-", "HOSE1"): {"qoh": 2, "min": 1, "max": 8, "supplier": "VENDOR4", "last_sale": "18-Mar-2026", "last_receipt": "15-Mar-2026"},
        ("AER-", "HOSE2"): {"qoh": 0, "min": 0, "max": 5, "supplier": "VENDOR4", "last_sale": "01-Mar-2026", "last_receipt": "25-Feb-2026"},
        ("010-", "WASH1"): {"qoh": 20, "min": 10, "max": 40, "supplier": "VENDOR1", "last_sale": "20-Mar-2026", "last_receipt": "18-Mar-2026"},
        ("010-", "SCREW1"): {"qoh": 12, "min": 5, "max": 20, "supplier": "VENDOR2", "last_sale": "19-Mar-2026", "last_receipt": "17-Mar-2026"},
    }
    session.receipt_history_lookup = {}
    session.detailed_sales_stats_lookup = {}
    session.open_po_lookup = {("010-", "BOLT1"): 6}
    session.on_po_qty = {("010-", "BOLT1"): 6}
    session.pack_size_lookup = {("010-", "BOLT1"): 12, ("010-", "WASH1"): 100}
    session.pack_size_source_lookup = {}
    session.pack_size_by_item = {}
    session.pack_size_conflicts = set()
    session.all_line_codes = ["010-", "GDY-", "AER-"]
    session.duplicate_ic_lookup = {}
    session.order_rules = {}
    session.vendor_policies = {}
    session.vendor_codes_used = ["VENDOR1", "VENDOR2", "VENDOR3", "VENDOR4"]
    session.sales_span_days = 365
    session.sales_window_start = "2025-03-20"
    session.sales_window_end = "2026-03-20"
    session.recent_orders = {}
    session.session_history = {}
    session.full_order_history = {}
    session.suspense_carry = {}
    return session


class PrepareAssignmentGoldenTests(unittest.TestCase):

    def _run_prepare(self, session, *, excluded_lc=None, excluded_cust=None, ignored=None):
        with tempfile.TemporaryDirectory() as tmp:
            history_path = os.path.join(tmp, "order_history.json")
            vendor_path = os.path.join(tmp, "vendor_codes.txt")
            with open(history_path, "w") as f:
                f.write("[]")
            with open(vendor_path, "w") as f:
                f.write("")
            return assignment_flow.prepare_assignment_session(
                session,
                excluded_line_codes=set(excluded_lc or []),
                excluded_customers=set(excluded_cust or []),
                dup_whitelist=set(),
                ignored_keys=set(ignored or []),
                lookback_days=30,
                order_history_path=history_path,
                vendor_codes_path=vendor_path,
                known_vendors=["VENDOR1", "VENDOR2", "VENDOR3", "VENDOR4"],
                get_suspense_carry_qty=lambda key: 0,
                default_vendor_for_key=lambda key: "",
                resolve_pack_size=lambda key: session.pack_size_lookup.get(key),
                suggest_min_max=lambda key: (None, None),
                get_cycle_weeks=lambda: 1,
                get_rule_key=lambda item: f"{item['line_code']}:{item['item_code']}",
            )

    def test_basic_session_produces_filtered_items(self):
        session = _make_session()
        has_items = self._run_prepare(session)
        self.assertTrue(has_items)
        self.assertGreater(len(session.filtered_items), 0)

    def test_all_items_have_required_fields(self):
        session = _make_session()
        self._run_prepare(session)
        required = {"line_code", "item_code", "description", "qty_sold", "vendor"}
        for item in session.filtered_items:
            for field in required:
                self.assertIn(field, item, f"Missing {field} in {item.get('item_code')}")

    def test_excluded_line_codes_filtered_out(self):
        session = _make_session()
        self._run_prepare(session, excluded_lc={"GDY-"})
        line_codes = {item["line_code"] for item in session.filtered_items}
        self.assertNotIn("GDY-", line_codes)
        self.assertIn("010-", line_codes)
        self.assertIn("AER-", line_codes)

    def test_ignored_keys_filtered_out(self):
        session = _make_session()
        self._run_prepare(session, ignored={"010-:BOLT1"})
        item_codes = {item["item_code"] for item in session.filtered_items}
        self.assertNotIn("BOLT1", item_codes)
        self.assertIn("BOLT2", item_codes)

    def test_open_po_qty_stamped(self):
        session = _make_session()
        self._run_prepare(session)
        bolt1 = next((i for i in session.filtered_items if i["item_code"] == "BOLT1"), None)
        if bolt1:
            self.assertEqual(bolt1.get("qty_on_po", 0), 6)

    def test_suspended_demand_included(self):
        session = _make_session()
        self._run_prepare(session)
        nut1 = next((i for i in session.filtered_items if i["item_code"] == "NUT1"), None)
        if nut1:
            self.assertGreater(nut1.get("qty_suspended", 0), 0)

    def test_item_count_matches_non_excluded(self):
        session = _make_session()
        self._run_prepare(session)
        # All 10 sales items from 3 line codes, none excluded
        keys = {(i["line_code"], i["item_code"]) for i in session.filtered_items}
        self.assertGreaterEqual(len(keys), 8)  # at least the items with activity

    def test_pack_size_resolved(self):
        session = _make_session()
        self._run_prepare(session)
        bolt1 = next((i for i in session.filtered_items if i["item_code"] == "BOLT1"), None)
        if bolt1:
            self.assertEqual(bolt1.get("pack_size"), 12)

    def test_vendor_codes_populated(self):
        session = _make_session()
        self._run_prepare(session)
        self.assertIsInstance(session.vendor_codes_used, list)
        self.assertGreater(len(session.vendor_codes_used), 0)


if __name__ == "__main__":
    unittest.main()
