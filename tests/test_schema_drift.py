import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import schema_drift


def _write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        for row in rows:
            f.write(",".join(str(c) for c in row) + "\n")


class NormalizeHeaderTests(unittest.TestCase):
    def test_lowercases_and_strips(self):
        out = schema_drift.normalize_header(["  PG ", "Item Code", "QOH "])
        self.assertEqual(out, ["pg", "item code", "qoh"])

    def test_drops_trailing_empty(self):
        out = schema_drift.normalize_header(["PG", "Item Code", "", "  "])
        self.assertEqual(out, ["pg", "item code"])

    def test_collapses_inner_whitespace(self):
        out = schema_drift.normalize_header(["Part  Number"])
        self.assertEqual(out, ["part number"])


class HashHeaderRowTests(unittest.TestCase):
    def test_identical_rows_hash_same(self):
        a = schema_drift.hash_header_row(["PG", "Item Code", "QOH"])
        b = schema_drift.hash_header_row(["pg", "ITEM CODE", "  qoh  "])
        self.assertEqual(a, b)

    def test_different_columns_hash_different(self):
        a = schema_drift.hash_header_row(["PG", "Item Code", "QOH"])
        b = schema_drift.hash_header_row(["PG", "Item Code", "QOH", "MIN"])
        self.assertNotEqual(a, b)

    def test_reordered_columns_hash_different(self):
        a = schema_drift.hash_header_row(["PG", "Item Code", "QOH"])
        b = schema_drift.hash_header_row(["Item Code", "PG", "QOH"])
        self.assertNotEqual(a, b)

    def test_trailing_empty_ignored(self):
        a = schema_drift.hash_header_row(["PG", "Item Code"])
        b = schema_drift.hash_header_row(["PG", "Item Code", "", ""])
        self.assertEqual(a, b)


class HashCsvHeaderTests(unittest.TestCase):
    def test_reads_first_nonempty_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.csv")
            _write_csv(path, [[], ["", ""], ["PG", "Item Code"], ["GR1-", "A"]])
            digest = schema_drift.hash_csv_header(path)
            self.assertEqual(digest, schema_drift.hash_header_row(["PG", "Item Code"]))

    def test_missing_file_returns_none(self):
        self.assertIsNone(schema_drift.hash_csv_header("/does/not/exist.csv"))

    def test_empty_file_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "empty.csv")
            open(path, "w").close()
            self.assertIsNone(schema_drift.hash_csv_header(path))


class ComputeSchemaHashesTests(unittest.TestCase):
    def test_skips_empty_paths(self):
        out = schema_drift.compute_schema_hashes({"sales": "", "po": None})
        self.assertEqual(out, {})

    def test_hashes_each_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            sales = os.path.join(tmp, "sales.csv")
            po = os.path.join(tmp, "po.csv")
            _write_csv(sales, [["Line Code", "Item Code", "Qty"]])
            _write_csv(po, [["PG", "IC", "Type"]])
            out = schema_drift.compute_schema_hashes({"sales": sales, "po": po, "missing": "/no/such"})
            self.assertEqual(set(out.keys()), {"sales", "po"})
            self.assertNotEqual(out["sales"], out["po"])


class DetectDriftTests(unittest.TestCase):
    def test_new_keys_are_not_drift(self):
        current = {"sales": "abc", "po": "def"}
        stored = {}
        self.assertEqual(schema_drift.detect_drift(current, stored), [])

    def test_changed_key_is_drift(self):
        current = {"sales": "abc", "po": "new"}
        stored = {"sales": "abc", "po": "old"}
        self.assertEqual(schema_drift.detect_drift(current, stored), ["po"])

    def test_missing_current_key_is_not_drift(self):
        # Key went away — not our concern here; load_flow handles missing files.
        current = {"sales": "abc"}
        stored = {"sales": "abc", "po": "old"}
        self.assertEqual(schema_drift.detect_drift(current, stored), [])

    def test_multiple_drifts_sorted(self):
        current = {"z": "1", "a": "1", "m": "1"}
        stored = {"z": "0", "a": "0", "m": "0"}
        self.assertEqual(schema_drift.detect_drift(current, stored), ["a", "m", "z"])


class FriendlyLabelTests(unittest.TestCase):
    def test_known_keys_have_labels(self):
        self.assertEqual(schema_drift.friendly_label("sales"), "Detailed Part Sales")
        self.assertEqual(schema_drift.friendly_label("po"), "PO Part Listing by Product Group")
        self.assertEqual(schema_drift.friendly_label("onhand"), "On Hand Min Max Sales")

    def test_unknown_key_echoes_through(self):
        self.assertEqual(schema_drift.friendly_label("whatever"), "whatever")


if __name__ == "__main__":
    unittest.main()
