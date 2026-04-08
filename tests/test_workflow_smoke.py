"""
End-to-end workflow smoke tests.

These tests exercise the full load → session → assignment → export pipeline
with real minimal CSV files, covering the kind of integration issues that only
surface when all flow modules work together (and that unit tests of individual
modules cannot catch).

They serve as the packaged-app workflow confidence check called for in Phase 1
of the roadmap.
"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import assignment_flow
import export_flow
import load_flow
from models import AppSessionState


# ---------------------------------------------------------------------------
# Helpers for building minimal representative CSV files
# ---------------------------------------------------------------------------

def _write_inventory_csv(path, rows):
    """
    Write a minimal On Hand / Min Max inventory CSV.

    Each row dict must have: line_code, item_code, qoh, repl_cost, min, max,
    ytd_sales, mo12_sales, supplier.  Columns 0-2 are padding so that
    lc_col resolves to index 3 (matching real X4 export layout).
    """
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        # Header row (ignored by parser — it looks for the first row that
        # contains a trailing-dash line-code fragment)
        writer.writerow(["Branch", "Status", "Customer",
                         "PG", "Item_Code", "Description",
                         "Item_Class", "QOH", "Repl_Cost",
                         "X4_Min", "X4_Max",  # col 9/10 not used by parser
                         "Min", "Max", "YTD_Sales", "12M_Sales", "Supplier",
                         "Last_Receipt", "Last_Sale"])
        for r in rows:
            writer.writerow([
                "", "", "",
                r["line_code"], r["item_code"], r.get("description", ""),
                "",
                str(r.get("qoh", 0)), str(r.get("repl_cost", 0)),
                "", "",
                str(r.get("min", 0)), str(r.get("max", 0)),
                str(r.get("ytd_sales", 0)), str(r.get("mo12_sales", 0)),
                r.get("supplier", ""),
                r.get("last_receipt", ""), r.get("last_sale", ""),
            ])


def _write_detailed_sales_csv(path, rows):
    """
    Write a minimal DETAILED PART SALES CSV in X4 layout.

    The X4 layout has a single long header row containing the report title and
    then the data rows in fixed column positions (col 24 = PG+item token,
    col 25 = description, col 26 = qty, col 31 = sale date).
    """
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        # X4 header that the parser uses to detect this layout
        header = [
            "Product Groups: ALL", "Branches: 1",
            "From: 01-Jan-2025 to 31-Mar-2026",
            "DETAILED PART SALES", " 8:00:00AM", "01-Apr-2026",
            "Sales Category: ALL", "Page -1 of 1",
            "Item\n\nCode", "Description", "Total\n\nQuantity", "Qty On Hand",
            "Extended\n\nSelling", "Extended\n\nCost",
            "Gross\n\nProfit", "Gross\n\nMargin",
            "Slmn", "BRANCH", "1", "3366629",
            "27,781,031.47", "18,810,903.78", "8,970,127.69", "32.29",
        ]
        # The data items start at col 24
        for r in rows:
            lc = r["line_code"].rstrip("-")
            # When line_code is blank, emit just the item code (no prefix dash)
            token = f"{lc}-{r['item_code']}" if lc else r["item_code"]
            # col 26 (Total Quantity) is the X4 group total — repeated on
            # every detail row — so the parser reads the per-line qty from
            # col 36 instead.  Mirror that here.
            data_cols = [
                token, r.get("description", ""),
                str(r.get("qty_sold", 1)), "0",
                "0", "0", "0", "0",
                r["line_code"], "SLMN", "527394", "VENDORCO",
                str(r.get("qty_sold", 1)), "1.00", "", "19.29",
                "17.54", "1.75", "9.07", "27",
            ]
            # sale_date at col 31 = header(24 cols) + offset 7 within data_cols
            # Rebuild to ensure col 31 = sale_date
            full_row = header[:]
            full_row.extend(data_cols)
            # col 31 relative to start = index 31
            while len(full_row) <= 31:
                full_row.append("")
            full_row[31] = r.get("sale_date", "15-Mar-2026")
            writer.writerow(full_row)


def _write_received_parts_csv(path, rows):
    """
    Write a minimal ReceivedPartsDetail CSV in X4 layout.

    X4 layout: col 14 = date, col 15 = line_code, col 16 = item_code,
    col 17 = description, col 18 = vendor, col 19 = type (RC/RR),
    col 22 = qty_received.
    """
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        header = [
            "RECEIVED PARTS DETAIL\n\nFrom 2025-01-01 to 2026-04-01",
            "2026-04-01\n\n\n 6:59:01AM\n\n\nPage -1 of 1",
            "Date", "PG", "Item_Code", "Description", "Vendor",
            "Major/Minor", "Ext Cost", "Qty Rec'd",
            "Net\n\nPurchases", "Stock\n\nReturns",
            "Warranty Returns ", "Dirty Core\n\n Returns",
        ]
        for r in rows:
            full_row = header[:]
            # pad to col 22
            while len(full_row) < 23:
                full_row.append("")
            full_row[14] = r.get("receipt_date", "15-Mar-2026")
            full_row[15] = r["line_code"]
            full_row[16] = r["item_code"]
            full_row[17] = r.get("description", "")
            full_row[18] = r.get("vendor", "")
            full_row[19] = r.get("type", "RC")
            full_row[20] = str(r.get("ext_cost", "0"))
            full_row[21] = str(r.get("qty_received", 1))
            full_row[22] = str(r.get("qty_received", 1))
            writer.writerow(full_row)


def _make_session_callbacks(session, *, vendor="VENDORCO", pack_size=6):
    """Return the minimal callback dict for prepare_assignment_session."""
    return dict(
        excluded_line_codes=set(),
        excluded_customers=set(),
        dup_whitelist=set(),
        ignored_keys=set(),
        lookback_days=14,
        order_history_path=str(ROOT / "_smoke_test_order_history.json"),
        vendor_codes_path=str(ROOT / "_smoke_test_vendor_codes.txt"),
        known_vendors=[vendor],
        get_suspense_carry_qty=lambda key: 0,
        default_vendor_for_key=lambda key: vendor,
        resolve_pack_size=lambda key: pack_size,
        suggest_min_max=lambda key: (None, None),
        get_cycle_weeks=lambda: 2,
        get_rule_key=lambda lc, ic: f"{lc}:{ic}",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class WorkflowSmokeTests(unittest.TestCase):
    """
    Integration tests that run the full load → session → assignment → export
    pipeline with real file I/O through the actual flow modules.
    """

    def _run_full_pipeline(self, inv_rows, sales_rows, receipt_rows, *,
                           vendor="VENDORCO", pack_size=6):
        """
        Write CSV fixtures, run parse_all_files + apply_load_result +
        prepare_assignment_session, and return the populated session.
        """
        with tempfile.TemporaryDirectory() as tmp:
            inv_path = str(Path(tmp) / "On Hand Min Max.csv")
            sales_path = str(Path(tmp) / "DETAILED PART SALES.csv")
            recv_path = str(Path(tmp) / "ReceivedPartsDetail.csv")

            _write_inventory_csv(inv_path, inv_rows)
            _write_detailed_sales_csv(sales_path, sales_rows)
            _write_received_parts_csv(recv_path, receipt_rows)

            paths = {
                "minmax": inv_path,
                "detailedsales": sales_path,
                "receivedparts": recv_path,
            }

            with patch("load_flow._save_parse_cache"):
                result = load_flow.parse_all_files(
                    paths,
                    old_po_warning_days=30,
                    short_sales_window_days=14,
                )

        session = AppSessionState(order_rules={})
        load_flow.apply_load_result(session, result)

        callbacks = _make_session_callbacks(session, vendor=vendor, pack_size=pack_size)
        with patch("assignment_flow.storage.get_recent_orders", return_value={}), \
             patch("assignment_flow.storage.load_vendor_codes", return_value=[vendor]):
            assignment_flow.prepare_assignment_session(session, **callbacks)

        return session

    # ------------------------------------------------------------------
    # Basic item appearance
    # ------------------------------------------------------------------

    def test_item_with_sales_appears_in_filtered_items(self):
        session = self._run_full_pipeline(
            inv_rows=[{"line_code": "AER-", "item_code": "GH781", "qoh": 2,
                       "min": 5, "max": 20, "ytd_sales": 12, "mo12_sales": 12,
                       "supplier": "VENDORCO", "repl_cost": 5.0}],
            sales_rows=[{"line_code": "AER-", "item_code": "GH781",
                         "description": "HOSE", "qty_sold": 9,
                         "sale_date": "15-Mar-2026"}],
            receipt_rows=[{"line_code": "AER-", "item_code": "GH781",
                           "vendor": "VENDORCO", "qty_received": 6,
                           "receipt_date": "01-Mar-2026"}],
        )
        self.assertEqual(len(session.filtered_items), 1)
        item = session.filtered_items[0]
        self.assertEqual(item["line_code"], "AER-")
        self.assertEqual(item["item_code"], "GH781")
        self.assertEqual(item["qty_sold"], 9)
        self.assertEqual(item["vendor"], "VENDORCO")
        self.assertGreater(item["order_qty"], 0)

    def test_item_with_no_demand_and_sufficient_stock_is_excluded(self):
        # No sales data path — build session state directly to exercise
        # assignment_flow's filtering logic without going through parse_all_files.
        session = AppSessionState(
            sales_items=[],
            inventory_lookup={("AER-", "GH781"): {"qoh": 50, "min": 5, "max": 20}},
            order_rules={},
        )
        callbacks = _make_session_callbacks(session)
        with patch("assignment_flow.storage.get_recent_orders", return_value={}), \
             patch("assignment_flow.storage.load_vendor_codes", return_value=["VENDORCO"]):
            assignment_flow.prepare_assignment_session(session, **callbacks)
        self.assertEqual(len(session.filtered_items), 0)

    def test_inventory_only_item_below_min_is_preserved(self):
        # No sales data path — build session state directly.
        session = AppSessionState(
            sales_items=[],
            inventory_lookup={("AER-", "GH781"): {"qoh": 1, "min": 5, "max": 20}},
            order_rules={},
        )
        callbacks = _make_session_callbacks(session)
        with patch("assignment_flow.storage.get_recent_orders", return_value={}), \
             patch("assignment_flow.storage.load_vendor_codes", return_value=["VENDORCO"]):
            assignment_flow.prepare_assignment_session(session, **callbacks)
        self.assertEqual(len(session.filtered_items), 1)
        item = session.filtered_items[0]
        self.assertTrue(item.get("candidate_preserved"))
        self.assertIn("candidate_preserved", item.get("reason_codes", []))

    # ------------------------------------------------------------------
    # Multi-item session
    # ------------------------------------------------------------------

    def test_multiple_items_all_appear_in_session(self):
        session = self._run_full_pipeline(
            inv_rows=[
                {"line_code": "AER-", "item_code": "GH781", "qoh": 2,
                 "min": 5, "max": 20, "ytd_sales": 10, "mo12_sales": 10,
                 "supplier": "VENDORCO", "repl_cost": 5.0},
                {"line_code": "AER-", "item_code": "GH782", "qoh": 0,
                 "min": 3, "max": 12, "ytd_sales": 6, "mo12_sales": 6,
                 "supplier": "VENDORCO", "repl_cost": 3.0},
            ],
            sales_rows=[
                {"line_code": "AER-", "item_code": "GH781",
                 "description": "HOSE A", "qty_sold": 9,
                 "sale_date": "15-Mar-2026"},
                {"line_code": "AER-", "item_code": "GH782",
                 "description": "HOSE B", "qty_sold": 5,
                 "sale_date": "20-Mar-2026"},
            ],
            receipt_rows=[
                {"line_code": "AER-", "item_code": "GH781",
                 "vendor": "VENDORCO", "qty_received": 6,
                 "receipt_date": "01-Mar-2026"},
                {"line_code": "AER-", "item_code": "GH782",
                 "vendor": "VENDORCO", "qty_received": 3,
                 "receipt_date": "05-Mar-2026"},
            ],
        )
        item_codes = {i["item_code"] for i in session.filtered_items}
        self.assertIn("GH781", item_codes)
        self.assertIn("GH782", item_codes)

    # ------------------------------------------------------------------
    # Assignment → export pipeline
    # ------------------------------------------------------------------

    def test_assigned_item_appears_in_export_groups(self):
        session = self._run_full_pipeline(
            inv_rows=[{"line_code": "AER-", "item_code": "GH781", "qoh": 2,
                       "min": 5, "max": 20, "ytd_sales": 12, "mo12_sales": 12,
                       "supplier": "VENDORCO", "repl_cost": 5.0}],
            sales_rows=[{"line_code": "AER-", "item_code": "GH781",
                         "description": "HOSE", "qty_sold": 9,
                         "sale_date": "15-Mar-2026"}],
            receipt_rows=[{"line_code": "AER-", "item_code": "GH781",
                           "vendor": "VENDORCO", "qty_received": 6,
                           "receipt_date": "01-Mar-2026"}],
        )
        self.assertEqual(len(session.filtered_items), 1)

        # Simulate the user assigning a vendor and order qty
        item = dict(session.filtered_items[0])
        item["vendor"] = "VENDORCO"
        item["order_qty"] = 12
        session.assigned_items = [item]

        groups = export_flow.group_assigned_items(session.assigned_items)
        self.assertIn("VENDORCO", groups)
        self.assertEqual(len(groups["VENDORCO"]), 1)
        self.assertEqual(groups["VENDORCO"][0]["order_qty"], 12)

    def test_release_now_items_partition_as_exportable(self):
        session = self._run_full_pipeline(
            inv_rows=[{"line_code": "AER-", "item_code": "GH781", "qoh": 2,
                       "min": 5, "max": 20, "ytd_sales": 12, "mo12_sales": 12,
                       "supplier": "VENDORCO", "repl_cost": 5.0}],
            sales_rows=[{"line_code": "AER-", "item_code": "GH781",
                         "description": "HOSE", "qty_sold": 9,
                         "sale_date": "15-Mar-2026"}],
            receipt_rows=[{"line_code": "AER-", "item_code": "GH781",
                           "vendor": "VENDORCO", "qty_received": 6,
                           "receipt_date": "01-Mar-2026"}],
        )
        item = dict(session.filtered_items[0])
        item["vendor"] = "VENDORCO"
        item["order_qty"] = 12
        item["release_decision"] = "release_now"
        session.assigned_items = [item]

        exportable, held = export_flow.partition_export_items(session.assigned_items)
        self.assertEqual(len(exportable), 1)
        self.assertEqual(len(held), 0)

    def test_held_item_partitions_as_held(self):
        session = self._run_full_pipeline(
            inv_rows=[{"line_code": "AER-", "item_code": "GH781", "qoh": 2,
                       "min": 5, "max": 20, "ytd_sales": 12, "mo12_sales": 12,
                       "supplier": "VENDORCO", "repl_cost": 5.0}],
            sales_rows=[{"line_code": "AER-", "item_code": "GH781",
                         "description": "HOSE", "qty_sold": 9,
                         "sale_date": "15-Mar-2026"}],
            receipt_rows=[{"line_code": "AER-", "item_code": "GH781",
                           "vendor": "VENDORCO", "qty_received": 6,
                           "receipt_date": "01-Mar-2026"}],
        )
        item = dict(session.filtered_items[0])
        item["vendor"] = "VENDORCO"
        item["order_qty"] = 6
        item["release_decision"] = "hold_for_threshold"
        item["release_reason"] = "Held for threshold"
        session.assigned_items = [item]

        exportable, held = export_flow.partition_export_items(session.assigned_items)
        self.assertEqual(len(exportable), 0)
        self.assertEqual(len(held), 1)

    # ------------------------------------------------------------------
    # Detailed pair: line code resolution through inventory
    # ------------------------------------------------------------------

    def test_detailed_sales_line_code_resolves_from_inventory(self):
        """
        Detailed sales rows with blank line codes are resolved to the line code
        from the inventory lookup when there is only one candidate.
        """
        session = self._run_full_pipeline(
            inv_rows=[{"line_code": "AER-", "item_code": "GH999", "qoh": 0,
                       "min": 5, "max": 20, "ytd_sales": 10, "mo12_sales": 10,
                       "supplier": "VENDORCO", "repl_cost": 5.0}],
            sales_rows=[{"line_code": "", "item_code": "GH999",
                         "description": "WIDGET", "qty_sold": 5,
                         "sale_date": "15-Mar-2026"}],
            receipt_rows=[{"line_code": "AER-", "item_code": "GH999",
                           "vendor": "VENDORCO", "qty_received": 6,
                           "receipt_date": "01-Mar-2026"}],
        )
        self.assertEqual(len(session.filtered_items), 1)
        self.assertEqual(session.filtered_items[0]["line_code"], "AER-")
        self.assertEqual(session.filtered_items[0]["item_code"], "GH999")

    # ------------------------------------------------------------------
    # Dash-bearing line codes (regression: v0.1.24 fix)
    # ------------------------------------------------------------------

    def test_dash_bearing_line_code_resolves_through_full_pipeline(self):
        """
        Items with dash-bearing line codes (e.g. A-B-) must appear in the
        session with the correct line code after load and assignment.
        """
        session = self._run_full_pipeline(
            inv_rows=[{"line_code": "A-B-", "item_code": "12345", "qoh": 2,
                       "min": 5, "max": 20, "ytd_sales": 8, "mo12_sales": 8,
                       "supplier": "VENDORCO", "repl_cost": 3.0}],
            sales_rows=[{"line_code": "A-B-", "item_code": "12345",
                         "description": "DASH WIDGET", "qty_sold": 6,
                         "sale_date": "15-Mar-2026"}],
            receipt_rows=[{"line_code": "A-B-", "item_code": "12345",
                           "vendor": "VENDORCO", "qty_received": 6,
                           "receipt_date": "01-Mar-2026"}],
        )
        self.assertEqual(len(session.filtered_items), 1)
        item = session.filtered_items[0]
        self.assertEqual(item["line_code"], "A-B-")
        self.assertEqual(item["item_code"], "12345")
        self.assertEqual(item["vendor"], "VENDORCO")

    # ------------------------------------------------------------------
    # Sales window and session metadata
    # ------------------------------------------------------------------

    def test_sales_window_is_populated_after_load(self):
        session = self._run_full_pipeline(
            inv_rows=[{"line_code": "AER-", "item_code": "GH781", "qoh": 2,
                       "min": 5, "max": 20, "ytd_sales": 12, "mo12_sales": 12,
                       "supplier": "VENDORCO", "repl_cost": 5.0}],
            sales_rows=[{"line_code": "AER-", "item_code": "GH781",
                         "description": "HOSE", "qty_sold": 9,
                         "sale_date": "15-Mar-2026"}],
            receipt_rows=[{"line_code": "AER-", "item_code": "GH781",
                           "vendor": "VENDORCO", "qty_received": 6,
                           "receipt_date": "01-Mar-2026"}],
        )
        self.assertIsNotNone(session.sales_window_start or session.sales_span_days)


if __name__ == "__main__":
    unittest.main()
