"""Tests for parsers.db_source and load_flow.parse_from_database using a fake
DB-API connection (no Informix client needed).

These lock in the DB-direct contract: correct key tuples (trailing dash, casing),
correct lookup value shapes, receipt_cost_lookup falling out of the aggregator,
and that the full downstream load pipeline runs on a DB source_bundle exactly as
it does on CSVs.
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers import db_source
import load_flow


class _FakeCursor:
    def __init__(self, dataset):
        self._dataset = dataset
        self._rows = []
        self.description = None

    def execute(self, sql, params=()):
        s = " ".join(sql.split())
        if "SET ROLE" in s:
            self._rows = []
            self.description = None
            return
        if "FROM whse" in s:
            key = "inventory"
        elif "FROM invoice_detail" in s:
            key = "sales"
        elif "FROM po_detail" in s:
            key = "receipts"
        elif "order_multiple" in s:
            key = "pack"
        else:
            raise AssertionError(f"unexpected SQL: {s[:60]}")
        cols, rows = self._dataset[key]
        self.description = [(c,) for c in cols]
        self._rows = list(rows)

    def fetchmany(self, n):
        batch, self._rows = self._rows[:n], self._rows[n:]
        return batch

    def close(self):
        pass


class _FakeConnection:
    def __init__(self, dataset):
        self._dataset = dataset

    def cursor(self):
        return _FakeCursor(self._dataset)


def _dataset():
    d = datetime.date
    return {
        "inventory": (
            ["line_code", "item_code", "description", "qoh", "repl_cost",
             "min_stk", "max_stk", "ytd_sales", "supplier", "last_receipt", "last_sale"],
            [
                # product_group already carries the dash; supplier lower-case to
                # prove normalization; dates as real date objects.
                ("AER-", "GH781-4", "HOSE", 2, 10.0, 1, 5, 40, "motion",
                 d(2026, 3, 2), d(2026, 3, 1)),
                # product_group WITHOUT a dash -> must gain one.
                ("ABC", "1", "WIDGET", 0, 3.5, 0, 4, 0, "SOURCE",
                 d(2026, 2, 1), d(2026, 2, 2)),
            ],
        ),
        "sales": (
            ["line_code", "item_code", "description", "qty_sold", "sale_date"],
            [
                ("AER-", "GH781-4", "HOSE", 4, d(2026, 3, 1)),
                ("AER-", "GH781-4", "HOSE", 2, d(2026, 3, 10)),
            ],
        ),
        "receipts": (
            ["line_code", "item_code", "description", "qty_received",
             "ext_cost", "receipt_date", "vendor"],
            [
                ("AER-", "GH781-4", "HOSE", 3, 30.0, d(2026, 3, 2), "motion"),
            ],
        ),
        "pack": (
            ["line_code", "item_code", "pack_size"],
            [("AER-", "GH781-4", 2), ("ABC", "1", 0)],
        ),
    }


class DbSourceContractTests(unittest.TestCase):
    def setUp(self):
        self.conn = _FakeConnection(_dataset())

    def test_inventory_lookup_shape_and_keys(self):
        inv = db_source.load_inventory_lookup(self.conn)
        # trailing dash guaranteed on both rows
        self.assertIn(("AER-", "GH781-4"), inv)
        self.assertIn(("ABC-", "1"), inv)
        entry = inv[("AER-", "GH781-4")]
        self.assertEqual(entry["qoh"], 2.0)
        self.assertEqual(entry["repl_cost"], 10.0)
        self.assertEqual(entry["min"], 1)
        self.assertEqual(entry["max"], 5)
        self.assertEqual(entry["ytd_sales"], 40)
        self.assertEqual(entry["supplier"], "MOTION")  # upper-normalized
        self.assertEqual(entry["last_receipt"], "2026-03-02")  # ISO string
        # full contract keys present
        for field in ("description", "qoh", "repl_cost", "min", "max",
                      "ytd_sales", "mo12_sales", "supplier", "last_receipt", "last_sale"):
            self.assertIn(field, entry)

    def test_pack_size_lookup_drops_nonpositive(self):
        packs = db_source.load_pack_size_lookup(self.conn)
        self.assertEqual(packs, {("AER-", "GH781-4"): 2})

    def test_bundle_receipt_cost_and_sales(self):
        bundle = db_source.build_source_bundle(self.conn)
        # receipt_cost_lookup = 30.0 / 3 = 10.0, keyed identically
        self.assertAlmostEqual(bundle["receipt_cost_lookup"][("AER-", "GH781-4")], 10.0)
        # sales_items aggregated qty_sold 4+2 = 6, qty_received 3
        sales = {(s["line_code"], s["item_code"]): s for s in bundle["sales_items"]}
        self.assertEqual(sales[("AER-", "GH781-4")]["qty_sold"], 6)
        self.assertEqual(sales[("AER-", "GH781-4")]["qty_received"], 3)
        self.assertIn("inventory_lookup", bundle)
        self.assertIn("pack_size_lookup", bundle)


class ParseFromDatabaseTests(unittest.TestCase):
    def test_full_pipeline_runs_on_db_bundle(self):
        conn = _FakeConnection(_dataset())
        result = load_flow.parse_from_database(
            conn,
            old_po_warning_days=90,
            short_sales_window_days=7,
        )
        self.assertEqual(result["sales_source_mode"], "database")
        # inventory came from the DB, keyed with trailing dash
        self.assertIn(("AER-", "GH781-4"), result["inventory_lookup"])
        self.assertEqual(result["pack_size_lookup"][("AER-", "GH781-4")], 2)
        # sales window spans 2026-03-01..2026-03-10 -> 10 days
        self.assertEqual(result["sales_span_days"], 10)
        # a short-window warning should fire (10 >= 7 so NOT short) -> ensure key present
        self.assertEqual(result["sales_window_start"], "2026-03-01")
        # downstream stats annualized without error
        stats = result["detailed_sales_stats_lookup"][("AER-", "GH781-4")]
        self.assertEqual(stats["qty_sold_total"], 6)

    def test_db_load_is_not_cached(self):
        # Two DB loads must both hit the DB (no file-signature cache collision).
        conn = _FakeConnection(_dataset())
        r1 = load_flow.parse_from_database(conn, old_po_warning_days=90, short_sales_window_days=7)
        r2 = load_flow.parse_from_database(conn, old_po_warning_days=90, short_sales_window_days=7)
        self.assertEqual(r1["sales_source_mode"], "database")
        self.assertEqual(r2["sales_source_mode"], "database")


if __name__ == "__main__":
    unittest.main()
