import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import skip_actions_flow


def _item(lc, ic, *, final=0, raw=0, description="", **extras):
    payload = {
        "line_code": lc,
        "item_code": ic,
        "final_qty": final,
        "raw_need": raw,
        "description": description,
    }
    payload.update(extras)
    return payload


class IsSkipItemTests(unittest.TestCase):
    def test_zero_final_and_raw_is_skip(self):
        self.assertTrue(skip_actions_flow.is_skip_item(_item("A", "1", final=0, raw=0)))

    def test_positive_raw_is_not_skip(self):
        self.assertFalse(skip_actions_flow.is_skip_item(_item("A", "1", final=0, raw=5)))

    def test_positive_final_is_not_skip(self):
        self.assertFalse(skip_actions_flow.is_skip_item(_item("A", "1", final=3, raw=0)))

    def test_negative_values_treated_as_skip(self):
        self.assertTrue(skip_actions_flow.is_skip_item(_item("A", "1", final=-2, raw=-1)))

    def test_non_dict_returns_false(self):
        self.assertFalse(skip_actions_flow.is_skip_item("not a dict"))
        self.assertFalse(skip_actions_flow.is_skip_item(None))

    def test_non_numeric_values_coerce_to_zero_then_skip(self):
        self.assertTrue(skip_actions_flow.is_skip_item({"final_qty": "x", "raw_need": "y"}))


class FilterSkipItemsTests(unittest.TestCase):
    def test_filters_to_skip_only(self):
        items = [
            _item("A", "1", final=0, raw=0),
            _item("A", "2", final=5, raw=5),
            _item("A", "3", final=0, raw=0),
        ]
        result = skip_actions_flow.filter_skip_items(items)
        self.assertEqual([i["item_code"] for i in result], ["1", "3"])

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(skip_actions_flow.filter_skip_items([]), [])
        self.assertEqual(skip_actions_flow.filter_skip_items(None), [])


class CountSkipClustersTests(unittest.TestCase):
    def test_groups_by_line_code(self):
        items = [
            _item("AAA", "1"), _item("AAA", "2"), _item("AAA", "3"),
            _item("BBB", "1"),
            _item("CCC", "1"), _item("CCC", "2"),
        ]
        clusters = skip_actions_flow.count_skip_clusters_by_line_code(items)
        self.assertEqual(
            [(c["line_code"], c["count"]) for c in clusters],
            [("AAA", 3), ("CCC", 2), ("BBB", 1)],
        )

    def test_skips_non_skip_items(self):
        items = [
            _item("AAA", "1", final=0, raw=0),
            _item("AAA", "2", final=5, raw=5),  # not skip
            _item("BBB", "1", final=0, raw=0),
        ]
        clusters = skip_actions_flow.count_skip_clusters_by_line_code(items)
        self.assertEqual(
            [(c["line_code"], c["count"]) for c in clusters],
            [("AAA", 1), ("BBB", 1)],
        )

    def test_alphabetical_tie_break(self):
        items = [
            _item("BBB", "1"), _item("BBB", "2"),
            _item("AAA", "1"), _item("AAA", "2"),
        ]
        clusters = skip_actions_flow.count_skip_clusters_by_line_code(items)
        self.assertEqual([c["line_code"] for c in clusters], ["AAA", "BBB"])

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(skip_actions_flow.count_skip_clusters_by_line_code([]), [])


class CollectKeysTests(unittest.TestCase):
    def test_collect_keys_for_action(self):
        items = [
            _item("A", "1"),
            _item("A", "2"),
            _item("", ""),  # dropped
        ]
        self.assertEqual(
            skip_actions_flow.collect_keys_for_action(items),
            [("A", "1"), ("A", "2")],
        )

    def test_skips_items_with_blank_item_code(self):
        items = [
            _item("A", ""),
            _item("A", "OK"),
        ]
        self.assertEqual(skip_actions_flow.collect_keys_for_action(items), [("A", "OK")])

    def test_collect_ignore_keys_returns_lc_colon_ic_strings(self):
        items = [_item("A", "1"), _item("B", "2")]
        self.assertEqual(
            skip_actions_flow.collect_ignore_keys(items),
            ["A:1", "B:2"],
        )


class BuildSkipExportRowsTests(unittest.TestCase):
    def test_only_includes_skip_items(self):
        items = [
            _item("A", "1", final=0, raw=0, description="SKIP ME"),
            _item("A", "2", final=5, raw=5, description="ORDER ME"),
        ]
        rows = skip_actions_flow.build_skip_export_rows(items)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["item_code"], "1")
        self.assertEqual(rows[0]["description"], "SKIP ME")

    def test_pulls_inventory_from_lookup_when_present(self):
        item = _item("A", "1", final=0, raw=0)
        inv = {("A", "1"): {"qoh": 12, "min": 4, "max": 10, "supplier": "VEND"}}
        rows = skip_actions_flow.build_skip_export_rows([item], inv)
        self.assertEqual(rows[0]["qoh"], 12)
        self.assertEqual(rows[0]["current_min"], 4)
        self.assertEqual(rows[0]["current_max"], 10)
        self.assertEqual(rows[0]["supplier"], "VEND")

    def test_falls_back_to_inventory_field_on_item(self):
        item = _item("A", "1", final=0, raw=0)
        item["inventory"] = {"qoh": 0, "min": None, "max": None, "supplier": "X"}
        rows = skip_actions_flow.build_skip_export_rows([item])
        self.assertEqual(rows[0]["qoh"], 0)
        self.assertEqual(rows[0]["current_min"], "")
        self.assertEqual(rows[0]["supplier"], "X")

    def test_uses_item_dates_when_present(self):
        item = _item("A", "1", final=0, raw=0,
                     last_sale_date="2026-03-25",
                     last_receipt_date="2026-03-17")
        rows = skip_actions_flow.build_skip_export_rows([item])
        self.assertEqual(rows[0]["last_sale_date"], "2026-03-25")
        self.assertEqual(rows[0]["last_receipt_date"], "2026-03-17")

    def test_includes_suggested_min_max(self):
        item = _item("A", "1", final=0, raw=0,
                     suggested_min=2, suggested_max=8)
        rows = skip_actions_flow.build_skip_export_rows([item])
        self.assertEqual(rows[0]["suggested_min"], 2)
        self.assertEqual(rows[0]["suggested_max"], 8)

    def test_rows_sorted_by_line_then_item(self):
        items = [
            _item("BBB", "001"),
            _item("AAA", "Z99"),
            _item("AAA", "A01"),
        ]
        rows = skip_actions_flow.build_skip_export_rows(items)
        self.assertEqual(
            [(r["line_code"], r["item_code"]) for r in rows],
            [("AAA", "A01"), ("AAA", "Z99"), ("BBB", "001")],
        )


class RenderSkipCsvTests(unittest.TestCase):
    def test_renders_header_and_rows_in_column_order(self):
        rows = [
            {
                "line_code": "AAA", "item_code": "1", "description": "DESC",
                "qoh": 0, "current_min": "", "current_max": "",
                "supplier": "VEND", "last_sale_date": "2026-03-25",
                "last_receipt_date": "", "suggested_min": 2, "suggested_max": 8,
            },
        ]
        csv_text = skip_actions_flow.render_skip_csv(rows)
        lines = csv_text.strip().split("\n")
        self.assertEqual(lines[0],
            "line_code,item_code,description,qoh,current_min,current_max,supplier,last_sale_date,last_receipt_date,suggested_min,suggested_max")
        self.assertIn("AAA,1,DESC,0,,,VEND,2026-03-25,,2,8", lines[1])

    def test_empty_rows_only_writes_header(self):
        csv_text = skip_actions_flow.render_skip_csv([])
        self.assertEqual(csv_text.strip(), ",".join(skip_actions_flow.SKIP_EXPORT_COLUMNS))

    def test_extra_keys_are_ignored(self):
        rows = [{
            "line_code": "AAA", "item_code": "1", "description": "DESC",
            "qoh": "", "current_min": "", "current_max": "",
            "supplier": "", "last_sale_date": "", "last_receipt_date": "",
            "suggested_min": "", "suggested_max": "",
            "extra_field": "should_not_appear",
        }]
        csv_text = skip_actions_flow.render_skip_csv(rows)
        self.assertNotIn("should_not_appear", csv_text)


if __name__ == "__main__":
    unittest.main()
