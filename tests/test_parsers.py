import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import parsers


class ParserSmokeTests(unittest.TestCase):
    def test_identify_packsize_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pack.csv"
            path.write_text(
                "Items WITH Order Multiple,09-Mar-2026,Product_Group,Item_Code,Description,Order_Multiple,Pkg\n",
                encoding="utf-8-sig",
            )
            self.assertEqual(parsers.identify_report_type(str(path)), "packsize")

    def test_identify_report_type_skips_leading_blank_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sales.csv"
            path.write_text(
                "\n\nPart Sales & Receipts,From: 01-Mar-2026 thru 10-Mar-2026\n",
                encoding="utf-8-sig",
            )
            self.assertEqual(parsers.identify_report_type(str(path)), "sales")

    def test_scan_directory_for_reports_finds_files_with_blank_leading_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            sales = Path(tmp) / "sales.csv"
            onhand = Path(tmp) / "onhand.csv"
            sales.write_text(
                "\nPart Sales & Receipts,From: 01-Mar-2026 thru 10-Mar-2026\n",
                encoding="utf-8-sig",
            )
            onhand.write_text(
                "\nON HAND REPORT,09-Mar-2026\n",
                encoding="utf-8-sig",
            )

            found = parsers.scan_directory_for_reports(tmp)

            self.assertEqual(found["sales"], str(sales))
            self.assertEqual(found["onhand"], str(onhand))

    def test_identify_report_type_detects_detailed_sales_and_received_parts_by_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            detailed = Path(tmp) / "DETAILEDPARTSALES.csv"
            received = Path(tmp) / "ReceivedPartsDetail.csv"
            detailed.write_text("line code,item code,qty sold,sale date\n", encoding="utf-8-sig")
            received.write_text("line code,item code,qty received,vendor,receipt date\n", encoding="utf-8-sig")

            self.assertEqual(parsers.identify_report_type(str(detailed)), "detailedsales")
            self.assertEqual(parsers.identify_report_type(str(received)), "receivedparts")

    def test_parse_pack_sizes_generic_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "generic_pack.csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["line code", "item code", "pack size"])
                writer.writerow(["AER-", "GH781-4", "500"])
            lookup = parsers.parse_pack_sizes_csv(str(path))
            self.assertEqual(lookup[("AER-", "GH781-4")], 500)

    def test_parse_pack_sizes_generic_csv_skips_leading_blank_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "generic_pack_blank.csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([])
                writer.writerow(["line code", "item code", "pack size"])
                writer.writerow(["AER-", "GH781-4", "500"])

            lookup = parsers.parse_pack_sizes_csv(str(path))

            self.assertEqual(lookup[("AER-", "GH781-4")], 500)

    def test_parse_pack_sizes_x4_csv_skips_leading_blank_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x4_pack_blank.csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([])
                writer.writerow(["Items WITH Order Multiple"])
                writer.writerow(["hdr", "AER-", "GH781-4", "DESC", "500"])

            lookup = parsers.parse_pack_sizes_csv(str(path))

            self.assertEqual(lookup[("AER-", "GH781-4")], 500)

    def test_parse_part_sales_csv_drops_only_identical_duplicate_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sales.csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["hdr", "AER-", "GH781-4", "HOSE", "5", "skip", "7"])
                writer.writerow(["hdr", "AER-", "GH781-4", "HOSE", "5", "skip", "7"])
                writer.writerow(["hdr2", "AER-", "GH781-4", "HOSE", "5", "skip", "7"])

            rows = parsers.parse_part_sales_csv(str(path))

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["qty_received"], 10)
            self.assertEqual(rows[0]["qty_sold"], 14)

    def test_parse_detailed_part_sales_and_received_parts_detail_build_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            detailed = Path(tmp) / "detailed.csv"
            received = Path(tmp) / "received.csv"
            with open(detailed, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["line code", "item code", "description", "qty sold", "sale date"])
                writer.writerow(["AER-", "GH781-4", "HOSE", "2", "01-Mar-2026"])
                writer.writerow(["AER-", "GH781-4", "HOSE", "3", "05-Mar-2026"])
            with open(received, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["line code", "item code", "description", "qty received", "vendor", "receipt date"])
                writer.writerow(["AER-", "GH781-4", "HOSE", "4", "motion", "02-Mar-2026"])
                writer.writerow(["AER-", "GH781-4", "HOSE", "1", "motion", "06-Mar-2026"])

            sales_rows = parsers.parse_detailed_part_sales_csv(str(detailed))
            receipt_rows = parsers.parse_received_parts_detail_csv(str(received))
            summary = parsers.build_sales_receipt_summary(sales_rows, receipt_rows)
            sales_start, sales_end = parsers.parse_detailed_sales_date_range(sales_rows)

            self.assertEqual(summary, [{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_received": 5,
                "qty_sold": 5,
            }])
            self.assertEqual(sales_start.date().isoformat(), "2026-03-01")
            self.assertEqual(sales_end.date().isoformat(), "2026-03-05")

    def test_build_receipt_history_lookup_ranks_vendors_by_recency_then_quantity(self):
        receipt_rows = [
            {
                "line_code": "AER-",
                "item_code": "GH781-4",
                "qty_received": 2,
                "vendor": "SOURCE",
                "receipt_date": "01-Mar-2026",
            },
            {
                "line_code": "AER-",
                "item_code": "GH781-4",
                "qty_received": 5,
                "vendor": "MOTION",
                "receipt_date": "05-Mar-2026",
            },
        ]

        history = parsers.build_receipt_history_lookup(receipt_rows)

        self.assertEqual(history[("AER-", "GH781-4")]["primary_vendor"], "MOTION")
        self.assertEqual(history[("AER-", "GH781-4")]["vendor_candidates"], ["MOTION", "SOURCE"])
        self.assertEqual(history[("AER-", "GH781-4")]["last_receipt_date"], "2026-03-05")
        self.assertEqual(history[("AER-", "GH781-4")]["vendor_confidence"], "medium")
        self.assertEqual(history[("AER-", "GH781-4")]["vendor_confidence_reason"], "dominant_but_mixed_vendor")

    def test_build_receipt_history_lookup_marks_mixed_vendor_history_low_confidence(self):
        receipt_rows = [
            {"line_code": "AER-", "item_code": "GH781-4", "qty_received": 4, "vendor": "MOTION", "receipt_date": "01-Mar-2026"},
            {"line_code": "AER-", "item_code": "GH781-4", "qty_received": 3, "vendor": "SOURCE", "receipt_date": "03-Mar-2026"},
            {"line_code": "AER-", "item_code": "GH781-4", "qty_received": 3, "vendor": "GREGDIST", "receipt_date": "05-Mar-2026"},
        ]

        history = parsers.build_receipt_history_lookup(receipt_rows)[("AER-", "GH781-4")]

        self.assertEqual(history["vendor_confidence"], "low")
        self.assertEqual(history["vendor_confidence_reason"], "mixed_vendor_history")
        self.assertTrue(history["vendor_ambiguous"])

    def test_build_detailed_sales_stats_lookup_captures_transaction_shape(self):
        sales_rows = [
            {"line_code": "AER-", "item_code": "GH781-4", "qty_sold": 1, "sale_date": "01-Mar-2026"},
            {"line_code": "AER-", "item_code": "GH781-4", "qty_sold": 3, "sale_date": "03-Mar-2026"},
            {"line_code": "AER-", "item_code": "GH781-4", "qty_sold": 5, "sale_date": "07-Mar-2026"},
        ]

        stats = parsers.build_detailed_sales_stats_lookup(sales_rows)[("AER-", "GH781-4")]

        self.assertEqual(stats["transaction_count"], 3)
        self.assertEqual(stats["qty_sold_total"], 9)
        self.assertEqual(stats["sale_day_count"], 3)
        self.assertEqual(stats["first_sale_date"], "2026-03-01")
        self.assertEqual(stats["last_sale_date"], "2026-03-07")
        self.assertEqual(stats["avg_units_per_transaction"], 3.0)
        self.assertEqual(stats["median_units_per_transaction"], 3)
        self.assertEqual(stats["max_units_per_transaction"], 5)
        self.assertEqual(stats["avg_days_between_sales"], 3.0)

    def test_build_pack_size_fallbacks_detects_conflicts(self):
        lookup = {
            ("AER-", "GH781-4"): 500,
            ("AER-", "GH781-5"): 100,
            ("BCA-", "GH781-4"): 250,
        }
        fallback, conflicts = parsers.build_pack_size_fallbacks(lookup)
        self.assertEqual(fallback["GH781-5"], 100)
        self.assertIn("GH781-4", conflicts)

    def test_parse_po_listing_csv_captures_po_number_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "po.csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["PO12345", "AER-", "GH781-4", "S", "6", "skip", "01-Jan-2026"])

            rows = parsers.parse_po_listing_csv(str(path))

            self.assertEqual(rows[0]["po_number"], "PO12345")
            self.assertEqual(rows[0]["po_type"], "S")

    def test_parse_suspended_csv_skips_leading_blank_rows_for_x4_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "susp.csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([])
                writer.writerow(["SUSPENSE REPORT"])
                writer.writerow([
                    "hdr", "AER-", "GH781-4", "HOSE", "x", "x", "x", "x", "x", "x",
                    "x", "01-Mar-2026", "C001", "Customer One", "x", "REF1", "3", "1",
                ])

            items, seen = parsers.parse_suspended_csv(str(path))

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["customer_code"], "C001")
            self.assertIn(("AER-", "GH781-4"), seen)

    def test_parse_suspended_csv_skips_leading_blank_rows_for_generic_header_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "susp_generic.csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([])
                writer.writerow(["line code", "item code"])
                writer.writerow(["AER-", "GH781-4"])

            items, seen = parsers.parse_suspended_csv(str(path))

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["line_code"], "AER-")
            self.assertEqual(items[0]["item_code"], "GH781-4")
            self.assertIn(("AER-", "GH781-4"), seen)

    def test_parse_on_hand_min_max_preserves_blank_qoh_and_cost_as_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "minmax.csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "hdr", "AER-", "GH781-4", "", "", "x", "x", "2", "6", "11", "22", "MOTION", "01-Mar-2026", "05-Mar-2026",
                ])

            lookup = parsers.parse_on_hand_min_max(str(path))

            self.assertIsNone(lookup[("AER-", "GH781-4")]["qoh"])
            self.assertIsNone(lookup[("AER-", "GH781-4")]["repl_cost"])


if __name__ == "__main__":
    unittest.main()
