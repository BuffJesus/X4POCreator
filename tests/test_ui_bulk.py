import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_bulk


class UIBulkTests(unittest.TestCase):
    def test_refresh_bulk_view_after_edit_refreshes_rows_when_unfiltered_unsorted(self):
        events = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(refresh_row=lambda row_id, values: events.append((row_id, values))),
            filtered_items=[
                {"line_code": "AER-", "item_code": "GH781-4", "vendor": "MOTION"},
                {"line_code": "AER-", "item_code": "GH781-5", "vendor": ""},
            ],
            _bulk_row_values=lambda item: (item["item_code"], item.get("vendor", "")),
            _apply_bulk_filter=lambda: events.append("filter"),
            _bulk_sort_col=None,
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
        )

        result = ui_bulk.refresh_bulk_view_after_edit(fake_app, ("0", "1"))

        self.assertTrue(result)
        self.assertEqual(events, [("0", ("GH781-4", "MOTION")), ("1", ("GH781-5", ""))])

    def test_refresh_bulk_view_after_edit_falls_back_to_filter_when_filtered(self):
        events = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(refresh_row=lambda row_id, values: events.append((row_id, values))),
            filtered_items=[{"line_code": "AER-", "item_code": "GH781-4"}],
            _bulk_row_values=lambda item: (item["item_code"],),
            _apply_bulk_filter=lambda: events.append("filter"),
            _bulk_sort_col=None,
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "AER-"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
        )

        result = ui_bulk.refresh_bulk_view_after_edit(fake_app, ("0",))

        self.assertFalse(result)
        self.assertEqual(events, ["filter"])


if __name__ == "__main__":
    unittest.main()
