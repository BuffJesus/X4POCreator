"""Guards for silent load-corruption fixes:

  * A provided-but-unusable inventory file must ABORT the load (not silently
    leave QOH=0 and over-order the whole catalogue).  load_flow.parse_all_files
  * parse_x4_date must be locale-independent for DD-Mon-YYYY dates.
"""

import contextlib
import datetime
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import load_flow
from parsers.dates import parse_x4_date


@contextlib.contextmanager
def _valid_sales_pair():
    """Patch the mandatory detailed-sales / received-parts pair so the load
    proceeds past the empty-sales early return and reaches the inventory gate."""
    with patch("load_flow.parsers.parse_detailed_part_sales_csv", return_value=[
        {"line_code": "AER-", "item_code": "GH781-4", "description": "HOSE",
         "qty_sold": 4, "sale_date": "01-Mar-2026"},
    ]), patch("load_flow.parsers.parse_received_parts_detail_csv", return_value=[
        {"line_code": "AER-", "item_code": "GH781-4", "description": "HOSE",
         "qty_received": 3, "vendor": "MOTION", "receipt_date": "02-Mar-2026"},
    ]), patch("load_flow.parsers.build_sales_receipt_summary", return_value=[{
        "line_code": "AER-", "item_code": "GH781-4", "description": "HOSE",
        "qty_received": 3, "qty_sold": 4,
    }]), patch(
        "load_flow.parsers.parse_detailed_sales_date_range",
        return_value=(datetime.datetime(2026, 3, 1), datetime.datetime(2026, 3, 10)),
    ), patch(
        "load_flow.parsers.build_receipt_history_lookup",
        return_value={("AER-", "GH781-4"): {"primary_vendor": "MOTION"}},
    ), patch(
        "load_flow.parsers.build_detailed_sales_stats_lookup",
        return_value={("AER-", "GH781-4"): {"transaction_count": 2, "qty_sold_total": 4}},
    ):
        yield


_SALES_PATHS = {"detailedsales": "detailed.csv", "receivedparts": "received.csv"}


class InventoryHardGateTests(unittest.TestCase):
    def test_provided_but_unreadable_onhand_aborts(self):
        # onhand is provided but its parse raises -> must be FATAL, not a soft
        # "continuing without it" that silently yields QOH=0 for the whole
        # catalogue and orders full target stock everywhere.
        with _valid_sales_pair(), patch(
            "load_flow.parsers.parse_on_hand_report",
            side_effect=IOError("boom"),
        ):
            with self.assertRaises(ValueError):
                load_flow.parse_all_files(
                    {**_SALES_PATHS, "onhand": "onhand.csv"},
                    old_po_warning_days=30,
                    short_sales_window_days=30,
                )

    def test_provided_onhand_that_parses_empty_aborts(self):
        # File readable but yields zero rows -> still fatal (wrong/empty export).
        with _valid_sales_pair(), patch(
            "load_flow.parsers.parse_on_hand_report",
            return_value={},
        ):
            with self.assertRaises(ValueError):
                load_flow.parse_all_files(
                    {**_SALES_PATHS, "onhand": "onhand.csv"},
                    old_po_warning_days=30,
                    short_sales_window_days=30,
                )

    def test_no_inventory_file_is_allowed(self):
        # No inventory file provided at all -> empty lookup is legitimate,
        # the load must NOT raise.
        with _valid_sales_pair():
            result = load_flow.parse_all_files(
                dict(_SALES_PATHS),
                old_po_warning_days=30,
                short_sales_window_days=30,
            )
        self.assertEqual(result["inventory_lookup"], {})


class LocaleIndependentDateTests(unittest.TestCase):
    def test_dd_mon_yyyy_parses_regardless_of_locale(self):
        import datetime

        self.assertEqual(parse_x4_date("20-Nov-2019"), datetime.datetime(2019, 11, 20))
        # Case-insensitive month token.
        self.assertEqual(parse_x4_date("01-jan-2020"), datetime.datetime(2020, 1, 1))
        self.assertEqual(parse_x4_date("DEC-31-2020".replace("DEC-31", "31-DEC")),
                         datetime.datetime(2020, 12, 31))

    def test_iso_still_parses(self):
        import datetime

        self.assertEqual(parse_x4_date("2019-11-20"), datetime.datetime(2019, 11, 20))

    def test_survives_non_english_locale(self):
        # With a non-English LC_TIME active, strptime("%b") would have failed;
        # the month-map path must still succeed. Skip if the locale is absent.
        import locale

        for loc in ("de_DE", "de_DE.UTF-8", "German_Germany", "fr_FR", "fr_FR.UTF-8"):
            try:
                locale.setlocale(locale.LC_TIME, loc)
            except locale.Error:
                continue
            try:
                import datetime
                self.assertEqual(parse_x4_date("20-Nov-2019"),
                                 datetime.datetime(2019, 11, 20))
            finally:
                locale.setlocale(locale.LC_TIME, "C")
            return
        self.skipTest("no non-English locale available on this machine")

    def test_junk_returns_none(self):
        self.assertIsNone(parse_x4_date("not-a-date"))
        self.assertIsNone(parse_x4_date(""))
        self.assertIsNone(parse_x4_date(None))


if __name__ == "__main__":
    unittest.main()
