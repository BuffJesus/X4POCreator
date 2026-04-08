import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import rules_csv_flow
from rules_csv_flow import (
    apply_import_diff,
    export_rules_csv,
    import_rules_csv,
)


class TestExportRulesCsv(unittest.TestCase):
    def test_empty_rules_produces_header_only(self):
        csv = export_rules_csv({})
        lines = [l for l in csv.splitlines() if l]
        self.assertEqual(len(lines), 1)
        self.assertIn("Line Code", lines[0])
        self.assertIn("Pack Qty", lines[0])

    def test_single_rule_round_trips(self):
        rules = {"AER-:GH781": {"order_policy": "pack_trigger", "pack_size": 12}}
        csv = export_rules_csv(rules)
        lines = csv.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("AER-", lines[1])
        self.assertIn("GH781", lines[1])
        self.assertIn("pack_trigger", lines[1])
        self.assertIn("12", lines[1])

    def test_sorted_by_line_code_then_item_code(self):
        rules = {
            "MOT-:ZZZ": {},
            "AER-:BBB": {},
            "AER-:AAA": {},
        }
        csv = export_rules_csv(rules)
        lines = [l for l in csv.strip().splitlines() if l][1:]  # skip header
        item_codes = [l.split(",")[1] for l in lines]
        self.assertEqual(item_codes, ["AAA", "BBB", "ZZZ"])

    def test_float_pack_size_rounded_to_int(self):
        rules = {"A-:X": {"pack_size": 10}}
        csv = export_rules_csv(rules)
        self.assertIn(",10,", csv)

    def test_cover_days_float_preserved(self):
        rules = {"A-:X": {"minimum_cover_days": 14.5}}
        csv = export_rules_csv(rules)
        self.assertIn("14.5", csv)

    def test_empty_rule_fields_produce_empty_cells(self):
        rules = {"A-:X": {}}
        csv = export_rules_csv(rules)
        lines = csv.strip().splitlines()
        self.assertEqual(len(lines), 2)
        data_row = lines[1]
        # Only Line Code and Item Code should be non-empty
        cells = data_row.split(",")
        self.assertEqual(cells[0], "A-")
        self.assertEqual(cells[1], "X")
        for cell in cells[2:]:
            self.assertEqual(cell.strip(), "")


class TestImportRulesCsv(unittest.TestCase):
    def _make_csv(self, rows):
        """Build a minimal CSV string from a list of row dicts."""
        import csv, io
        buf = io.StringIO()
        headers = ["Line Code", "Item Code", "Order Policy", "Pack Qty",
                   "Min Order Qty", "Cover Days", "Cover Cycles",
                   "Trigger Qty", "Trigger %", "Notes"]
        writer = csv.DictWriter(buf, fieldnames=headers, lineterminator="\r\n",
                                extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return buf.getvalue()

    def test_new_rule_appears_in_added(self):
        csv = self._make_csv([{"Line Code": "AER-", "Item Code": "GH781",
                               "Pack Qty": "10"}])
        diff = import_rules_csv(csv, {})
        self.assertIn("AER-:GH781", diff["added"])
        self.assertEqual(diff["added"]["AER-:GH781"]["pack_size"], 10)

    def test_unchanged_rule_appears_in_unchanged(self):
        rules = {"AER-:GH781": {"pack_size": 10}}
        csv = self._make_csv([{"Line Code": "AER-", "Item Code": "GH781",
                               "Pack Qty": "10"}])
        diff = import_rules_csv(csv, rules)
        self.assertIn("AER-:GH781", diff["unchanged"])
        self.assertEqual(len(diff["changed"]), 0)

    def test_changed_rule_appears_in_changed(self):
        rules = {"AER-:GH781": {"pack_size": 10}}
        csv = self._make_csv([{"Line Code": "AER-", "Item Code": "GH781",
                               "Pack Qty": "20"}])
        diff = import_rules_csv(csv, rules)
        self.assertIn("AER-:GH781", diff["changed"])
        self.assertEqual(diff["changed"]["AER-:GH781"]["pack_size"], 20)

    def test_all_blank_row_marks_existing_for_deletion(self):
        rules = {"AER-:GH781": {"pack_size": 10}}
        csv = self._make_csv([{"Line Code": "AER-", "Item Code": "GH781"}])
        diff = import_rules_csv(csv, rules)
        self.assertIn("AER-:GH781", diff["deleted"])

    def test_all_blank_row_for_nonexistent_key_is_skipped(self):
        csv = self._make_csv([{"Line Code": "AER-", "Item Code": "NOPE"}])
        diff = import_rules_csv(csv, {})
        self.assertEqual(diff["skipped"], 1)
        self.assertEqual(len(diff["deleted"]), 0)

    def test_blank_line_code_skipped(self):
        csv = self._make_csv([{"Line Code": "", "Item Code": "GH781", "Pack Qty": "10"}])
        diff = import_rules_csv(csv, {})
        self.assertEqual(diff["skipped"], 1)
        self.assertEqual(len(diff["added"]), 0)

    def test_invalid_pack_qty_skipped_with_warning(self):
        csv = self._make_csv([{"Line Code": "AER-", "Item Code": "GH781",
                               "Pack Qty": "bad"}])
        diff = import_rules_csv(csv, {})
        self.assertTrue(len(diff["errors"]) > 0)

    def test_existing_rules_absent_from_csv_untouched(self):
        rules = {"AER-:GH781": {"pack_size": 50}, "MOT-:XY999": {"pack_size": 24}}
        csv = self._make_csv([{"Line Code": "AER-", "Item Code": "GH781",
                               "Pack Qty": "50"}])
        diff = import_rules_csv(csv, rules)
        # MOT-:XY999 not in CSV → not in any diff bucket
        self.assertNotIn("MOT-:XY999", diff["added"])
        self.assertNotIn("MOT-:XY999", diff["changed"])
        self.assertNotIn("MOT-:XY999", diff["deleted"])

    def test_empty_csv_produces_no_changes(self):
        diff = import_rules_csv("", {})
        self.assertEqual(len(diff["added"]), 0)
        self.assertEqual(len(diff["errors"]), 1)

    def test_cover_days_parsed_as_float(self):
        csv = self._make_csv([{"Line Code": "A-", "Item Code": "X", "Cover Days": "14.5"}])
        diff = import_rules_csv(csv, {})
        self.assertEqual(diff["added"]["A-:X"]["minimum_cover_days"], 14.5)

    def test_notes_preserved(self):
        csv = self._make_csv([{"Line Code": "A-", "Item Code": "X", "Notes": "special item"}])
        diff = import_rules_csv(csv, {})
        self.assertEqual(diff["added"]["A-:X"]["notes"], "special item")


class TestApplyImportDiff(unittest.TestCase):
    def test_adds_new_rules(self):
        rules = {}
        diff = {"added": {"A:1": {"pack_size": 10}}, "changed": {}, "deleted": set()}
        apply_import_diff(rules, diff)
        self.assertEqual(rules["A:1"]["pack_size"], 10)

    def test_updates_changed_rules(self):
        rules = {"A:1": {"pack_size": 10}}
        diff = {"added": {}, "changed": {"A:1": {"pack_size": 20}}, "deleted": set()}
        apply_import_diff(rules, diff)
        self.assertEqual(rules["A:1"]["pack_size"], 20)

    def test_deletes_rules(self):
        rules = {"A:1": {"pack_size": 10}}
        diff = {"added": {}, "changed": {}, "deleted": {"A:1"}}
        apply_import_diff(rules, diff)
        self.assertNotIn("A:1", rules)

    def test_returns_total_affected_count(self):
        rules = {"B:2": {"pack_size": 5}}
        diff = {
            "added": {"A:1": {}},
            "changed": {"B:2": {"pack_size": 10}},
            "deleted": {"C:3"},
        }
        count = apply_import_diff(rules, diff)
        self.assertEqual(count, 3)

    def test_round_trip_fidelity(self):
        original = {
            "AER-:GH781": {"order_policy": "pack_trigger", "pack_size": 12,
                           "minimum_cover_days": 14.0},
            "MOT-:XY999": {"pack_size": 6, "min_order_qty": 3},
        }
        csv = export_rules_csv(original)
        diff = import_rules_csv(csv, {})
        result = {}
        apply_import_diff(result, diff)
        for key in original:
            self.assertIn(key, result)
            for field_key, value in original[key].items():
                self.assertEqual(result[key].get(field_key), value,
                                 f"{key}.{field_key}: expected {value!r}, got {result[key].get(field_key)!r}")
