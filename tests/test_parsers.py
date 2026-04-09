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

    def test_parse_pack_sizes_generic_csv_accepts_slash_line_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "generic_pack_slash.csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["line code", "item code", "pack size"])
                writer.writerow(["B/B-", "GH781-4", "500"])

            lookup = parsers.parse_pack_sizes_csv(str(path))

            self.assertEqual(lookup[("B/B-", "GH781-4")], 500)

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

    def test_parse_detailed_pair_aggregates_matches_summary_stats_and_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            detailed = Path(tmp) / "detailed.csv"
            received = Path(tmp) / "received.csv"
            with open(detailed, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["line code", "item code", "description", "qty sold", "sale date"])
                writer.writerow(["AER-", "GH781-4", "HOSE", "2", "01-Mar-2026"])
                writer.writerow(["AER-", "GH781-4", "HOSE", "3", "05-Mar-2026"])
                writer.writerow(["AER-", "GH781-4", "HOSE", "3", "05-Mar-2026"])
            with open(received, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["line code", "item code", "description", "qty received", "vendor", "receipt date"])
                writer.writerow(["AER-", "GH781-4", "HOSE", "4", "motion", "02-Mar-2026"])
                writer.writerow(["AER-", "GH781-4", "HOSE", "1", "motion", "06-Mar-2026"])

            aggregates = parsers.parse_detailed_pair_aggregates(str(detailed), str(received))

            self.assertEqual(aggregates["sales_items"], [{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_received": 5,
                "qty_sold": 5,
            }])
            self.assertEqual(aggregates["sales_window"][0].date().isoformat(), "2026-03-01")
            self.assertEqual(aggregates["sales_window"][1].date().isoformat(), "2026-03-05")
            stats = aggregates["detailed_sales_stats_lookup"][("AER-", "GH781-4")]
            self.assertEqual(stats["transaction_count"], 2)
            self.assertEqual(stats["qty_sold_total"], 5)
            self.assertEqual(stats["sale_day_count"], 2)
            receipt = aggregates["receipt_history_lookup"][("AER-", "GH781-4")]
            self.assertEqual(receipt["primary_vendor"], "MOTION")
            self.assertEqual(receipt["receipt_count"], 2)
            self.assertEqual(receipt["qty_received_total"], 5)
            self.assertEqual(aggregates["detailed_sales_rows"], [{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_sold": 5,
                "row_count": 2,
            }])

    def test_parse_received_parts_detail_x4_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ReceivedPartsDetail.csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "RECEIVED PARTS DETAIL\n\nFrom 2018-03-26 to 2026-03-16",
                    "2026-03-16\n\n\n 6:59:01AM\n\n\nPage -1 of 1",
                    "Date", "PG", "Item_Code", "Description", "Vendor", "Major/Minor",
                    "Ext Cost", "Qty Rec'd", "Net\n\nPurchases", "Stock\n\nReturns",
                    "Warranty Returns ", "Dirty Core\n\n Returns",
                    "26-Mar-2018", "FAR-", "X107-C", "3/8 EXTRUDED STREET TEE",
                    "UNISELE", "RR", "3", "9.84", "4.00", "9.84", "0.00", "0.00",
                    "0.00", "15,770,378", "245,523", "23,969", "77,840",
                ])

            rows = parsers.parse_received_parts_detail_csv(str(path))

        self.assertEqual(rows, [{
            "line_code": "FAR-",
            "item_code": "X107-C",
            "description": "3/8 EXTRUDED STREET TEE",
            "qty_received": 4,
            "receipt_date": "26-Mar-2018",
            "vendor": "UNISELE",
        }])

    def test_parse_detailed_part_sales_x4_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "DETAILED PART SALES.csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Product Groups: ALL", "Branches: 1", "From: 26-Mar-2018 to 31-Mar-2026",
                    "DETAILED PART SALES", " 8:29:38AM", "16-Mar-2026", "Sales Category: ALL",
                    "Page -1 of 1", "Item\n\nCode", "Description", "Total\n\nQuantity", "Qty On Hand",
                    "Extended\n\nSelling", "Extended\n\nCost", "Gross\n\nProfit", "Gross\n\nMargin",
                    "Slmn", "BRANCH", "1", "3366629", "27,781,031.47", "18,810,903.78",
                    "8,970,127.69", "32.29", "010-00055062", "GLOBAL STRIPE", "3", "19.29", "17.54",
                    "1.75", "9.07", "20-Nov-2019", "harley", "527394", "BROOBEST", "19.29", "3.00",
                    "", "19.29", "17.54", "1.75", "9.07", "27",
                ])

            rows = parsers.parse_detailed_part_sales_csv(str(path))

        self.assertEqual(rows, [{
            "line_code": "010-",
            "item_code": "00055062",
            "description": "GLOBAL STRIPE",
            "qty_sold": 3,
            "sale_date": "20-Nov-2019",
        }])

    def test_parse_detailed_part_sales_x4_layout_tolerates_spaces_around_line_code_separator(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "DETAILED PART SALES.csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Product Groups: ALL", "Branches: 1", "From: 26-Mar-2018 to 31-Mar-2026",
                    "DETAILED PART SALES", " 8:29:38AM", "16-Mar-2026", "Sales Category: ALL",
                    "Page -1 of 1", "Item\n\nCode", "Description", "Total\n\nQuantity", "Qty On Hand",
                    "Extended\n\nSelling", "Extended\n\nCost", "Gross\n\nProfit", "Gross\n\nMargin",
                    "Slmn", "BRANCH", "1", "3366629", "27,781,031.47", "18,810,903.78",
                    "8,970,127.69", "32.29", "010 - 00055062", "GLOBAL STRIPE", "3", "19.29", "17.54",
                    "1.75", "9.07", "20-Nov-2019", "harley", "527394", "BROOBEST", "19.29", "3.00",
                    "", "19.29", "17.54", "1.75", "9.07", "27",
                ])

            rows = parsers.parse_detailed_part_sales_csv(str(path))

        self.assertEqual(rows, [{
            "line_code": "010-",
            "item_code": "00055062",
            "description": "GLOBAL STRIPE",
            "qty_sold": 3,
            "sale_date": "20-Nov-2019",
        }])

    def test_parse_detailed_part_sales_x4_layout_accepts_slash_line_code_fragment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "DETAILED PART SALES.csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Product Groups: ALL", "Branches: 1", "From: 26-Mar-2018 to 31-Mar-2026",
                    "DETAILED PART SALES", " 8:29:38AM", "16-Mar-2026", "Sales Category: ALL",
                    "Page -1 of 1", "Item\n\nCode", "Description", "Total\n\nQuantity", "Qty On Hand",
                    "Extended\n\nSelling", "Extended\n\nCost", "Gross\n\nProfit", "Gross\n\nMargin",
                    "Slmn", "BRANCH", "1", "3366629", "27,781,031.47", "18,810,903.78",
                    "8,970,127.69", "32.29", "B/B-00055062", "GLOBAL STRIPE", "3", "19.29", "17.54",
                    "1.75", "9.07", "20-Nov-2019", "harley", "527394", "BROOBEST", "19.29", "3.00",
                    "", "19.29", "17.54", "1.75", "9.07", "27",
                ])

            rows = parsers.parse_detailed_part_sales_csv(str(path))

        self.assertEqual(rows, [{
            "line_code": "B/B-",
            "item_code": "00055062",
            "description": "GLOBAL STRIPE",
            "qty_sold": 3,
            "sale_date": "20-Nov-2019",
        }])

    def test_parse_received_parts_detail_x4_layout_accepts_slash_line_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ReceivedPartsDetail.csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "RECEIVED PARTS DETAIL\n\nFrom 2018-03-26 to 2026-03-16",
                    "2026-03-16\n\n\n 6:59:01AM\n\n\nPage -1 of 1",
                    "Date", "PG", "Item_Code", "Description", "Vendor", "Major/Minor",
                    "Ext Cost", "Qty Rec'd", "Net\n\nPurchases", "Stock\n\nReturns",
                    "Warranty Returns ", "Dirty Core\n\n Returns",
                    "26-Mar-2018", "C/W-", "X107-C", "3/8 EXTRUDED STREET TEE",
                    "UNISELE", "RR", "3", "9.84", "4.00", "9.84", "0.00", "0.00",
                    "0.00", "15,770,378", "245,523", "23,969", "77,840",
                ])

            rows = parsers.parse_received_parts_detail_csv(str(path))

        self.assertEqual(rows, [{
            "line_code": "C/W-",
            "item_code": "X107-C",
            "description": "3/8 EXTRUDED STREET TEE",
            "qty_received": 4,
            "receipt_date": "26-Mar-2018",
            "vendor": "UNISELE",
        }])

    def test_parse_detailed_part_sales_x4_layout_accepts_dash_line_code_fragment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "DETAILED PART SALES.csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Product Groups: ALL", "Branches: 1", "From: 26-Mar-2018 to 31-Mar-2026",
                    "DETAILED PART SALES", " 8:29:38AM", "16-Mar-2026", "Sales Category: ALL",
                    "Page -1 of 1", "Item\n\nCode", "Description", "Total\n\nQuantity", "Qty On Hand",
                    "Extended\n\nSelling", "Extended\n\nCost", "Gross\n\nProfit", "Gross\n\nMargin",
                    "Slmn", "BRANCH", "1", "3366629", "27,781,031.47", "18,810,903.78",
                    "8,970,127.69", "32.29", "A-B-12345", "WIDGET", "3", "19.29", "17.54",
                    "1.75", "9.07", "20-Nov-2019", "harley", "527394", "BROOBEST", "19.29", "3.00",
                    "", "19.29", "17.54", "1.75", "9.07", "27",
                ])

            rows = parsers.parse_detailed_part_sales_csv(str(path))

        self.assertEqual(rows, [{
            "line_code": "A-B-",
            "item_code": "12345",
            "description": "WIDGET",
            "qty_sold": 3,
            "sale_date": "20-Nov-2019",
        }])

    def test_parse_detailed_part_sales_x4_layout_resolves_k_dash_d_prefix_as_line_code(self):
        # K-D-1708: fixed-width split treats "K-D" as the 3-char line code fragment.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "DETAILED PART SALES.csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Product Groups: ALL", "Branches: 1", "From: 26-Mar-2018 to 31-Mar-2026",
                    "DETAILED PART SALES", " 8:29:38AM", "16-Mar-2026", "Sales Category: ALL",
                    "Page -1 of 1", "Item\n\nCode", "Description", "Total\n\nQuantity", "Qty On Hand",
                    "Extended\n\nSelling", "Extended\n\nCost", "Gross\n\nProfit", "Gross\n\nMargin",
                    "Slmn", "BRANCH", "1", "3366629", "27,781,031.47", "18,810,903.78",
                    "8,970,127.69", "32.29", "K-D-1708", "COUPLER", "3", "19.29", "17.54",
                    "1.75", "9.07", "20-Nov-2019", "harley", "527394", "BROOBEST", "19.29", "3.00",
                    "", "19.29", "17.54", "1.75", "9.07", "27",
                ])

            rows = parsers.parse_detailed_part_sales_csv(str(path))

        self.assertEqual(rows, [{
            "line_code": "K-D-",
            "item_code": "1708",
            "description": "COUPLER",
            "qty_sold": 3,
            "sale_date": "20-Nov-2019",
        }])

    def test_parse_detailed_part_sales_x4_layout_leaves_no_separator_token_unresolved(self):
        # Tokens where position 3 is not '-' cannot be an X4 line-code split.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "DETAILED PART SALES.csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Product Groups: ALL", "Branches: 1", "From: 26-Mar-2018 to 31-Mar-2026",
                    "DETAILED PART SALES", " 8:29:38AM", "16-Mar-2026", "Sales Category: ALL",
                    "Page -1 of 1", "Item\n\nCode", "Description", "Total\n\nQuantity", "Qty On Hand",
                    "Extended\n\nSelling", "Extended\n\nCost", "Gross\n\nProfit", "Gross\n\nMargin",
                    "Slmn", "BRANCH", "1", "3366629", "27,781,031.47", "18,810,903.78",
                    "8,970,127.69", "32.29", "AB-12345", "WIDGET", "3", "19.29", "17.54",
                    "1.75", "9.07", "20-Nov-2019", "harley", "527394", "BROOBEST", "19.29", "3.00",
                    "", "19.29", "17.54", "1.75", "9.07", "27",
                ])

            rows = parsers.parse_detailed_part_sales_csv(str(path))

        self.assertEqual(rows, [{
            "line_code": "",
            "item_code": "AB-12345",
            "description": "WIDGET",
            "qty_sold": 3,
            "sale_date": "20-Nov-2019",
        }])

    def test_parse_detailed_part_sales_x4_layout_uses_per_line_qty_not_repeated_total(self):
        # Regression: column 26 ("Total Quantity") is the X4 group total
        # repeated on every detail row.  Summing it across rows multiplied
        # the real qty by the row count.  Verify each detail row carries
        # its own per-line qty (col 36) and that aggregation matches the
        # repeated total exactly.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "DETAILED PART SALES.csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                header = [
                    "Product Groups: ALL", "Branches: 1", "From: 01-Jan-2026 to 07-Apr-2026",
                    "DETAILED PART SALES", "10:41:31AM", "07-Apr-2026", "Sales Category: ALL",
                    "Page -1 of 1", "Item\n\nCode", "Description", "Total\n\nQuantity", "Qty On Hand",
                    "Extended\n\nSelling", "Extended\n\nCost", "Gross\n\nProfit", "Gross\n\nMargin",
                    "Slmn", "BRANCH", "1", "116338", "1,070,950.18", "738,970.70",
                    "331,979.48", "31.00",
                ]
                per_line_qtys = ["2.00", "1.00", "1.00", "4.00", "4.00", "1.00"]
                dates = ["20-Mar-2026", "23-Mar-2026", "25-Mar-2026",
                         "13-Mar-2026", "15-Jan-2026", "24-Jan-2026"]
                for qty, date in zip(per_line_qtys, dates):
                    row = header + [
                        "GR1-4211-08-06", "ORB MALE CRIMP FITTING",
                        "13", "128.31", "68.46", "59.85", "46.64",
                        date, "Wiebes", "684608", "CASH2",
                        "10.56", qty, "", "21.12", "10.56", "10.56", "50.00", "42",
                    ]
                    writer.writerow(row)

            rows = parsers.parse_detailed_part_sales_csv(str(path))

        self.assertEqual(len(rows), 6)
        per_row_qtys = [r["qty_sold"] for r in rows]
        self.assertEqual(per_row_qtys, [2, 1, 1, 4, 4, 1])
        # Aggregation should equal the X4 Total Quantity (13), not 6×13=78.
        summary = parsers.build_sales_receipt_summary(rows, [])
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["qty_sold"], 13)
        self.assertEqual(summary[0]["line_code"], "GR1-")
        self.assertEqual(summary[0]["item_code"], "4211-08-06")

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

    def test_build_receipt_history_lookup_captures_receipt_cadence_and_lot_size_stats(self):
        receipt_rows = [
            {"line_code": "AER-", "item_code": "GH781-4", "qty_received": 2, "vendor": "MOTION", "receipt_date": "01-Mar-2026"},
            {"line_code": "AER-", "item_code": "GH781-4", "qty_received": 4, "vendor": "MOTION", "receipt_date": "05-Mar-2026"},
            {"line_code": "AER-", "item_code": "GH781-4", "qty_received": 8, "vendor": "SOURCE", "receipt_date": "11-Mar-2026"},
        ]

        history = parsers.build_receipt_history_lookup(receipt_rows)[("AER-", "GH781-4")]

        self.assertEqual(history["receipt_count"], 3)
        self.assertEqual(history["qty_received_total"], 14)
        self.assertEqual(history["first_receipt_date"], "2026-03-01")
        self.assertEqual(history["last_receipt_date"], "2026-03-11")
        self.assertAlmostEqual(history["avg_units_per_receipt"], 14 / 3)
        self.assertEqual(history["median_units_per_receipt"], 4)
        self.assertEqual(history["max_units_per_receipt"], 8)
        self.assertEqual(history["avg_days_between_receipts"], 5.0)
        self.assertEqual(history["receipt_pack_candidate"], 8)
        self.assertEqual(history["receipt_pack_candidates"], [8, 4, 2])
        self.assertEqual(history["receipt_pack_confidence"], "low")

    def test_build_receipt_history_lookup_uses_repeated_receipt_lot_as_pack_candidate(self):
        receipt_rows = [
            {"line_code": "AER-", "item_code": "GH781-4", "qty_received": 25, "vendor": "MOTION", "receipt_date": "01-Mar-2026"},
            {"line_code": "AER-", "item_code": "GH781-4", "qty_received": 25, "vendor": "MOTION", "receipt_date": "05-Mar-2026"},
            {"line_code": "AER-", "item_code": "GH781-4", "qty_received": 25, "vendor": "SOURCE", "receipt_date": "11-Mar-2026"},
            {"line_code": "AER-", "item_code": "GH781-4", "qty_received": 1, "vendor": "SOURCE", "receipt_date": "15-Mar-2026"},
        ]

        history = parsers.build_receipt_history_lookup(receipt_rows)[("AER-", "GH781-4")]

        self.assertEqual(history["receipt_pack_candidate"], 25)
        self.assertEqual(history["receipt_pack_candidates"], [25])
        self.assertEqual(history["receipt_pack_confidence"], "high")
        self.assertAlmostEqual(history["receipt_pack_candidate_share"], 0.75)

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


    def test_parse_x4_date_handles_both_formats(self):
        self.assertEqual(
            parsers.parse_x4_date("20-Mar-2026"),
            __import__("datetime").datetime(2026, 3, 20),
        )
        self.assertEqual(
            parsers.parse_x4_date("2026-03-20"),
            __import__("datetime").datetime(2026, 3, 20),
        )
        self.assertIsNone(parsers.parse_x4_date(""))
        self.assertIsNone(parsers.parse_x4_date("not-a-date"))

    def test_parse_x4_date_is_memoized(self):
        # Regression: the 8-year sales dataset was hitting strptime
        # 1.67M times at ~20us/call (~33s).  Memoizing the parse is
        # safe because the input is a short string and the output is
        # immutable — the cache just avoids redundant strptime work.
        parsers._PARSE_X4_DATE_CACHE.clear()
        first = parsers.parse_x4_date("20-Mar-2026")
        self.assertIn("20-Mar-2026", parsers._PARSE_X4_DATE_CACHE)
        # Second call returns the exact same cached object.
        second = parsers.parse_x4_date("20-Mar-2026")
        self.assertIs(first, second)
        # Unknown strings don't pollute the cache.
        self.assertIsNone(parsers.parse_x4_date("garbage"))
        self.assertNotIn("garbage", parsers._PARSE_X4_DATE_CACHE)


if __name__ == "__main__":
    unittest.main()
