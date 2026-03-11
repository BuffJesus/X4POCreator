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


if __name__ == "__main__":
    unittest.main()
