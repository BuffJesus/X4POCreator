import sys
import unittest
from datetime import datetime
from pathlib import Path
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import load_flow
from models import AppSessionState


class LoadFlowTests(unittest.TestCase):
    def test_parse_all_files_reuses_cached_result_when_signatures_match(self):
        _aggregates = {
            "detailed_sales_rows": [],
            "sales_items": [{"line_code": "AER-", "item_code": "GH781-4",
                              "description": "HOSE", "qty_received": 0, "qty_sold": 2}],
            "sales_window": (datetime(2026, 3, 1), datetime(2026, 3, 3)),
            "receipt_history_lookup": {},
            "detailed_sales_stats_lookup": {},
        }
        with tempfile.TemporaryDirectory() as tmp:
            detailed_path = Path(tmp) / "detailed.csv"
            recv_path = Path(tmp) / "received.csv"
            cache_path = Path(tmp) / "parse_cache.pkl"
            detailed_path.write_text("placeholder\n", encoding="utf-8-sig")
            recv_path.write_text("placeholder\n", encoding="utf-8-sig")
            with patch.object(load_flow, "PARSE_CACHE_FILE", str(cache_path)):
                with patch("load_flow.parsers.parse_detailed_pair_aggregates",
                           return_value=_aggregates):
                    first = load_flow.parse_all_files(
                        {
                            "detailedsales": str(detailed_path),
                            "receivedparts": str(recv_path),
                            "po": "",
                            "susp": "",
                            "onhand": "",
                            "minmax": "",
                            "packsize": "",
                        },
                        old_po_warning_days=90,
                        short_sales_window_days=7,
                    )

                with patch("load_flow.parsers.parse_detailed_pair_aggregates",
                           side_effect=AssertionError("parser should not run")):
                    second = load_flow.parse_all_files(
                        {
                            "detailedsales": str(detailed_path),
                            "receivedparts": str(recv_path),
                            "po": "",
                            "susp": "",
                            "onhand": "",
                            "minmax": "",
                            "packsize": "",
                        },
                        old_po_warning_days=90,
                        short_sales_window_days=7,
                    )

        self.assertEqual(first["sales_items"], second["sales_items"])
        self.assertEqual(first["sales_window_start"], second["sales_window_start"])

    def test_parse_all_files_invalidates_cache_when_file_signature_changes(self):
        _aggregates_v1 = {
            "detailed_sales_rows": [],
            "sales_items": [{"line_code": "AER-", "item_code": "GH781-4",
                              "description": "HOSE", "qty_received": 0, "qty_sold": 2}],
            "sales_window": (datetime(2026, 3, 1), datetime(2026, 3, 3)),
            "receipt_history_lookup": {},
            "detailed_sales_stats_lookup": {},
        }
        _aggregates_v2 = {
            "detailed_sales_rows": [],
            "sales_items": [{"line_code": "AER-", "item_code": "GH781-4",
                              "description": "HOSE", "qty_received": 0, "qty_sold": 5}],
            "sales_window": (datetime(2026, 3, 1), datetime(2026, 3, 5)),
            "receipt_history_lookup": {},
            "detailed_sales_stats_lookup": {},
        }
        with tempfile.TemporaryDirectory() as tmp:
            detailed_path = Path(tmp) / "detailed.csv"
            recv_path = Path(tmp) / "received.csv"
            cache_path = Path(tmp) / "parse_cache.pkl"
            detailed_path.write_text("placeholder\n", encoding="utf-8-sig")
            recv_path.write_text("placeholder\n", encoding="utf-8-sig")
            with patch.object(load_flow, "PARSE_CACHE_FILE", str(cache_path)):
                with patch("load_flow.parsers.parse_detailed_pair_aggregates",
                           return_value=_aggregates_v1):
                    load_flow.parse_all_files(
                        {
                            "detailedsales": str(detailed_path),
                            "receivedparts": str(recv_path),
                            "po": "",
                            "susp": "",
                            "onhand": "",
                            "minmax": "",
                            "packsize": "",
                        },
                        old_po_warning_days=90,
                        short_sales_window_days=7,
                    )

                detailed_path.write_text("placeholder\nchanged\n", encoding="utf-8-sig")
                with patch("load_flow.parsers.parse_detailed_pair_aggregates",
                           return_value=_aggregates_v2) as mocked_parse:
                    result = load_flow.parse_all_files(
                        {
                            "detailedsales": str(detailed_path),
                            "receivedparts": str(recv_path),
                            "po": "",
                            "susp": "",
                            "onhand": "",
                            "minmax": "",
                            "packsize": "",
                        },
                        old_po_warning_days=90,
                        short_sales_window_days=7,
                    )

        self.assertEqual(mocked_parse.call_count, 1)
        self.assertEqual(result["sales_items"][0]["qty_sold"], 5)

    def test_parse_all_files_sales_window_warning_uses_actionable_language(self):
        _items = [{"line_code": "AER-", "item_code": "GH781-4",
                   "description": "HOSE", "qty_received": 0, "qty_sold": 2}]
        with patch("load_flow.parsers.parse_detailed_part_sales_csv", return_value=[]), \
             patch("load_flow.parsers.parse_received_parts_detail_csv", return_value=[]), \
             patch("load_flow.parsers.build_sales_receipt_summary", return_value=_items), \
             patch("load_flow.parsers.parse_detailed_sales_date_range",
                   return_value=(datetime(2026, 3, 1), datetime(2026, 3, 3))), \
             patch("load_flow.parsers.build_receipt_history_lookup", return_value={}), \
             patch("load_flow.parsers.build_detailed_sales_stats_lookup", return_value={}):
            result = load_flow.parse_all_files(
                {
                    "detailedsales": "detailed.csv",
                    "receivedparts": "received.csv",
                    "po": "",
                    "susp": "",
                    "onhand": "",
                    "minmax": "",
                    "packsize": "",
                },
                old_po_warning_days=90,
                short_sales_window_days=7,
            )

        title, message = result["warnings"][0]
        self.assertEqual(title, "Sales Window Warning")
        self.assertIn("You can continue", message)
        self.assertIn("wider sales date range is recommended", message)

    def test_parse_all_files_warns_when_inventory_has_negative_qoh(self):
        _items = [{"line_code": "AMS-", "item_code": "XLF-1G",
                   "description": "5W-30 XL OIL", "qty_received": 0, "qty_sold": 2}]
        with patch("load_flow.parsers.parse_detailed_part_sales_csv", return_value=[]), \
             patch("load_flow.parsers.parse_received_parts_detail_csv", return_value=[]), \
             patch("load_flow.parsers.build_sales_receipt_summary", return_value=_items), \
             patch("load_flow.parsers.parse_detailed_sales_date_range",
                   return_value=(None, None)), \
             patch("load_flow.parsers.build_receipt_history_lookup", return_value={}), \
             patch("load_flow.parsers.build_detailed_sales_stats_lookup", return_value={}), \
             patch("load_flow.parsers.parse_on_hand_report",
                   return_value={("AMS-", "XLF-1G"): {"qoh": -12.0, "repl_cost": 45.75}}):
            result = load_flow.parse_all_files(
                {
                    "detailedsales": "detailed.csv",
                    "receivedparts": "received.csv",
                    "po": "",
                    "susp": "",
                    "onhand": "onhand.csv",
                    "minmax": "",
                    "packsize": "",
                },
                old_po_warning_days=90,
                short_sales_window_days=7,
            )

        warning_titles = [title for title, _message in result["warnings"]]
        self.assertIn("Negative QOH Warning", warning_titles)
        self.assertEqual(result["startup_warning_rows"][0]["warning_type"], "Negative QOH Warning")
        self.assertEqual(result["startup_warning_rows"][0]["qty"], "-12")

    def test_apply_load_result_populates_session_fields(self):
        session = AppSessionState()
        result = {
            "sales_span_days": 31,
            "sales_window_start": "2026-02-01",
            "sales_window_end": "2026-03-03",
            "sales_items": [{"line_code": "AER-", "item_code": "GH781-4"}],
            "all_line_codes": ["AER-"],
            "po_items": [{"line_code": "AER-", "item_code": "GH781-4", "qty": 2}],
            "open_po_lookup": {("AER-", "GH781-4"): [{"qty": 2}]},
            "inventory_lookup": {("AER-", "GH781-4"): {"qoh": 5}},
            "receipt_history_lookup": {("AER-", "GH781-4"): {"primary_vendor": "MOTION"}},
            "detailed_sales_stats_lookup": {("AER-", "GH781-4"): {"transaction_count": 3}},
            "pack_size_lookup": {("AER-", "GH781-4"): 6},
            "startup_warning_rows": [{"warning_type": "Example"}],
        }

        load_flow.apply_load_result(session, result, parsers_module=type("P", (), {
            "build_pack_size_fallbacks": staticmethod(lambda lookup: ({"GH781-4": 6}, {"DUP-1"})),
        }))

        self.assertEqual(session.sales_items, result["sales_items"])
        self.assertEqual(session.sales_span_days, 31)
        self.assertEqual(session.sales_window_start, "2026-02-01")
        self.assertEqual(session.sales_window_end, "2026-03-03")
        self.assertEqual(session.inventory_source_lookup, result["inventory_lookup"])
        self.assertEqual(session.receipt_history_lookup, result["receipt_history_lookup"])
        self.assertEqual(session.detailed_sales_stats_lookup, result["detailed_sales_stats_lookup"])
        self.assertEqual(session.inventory_coverage_missing_keys, set())
        self.assertEqual(session.detailed_sales_conflict_keys, set())
        self.assertEqual(session.unresolved_detailed_item_codes, set())
        self.assertEqual(session.pack_size_by_item, {"GH781-4": 6})
        self.assertEqual(session.pack_size_conflicts, {"DUP-1"})

    def test_parse_all_files_accepts_detailed_sales_and_received_parts_pair(self):
        with patch("load_flow.parsers.parse_detailed_part_sales_csv", return_value=[
            {
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_sold": 4,
                "sale_date": "01-Mar-2026",
            },
        ]), patch("load_flow.parsers.parse_received_parts_detail_csv", return_value=[
            {
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_received": 3,
                "vendor": "MOTION",
                "receipt_date": "02-Mar-2026",
            },
        ]), patch("load_flow.parsers.build_sales_receipt_summary", return_value=[{
            "line_code": "AER-",
            "item_code": "GH781-4",
            "description": "HOSE",
            "qty_received": 3,
            "qty_sold": 4,
        }]), patch(
            "load_flow.parsers.parse_detailed_sales_date_range",
            return_value=(datetime(2026, 3, 1), datetime(2026, 3, 10)),
        ), patch(
            "load_flow.parsers.build_receipt_history_lookup",
            return_value={("AER-", "GH781-4"): {"primary_vendor": "MOTION"}},
        ), patch(
            "load_flow.parsers.build_detailed_sales_stats_lookup",
            return_value={("AER-", "GH781-4"): {"transaction_count": 2, "qty_sold_total": 4}},
        ):
            result = load_flow.parse_all_files(
                {
                    "sales": "",
                    "detailedsales": "detailed.csv",
                    "receivedparts": "received.csv",
                    "po": "",
                    "susp": "",
                    "onhand": "",
                    "minmax": "",
                    "packsize": "",
                },
                old_po_warning_days=90,
                short_sales_window_days=7,
            )

        self.assertEqual(result["sales_items"][0]["qty_sold"], 4)
        self.assertEqual(result["sales_items"][0]["qty_received"], 3)
        self.assertEqual(result["sales_span_days"], 10)
        self.assertEqual(result["sales_window_start"], "2026-03-01")
        self.assertEqual(result["sales_window_end"], "2026-03-10")
        self.assertEqual(result["receipt_history_lookup"][("AER-", "GH781-4")]["primary_vendor"], "MOTION")
        self.assertEqual(result["detailed_sales_stats_lookup"][("AER-", "GH781-4")]["transaction_count"], 2)
        self.assertAlmostEqual(result["detailed_sales_stats_lookup"][("AER-", "GH781-4")]["annualized_qty_sold"], 146.1, places=3)
        self.assertEqual(result["sales_items"][0]["transaction_count"], 2)

    def test_parse_all_files_resolves_blank_detailed_sales_line_code_from_inventory(self):
        with patch("load_flow.parsers.parse_detailed_part_sales_csv", return_value=[
            {
                "line_code": "",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_sold": 4,
                "sale_date": "01-Mar-2026",
            },
        ]), patch("load_flow.parsers.parse_received_parts_detail_csv", return_value=[]), patch(
            "load_flow.parsers.build_sales_receipt_summary",
            return_value=[{
                "line_code": "",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_received": 0,
                "qty_sold": 4,
            }],
        ), patch(
            "load_flow.parsers.parse_detailed_sales_date_range",
            return_value=(datetime(2026, 3, 1), datetime(2026, 3, 10)),
        ), patch(
            "load_flow.parsers.build_receipt_history_lookup",
            return_value={},
        ), patch(
            "load_flow.parsers.build_detailed_sales_stats_lookup",
            return_value={("", "GH781-4"): {"transaction_count": 2, "qty_sold_total": 4}},
        ), patch(
            "load_flow.parsers.parse_on_hand_report",
            return_value={("AER-", "GH781-4"): {"qoh": 5.0, "repl_cost": 12.5}},
        ):
            result = load_flow.parse_all_files(
                {
                    "sales": "",
                    "detailedsales": "detailed.csv",
                    "receivedparts": "received.csv",
                    "po": "",
                    "susp": "",
                    "onhand": "onhand.csv",
                    "minmax": "",
                    "packsize": "",
                },
                old_po_warning_days=90,
                short_sales_window_days=7,
            )

        self.assertEqual(result["sales_items"][0]["line_code"], "AER-")
        self.assertIn(("AER-", "GH781-4"), result["detailed_sales_stats_lookup"])
        self.assertEqual(result["sales_items"][0]["transaction_count"], 2)
        self.assertEqual(result["detailed_sales_resolution"]["row_count"], 0)

    def test_parse_all_files_warns_when_detailed_sales_rows_remain_unresolved(self):
        with patch("load_flow.parsers.parse_detailed_part_sales_csv", return_value=[
            {
                "line_code": "",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_sold": 4,
                "sale_date": "01-Mar-2026",
            },
            {
                "line_code": "",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_sold": 2,
                "sale_date": "02-Mar-2026",
            },
        ]), patch("load_flow.parsers.parse_received_parts_detail_csv", return_value=[]), patch(
            "load_flow.parsers.build_sales_receipt_summary",
            return_value=[{
                "line_code": "",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_received": 0,
                "qty_sold": 6,
            }],
        ), patch(
            "load_flow.parsers.parse_detailed_sales_date_range",
            return_value=(datetime(2026, 3, 1), datetime(2026, 3, 10)),
        ), patch(
            "load_flow.parsers.build_receipt_history_lookup",
            return_value={},
        ), patch(
            "load_flow.parsers.build_detailed_sales_stats_lookup",
            return_value={("", "GH781-4"): {"transaction_count": 2, "qty_sold_total": 6}},
        ):
            result = load_flow.parse_all_files(
                {
                    "sales": "",
                    "detailedsales": "detailed.csv",
                    "receivedparts": "received.csv",
                    "po": "",
                    "susp": "",
                    "onhand": "",
                    "minmax": "",
                    "packsize": "",
                },
                old_po_warning_days=90,
                short_sales_window_days=7,
            )

        self.assertEqual(result["detailed_sales_resolution"]["row_count"], 2)
        self.assertEqual(result["detailed_sales_resolution"]["item_count"], 1)
        self.assertEqual(result["detailed_sales_resolution"]["items"][0]["item_code"], "GH781-4")
        warning_titles = [title for title, _message in result["warnings"]]
        self.assertIn("Detailed Sales Resolution Warning", warning_titles)
        startup_rows = [
            row for row in result["startup_warning_rows"]
            if row["warning_type"] == "Detailed Sales Resolution Warning"
        ]
        self.assertEqual(len(startup_rows), 1)
        self.assertEqual(startup_rows[0]["qty"], "2")
        self.assertEqual(result["unresolved_detailed_item_codes"], {"GH781-4"})

    def test_parse_all_files_warns_when_parsed_detailed_sales_line_code_conflicts_with_known_data(self):
        with patch("load_flow.parsers.parse_detailed_part_sales_csv", return_value=[
            {
                "line_code": "WRONG-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_sold": 4,
                "sale_date": "01-Mar-2026",
            },
        ]), patch("load_flow.parsers.parse_received_parts_detail_csv", return_value=[]), patch(
            "load_flow.parsers.build_sales_receipt_summary",
            return_value=[{
                "line_code": "WRONG-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_received": 0,
                "qty_sold": 4,
            }],
        ), patch(
            "load_flow.parsers.parse_detailed_sales_date_range",
            return_value=(datetime(2026, 3, 1), datetime(2026, 3, 10)),
        ), patch(
            "load_flow.parsers.build_receipt_history_lookup",
            return_value={},
        ), patch(
            "load_flow.parsers.build_detailed_sales_stats_lookup",
            return_value={("WRONG-", "GH781-4"): {"transaction_count": 1, "qty_sold_total": 4}},
        ), patch(
            "load_flow.parsers.parse_on_hand_report",
            return_value={
                ("AER-", "GH781-4"): {"qoh": 5.0, "repl_cost": 12.5},
                ("ALT-", "GH781-4"): {"qoh": 1.0, "repl_cost": 9.0},
            },
        ):
            result = load_flow.parse_all_files(
                {
                    "sales": "",
                    "detailedsales": "detailed.csv",
                    "receivedparts": "received.csv",
                    "po": "",
                    "susp": "",
                    "onhand": "onhand.csv",
                    "minmax": "",
                    "packsize": "",
                },
                old_po_warning_days=90,
                short_sales_window_days=7,
            )

        self.assertEqual(result["detailed_sales_conflicts"]["row_count"], 1)
        self.assertEqual(result["detailed_sales_conflicts"]["item_count"], 1)
        self.assertEqual(result["detailed_sales_conflicts"]["items"][0]["line_code"], "WRONG-")
        self.assertEqual(result["detailed_sales_conflicts"]["items"][0]["known_line_codes"], ["AER-", "ALT-"])
        warning_titles = [title for title, _message in result["warnings"]]
        self.assertIn("Detailed Sales Line-Code Conflict Warning", warning_titles)
        self.assertNotIn("Detailed Sales Line-Code Correction", warning_titles)
        startup_rows = [
            row for row in result["startup_warning_rows"]
            if row["warning_type"] == "Detailed Sales Line-Code Conflict Warning"
        ]
        self.assertEqual(len(startup_rows), 1)
        self.assertEqual(startup_rows[0]["qty"], "1")
        self.assertEqual(result["detailed_sales_corrections"]["row_count"], 0)
        self.assertEqual(result["detailed_sales_conflict_keys"], {("WRONG-", "GH781-4")})

    def test_parse_all_files_auto_corrects_conflicting_detailed_sales_line_code_when_known_candidate_is_unique(self):
        with patch("load_flow.parsers.parse_detailed_part_sales_csv", return_value=[
            {
                "line_code": "WRONG-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_sold": 4,
                "sale_date": "01-Mar-2026",
            },
        ]), patch("load_flow.parsers.parse_received_parts_detail_csv", return_value=[]), patch(
            "load_flow.parsers.build_sales_receipt_summary",
            return_value=[{
                "line_code": "WRONG-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_received": 0,
                "qty_sold": 4,
            }],
        ), patch(
            "load_flow.parsers.parse_detailed_sales_date_range",
            return_value=(datetime(2026, 3, 1), datetime(2026, 3, 10)),
        ), patch(
            "load_flow.parsers.build_receipt_history_lookup",
            return_value={},
        ), patch(
            "load_flow.parsers.build_detailed_sales_stats_lookup",
            return_value={("WRONG-", "GH781-4"): {"transaction_count": 1, "qty_sold_total": 4}},
        ), patch(
            "load_flow.parsers.parse_on_hand_report",
            return_value={("AER-", "GH781-4"): {"qoh": 5.0, "repl_cost": 12.5}},
        ):
            result = load_flow.parse_all_files(
                {
                    "sales": "",
                    "detailedsales": "detailed.csv",
                    "receivedparts": "received.csv",
                    "po": "",
                    "susp": "",
                    "onhand": "onhand.csv",
                    "minmax": "",
                    "packsize": "",
                },
                old_po_warning_days=90,
                short_sales_window_days=7,
            )

        self.assertEqual(result["sales_items"][0]["line_code"], "AER-")
        self.assertIn(("AER-", "GH781-4"), result["detailed_sales_stats_lookup"])
        self.assertNotIn(("WRONG-", "GH781-4"), result["detailed_sales_stats_lookup"])
        self.assertEqual(result["detailed_sales_corrections"]["row_count"], 1)
        self.assertEqual(result["detailed_sales_corrections"]["item_count"], 1)
        self.assertEqual(result["detailed_sales_corrections"]["item_codes"], ["GH781-4"])
        self.assertEqual(result["detailed_sales_conflicts"]["row_count"], 0)
        warning_titles = [title for title, _message in result["warnings"]]
        self.assertIn("Detailed Sales Line-Code Correction", warning_titles)
        self.assertNotIn("Detailed Sales Line-Code Conflict Warning", warning_titles)

    def test_parse_all_files_treats_ambiguous_short_prefix_detailed_sales_token_as_unresolved(self):
        with patch("load_flow.parsers.parse_detailed_part_sales_csv", return_value=[
            {
                "line_code": "",
                "item_code": "K-D-1708",
                "description": "COUPLER",
                "qty_sold": 4,
                "sale_date": "01-Mar-2026",
            },
        ]), patch("load_flow.parsers.parse_received_parts_detail_csv", return_value=[]), patch(
            "load_flow.parsers.build_sales_receipt_summary",
            return_value=[{
                "line_code": "",
                "item_code": "K-D-1708",
                "description": "COUPLER",
                "qty_received": 0,
                "qty_sold": 4,
            }],
        ), patch(
            "load_flow.parsers.parse_detailed_sales_date_range",
            return_value=(datetime(2026, 3, 1), datetime(2026, 3, 10)),
        ), patch(
            "load_flow.parsers.build_receipt_history_lookup",
            return_value={},
        ), patch(
            "load_flow.parsers.build_detailed_sales_stats_lookup",
            return_value={("", "K-D-1708"): {"transaction_count": 1, "qty_sold_total": 4}},
        ), patch(
            "load_flow.parsers.parse_on_hand_report",
            return_value={},
        ):
            result = load_flow.parse_all_files(
                {
                    "sales": "",
                    "detailedsales": "detailed.csv",
                    "receivedparts": "received.csv",
                    "po": "",
                    "susp": "",
                    "onhand": "onhand.csv",
                    "minmax": "",
                    "packsize": "",
                },
                old_po_warning_days=90,
                short_sales_window_days=7,
            )

        self.assertEqual(result["sales_items"][0]["line_code"], "")
        self.assertEqual(result["detailed_sales_resolution"]["row_count"], 1)
        self.assertEqual(result["detailed_sales_resolution"]["items"][0]["item_code"], "K-D-1708")
        self.assertEqual(result["detailed_sales_conflicts"]["row_count"], 0)
        self.assertEqual(result["detailed_sales_corrections"]["row_count"], 0)
        warning_titles = [title for title, _message in result["warnings"]]
        self.assertIn("Detailed Sales Resolution Warning", warning_titles)
        self.assertNotIn("Detailed Sales Line-Code Conflict Warning", warning_titles)

    def test_parse_all_files_old_po_warning_includes_po_reference(self):
        _items = [{"line_code": "AER-", "item_code": "GH781-4",
                   "description": "HOSE", "qty_received": 0, "qty_sold": 2}]
        with patch("load_flow.parsers.parse_detailed_part_sales_csv", return_value=[]), \
             patch("load_flow.parsers.parse_received_parts_detail_csv", return_value=[]), \
             patch("load_flow.parsers.build_sales_receipt_summary", return_value=_items), \
             patch("load_flow.parsers.parse_detailed_sales_date_range",
                   return_value=(None, None)), \
             patch("load_flow.parsers.build_receipt_history_lookup", return_value={}), \
             patch("load_flow.parsers.build_detailed_sales_stats_lookup", return_value={}), \
             patch("load_flow.parsers.parse_po_listing_csv", return_value=[{
                 "po_number": "PO12345",
                 "line_code": "AER-",
                 "item_code": "GH781-4",
                 "po_type": "S",
                 "qty": 6,
                 "date_issued": "01-Jan-2025",
             }]):
            result = load_flow.parse_all_files(
                {
                    "detailedsales": "detailed.csv",
                    "receivedparts": "received.csv",
                    "po": "po.csv",
                    "susp": "",
                    "onhand": "",
                    "minmax": "",
                    "packsize": "",
                },
                old_po_warning_days=90,
                short_sales_window_days=7,
                now=datetime(2026, 3, 10),
            )

        rows = [row for row in result["startup_warning_rows"] if row["warning_type"] == "Old Open PO Warning"]
        self.assertEqual(len(rows), 1)
        self.assertIn("PO12345/S 01-Jan-2025 qty 6", rows[0]["po_reference"])

    def test_parse_all_files_preserves_onhand_qoh_when_minmax_qoh_is_blank(self):
        _items = [{"line_code": "AER-", "item_code": "GH781-4",
                   "description": "HOSE", "qty_received": 0, "qty_sold": 2}]
        with patch("load_flow.parsers.parse_detailed_part_sales_csv", return_value=[]), \
             patch("load_flow.parsers.parse_received_parts_detail_csv", return_value=[]), \
             patch("load_flow.parsers.build_sales_receipt_summary", return_value=_items), \
             patch("load_flow.parsers.parse_detailed_sales_date_range",
                   return_value=(None, None)), \
             patch("load_flow.parsers.build_receipt_history_lookup", return_value={}), \
             patch("load_flow.parsers.build_detailed_sales_stats_lookup", return_value={}), \
             patch("load_flow.parsers.parse_on_hand_report",
                   return_value={("AER-", "GH781-4"): {"qoh": 9.0, "repl_cost": 12.5}}), \
             patch("load_flow.parsers.parse_on_hand_min_max", return_value={("AER-", "GH781-4"): {
                 "qoh": None, "repl_cost": None, "min": 2, "max": 6,
                 "ytd_sales": 11, "mo12_sales": 22, "supplier": "MOTION",
                 "last_receipt": "01-Mar-2026", "last_sale": "05-Mar-2026",
             }}):
            result = load_flow.parse_all_files(
                {
                    "detailedsales": "detailed.csv",
                    "receivedparts": "received.csv",
                    "po": "",
                    "susp": "",
                    "onhand": "onhand.csv",
                    "minmax": "minmax.csv",
                    "packsize": "",
                },
                old_po_warning_days=90,
                short_sales_window_days=7,
            )

        inventory = result["inventory_lookup"][("AER-", "GH781-4")]
        self.assertEqual(inventory["qoh"], 9.0)
        self.assertEqual(inventory["repl_cost"], 12.5)
        self.assertEqual(inventory["min"], 2)
        self.assertEqual(inventory["max"], 6)

    def test_parse_all_files_annotates_sales_items_with_loaded_window_metrics(self):
        _items = [{"line_code": "AER-", "item_code": "GH781-4",
                   "description": "HOSE", "qty_received": 12, "qty_sold": 52}]
        with patch("load_flow.parsers.parse_detailed_part_sales_csv", return_value=[]), \
             patch("load_flow.parsers.parse_received_parts_detail_csv", return_value=[]), \
             patch("load_flow.parsers.build_sales_receipt_summary", return_value=_items), \
             patch("load_flow.parsers.parse_detailed_sales_date_range",
                   return_value=(datetime(2025, 3, 1), datetime(2026, 2, 28))), \
             patch("load_flow.parsers.build_receipt_history_lookup", return_value={}), \
             patch("load_flow.parsers.build_detailed_sales_stats_lookup", return_value={}), \
             patch("load_flow.parsers.parse_on_hand_min_max", return_value={("AER-", "GH781-4"): {
                 "qoh": 9.0, "repl_cost": 12.5, "min": 2, "max": 6,
                 "ytd_sales": 11, "mo12_sales": 22, "supplier": "MOTION",
                 "last_receipt": "01-Mar-2026", "last_sale": "05-Mar-2026",
             }}):
            result = load_flow.parse_all_files(
                {
                    "detailedsales": "detailed.csv",
                    "receivedparts": "received.csv",
                    "po": "",
                    "susp": "",
                    "onhand": "",
                    "minmax": "minmax.csv",
                    "packsize": "",
                },
                old_po_warning_days=90,
                short_sales_window_days=7,
                now=datetime(2026, 3, 12),
            )

        item = result["sales_items"][0]
        self.assertEqual(result["sales_window_start"], "2025-03-01")
        self.assertEqual(result["sales_window_end"], "2026-02-28")
        self.assertEqual(item["sales_span_days"], 365)
        self.assertAlmostEqual(item["avg_weekly_sales_loaded"], 0.9973, places=3)
        self.assertAlmostEqual(item["annualized_sales_loaded"], 52.0356, places=3)
        self.assertEqual(item["last_sale_date"], "2026-03-05")
        self.assertEqual(item["days_since_last_sale"], 7)
        self.assertEqual(item["performance_profile"], "steady")
        self.assertEqual(item["sales_health_signal"], "active")
        self.assertFalse(item["possible_missed_reorder"])

    def test_parse_all_files_normalizes_invalid_min_max_pairs_and_warns(self):
        _items = [{"line_code": "AER-", "item_code": "GH781-4",
                   "description": "HOSE", "qty_received": 0, "qty_sold": 2}]
        with patch("load_flow.parsers.parse_detailed_part_sales_csv", return_value=[]), \
             patch("load_flow.parsers.parse_received_parts_detail_csv", return_value=[]), \
             patch("load_flow.parsers.build_sales_receipt_summary", return_value=_items), \
             patch("load_flow.parsers.parse_detailed_sales_date_range",
                   return_value=(None, None)), \
             patch("load_flow.parsers.build_receipt_history_lookup", return_value={}), \
             patch("load_flow.parsers.build_detailed_sales_stats_lookup", return_value={}), \
             patch("load_flow.parsers.parse_on_hand_min_max", return_value={
                 ("AER-", "GH781-4"): {
                     "qoh": 9.0, "repl_cost": 12.5, "min": -2, "max": -5,
                     "ytd_sales": 11, "mo12_sales": 22, "supplier": "MOTION",
                     "last_receipt": "01-Mar-2026", "last_sale": "05-Mar-2026",
                 },
                 ("AMS-", "XLF-1G"): {
                     "qoh": 4.0, "repl_cost": 8.0, "min": 6, "max": 3,
                     "ytd_sales": 5, "mo12_sales": 10, "supplier": "AMSOIL",
                     "last_receipt": "01-Mar-2026", "last_sale": "05-Mar-2026",
                 },
             }):
            result = load_flow.parse_all_files(
                {
                    "detailedsales": "detailed.csv",
                    "receivedparts": "received.csv",
                    "po": "",
                    "susp": "",
                    "onhand": "",
                    "minmax": "minmax.csv",
                    "packsize": "",
                },
                old_po_warning_days=90,
                short_sales_window_days=7,
            )

        inventory_a = result["inventory_lookup"][("AER-", "GH781-4")]
        inventory_b = result["inventory_lookup"][("AMS-", "XLF-1G")]
        self.assertEqual(inventory_a["min"], 0)
        self.assertEqual(inventory_a["max"], 0)
        self.assertEqual(inventory_b["min"], 6)
        self.assertEqual(inventory_b["max"], 6)
        warning_titles = [title for title, _message in result["warnings"]]
        self.assertIn("Min/Max Sanity Warning", warning_titles)
        startup_rows = [
            row for row in result["startup_warning_rows"]
            if row["warning_type"] == "Min/Max Sanity Warning"
        ]
        self.assertEqual(len(startup_rows), 2)
        self.assertIn("min_clamped_to_zero", startup_rows[0]["details"] + startup_rows[1]["details"])
        self.assertIn("max_raised_to_min", startup_rows[0]["details"] + startup_rows[1]["details"])

    # --- Phase 5: data quality summary ---

    def _make_session_with_quality_data(self, *, total=10, covered=10, unresolved=0, conflicts=0, missing_sale=0, missing_receipt=0):
        session = AppSessionState()
        session.sales_items = [{}] * total
        session.inventory_lookup = {
            (f"AER-", f"ITEM{i}"): {
                "last_sale": None if i < missing_sale else "01-Mar-2026",
                "last_receipt": None if i < missing_receipt else "15-Feb-2026",
            }
            for i in range(covered)
        }
        session.unresolved_detailed_item_codes = {f"UNRES{i}" for i in range(unresolved)}
        session.detailed_sales_conflict_keys = {(f"AER-", f"CONF{i}") for i in range(conflicts)}
        return session

    def test_data_quality_summary_clean_session(self):
        session = self._make_session_with_quality_data(total=10, covered=10, unresolved=0)
        summary = load_flow.compute_data_quality_summary(session)
        self.assertEqual(summary["total_items"], 10)
        self.assertEqual(summary["inventory_covered"], 10)
        self.assertEqual(summary["unresolved_item_codes"], 0)
        self.assertAlmostEqual(summary["quality_score"], 1.0)
        self.assertFalse(summary["gate_required"])

    def test_data_quality_summary_gate_required_when_unresolved_exceeds_threshold(self):
        # >10% unresolved triggers gate
        session = self._make_session_with_quality_data(total=10, covered=10, unresolved=2)
        summary = load_flow.compute_data_quality_summary(session)
        self.assertTrue(summary["gate_required"])
        self.assertLess(summary["quality_score"], 1.0)

    def test_data_quality_summary_gate_not_required_when_unresolved_at_threshold(self):
        # exactly 10% — should NOT gate (must be strictly >)
        session = self._make_session_with_quality_data(total=10, covered=10, unresolved=1)
        summary = load_flow.compute_data_quality_summary(session)
        self.assertFalse(summary["gate_required"])

    def test_data_quality_summary_counts_missing_recency(self):
        session = self._make_session_with_quality_data(total=10, covered=5, missing_sale=3, missing_receipt=2)
        summary = load_flow.compute_data_quality_summary(session)
        self.assertEqual(summary["missing_last_sale"], 3)
        self.assertEqual(summary["missing_last_receipt"], 2)

    def test_data_quality_summary_handles_empty_session(self):
        session = AppSessionState()
        summary = load_flow.compute_data_quality_summary(session)
        self.assertEqual(summary["total_items"], 0)
        self.assertAlmostEqual(summary["quality_score"], 1.0)
        self.assertFalse(summary["gate_required"])


if __name__ == "__main__":
    unittest.main()
