import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import supplier_map_flow


class LoadSaveSupplierMapTests(unittest.TestCase):
    def test_load_missing_file_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(supplier_map_flow.load_supplier_map(str(Path(tmp) / "nope.json")), {})

    def test_load_malformed_json_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("not json", encoding="utf-8")
            self.assertEqual(supplier_map_flow.load_supplier_map(str(path)), {})

    def test_load_non_dict_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "list.json"
            path.write_text("[1, 2, 3]", encoding="utf-8")
            self.assertEqual(supplier_map_flow.load_supplier_map(str(path)), {})

    def test_load_normalizes_keys_and_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ok.json"
            path.write_text(json.dumps({" grelin ": "vendorco", "Acme": "ACME-V"}), encoding="utf-8")
            self.assertEqual(
                supplier_map_flow.load_supplier_map(str(path)),
                {"GRELIN": "VENDORCO", "ACME": "ACME-V"},
            )

    def test_load_drops_blank_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blank.json"
            path.write_text(json.dumps({"GRELIN": "", "": "VENDORCO", "OK": "OK"}), encoding="utf-8")
            self.assertEqual(supplier_map_flow.load_supplier_map(str(path)), {"OK": "OK"})

    def test_save_creates_file_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.json"
            supplier_map_flow.save_supplier_map(str(path), {"grelin": "vendorco", "": "skip", "ok": ""})
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data, {"GRELIN": "VENDORCO"})

    def test_save_then_load_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.json"
            mapping = {"GRELIN": "VENDORCO", "ACME": "ACME-V"}
            supplier_map_flow.save_supplier_map(str(path), mapping)
            self.assertEqual(supplier_map_flow.load_supplier_map(str(path)), mapping)


class ApplySupplierMapTests(unittest.TestCase):
    def test_empty_map_returns_empty_pairs(self):
        items = [{"vendor": "", "inventory": {"supplier": "GRELIN"}}]
        self.assertEqual(supplier_map_flow.apply_supplier_map(items, {}), [])

    def test_skips_already_assigned_items(self):
        items = [{"vendor": "EXISTING", "inventory": {"supplier": "GRELIN"}}]
        self.assertEqual(
            supplier_map_flow.apply_supplier_map(items, {"GRELIN": "VENDORCO"}),
            [],
        )

    def test_matches_unassigned_items_via_inventory_supplier(self):
        item = {"vendor": "", "inventory": {"supplier": "grelin"}, "item_code": "A"}
        pairs = supplier_map_flow.apply_supplier_map([item], {"GRELIN": "VENDORCO"})
        self.assertEqual(len(pairs), 1)
        self.assertIs(pairs[0][0], item)
        self.assertEqual(pairs[0][1], "VENDORCO")

    def test_falls_back_to_top_level_supplier_field(self):
        item = {"vendor": "", "supplier": "ACME", "item_code": "B"}
        pairs = supplier_map_flow.apply_supplier_map([item], {"ACME": "ACME-V"})
        self.assertEqual(pairs, [(item, "ACME-V")])

    def test_skips_items_with_no_supplier(self):
        items = [{"vendor": "", "item_code": "C"}]
        self.assertEqual(supplier_map_flow.apply_supplier_map(items, {"GRELIN": "X"}), [])

    def test_skips_items_whose_supplier_is_not_mapped(self):
        items = [{"vendor": "", "inventory": {"supplier": "UNKNOWN"}}]
        self.assertEqual(supplier_map_flow.apply_supplier_map(items, {"GRELIN": "X"}), [])


class BuildSupplierMapFromHistoryTests(unittest.TestCase):
    def test_empty_input_returns_empty_dict(self):
        self.assertEqual(supplier_map_flow.build_supplier_map_from_history([]), {})
        self.assertEqual(supplier_map_flow.build_supplier_map_from_history(None), {})

    def test_picks_most_frequent_vendor_per_supplier(self):
        snapshots = [
            {"exported_items": [
                {"inventory": {"supplier": "GRELIN"}, "vendor": "VENDORCO"},
                {"inventory": {"supplier": "GRELIN"}, "vendor": "VENDORCO"},
                {"inventory": {"supplier": "GRELIN"}, "vendor": "OTHER"},
                {"inventory": {"supplier": "ACME"}, "vendor": "ACME-V"},
            ]},
        ]
        self.assertEqual(
            supplier_map_flow.build_supplier_map_from_history(snapshots),
            {"GRELIN": "VENDORCO", "ACME": "ACME-V"},
        )

    def test_falls_back_to_assigned_items_when_exported_missing(self):
        snapshots = [
            {"assigned_items": [
                {"inventory": {"supplier": "GRELIN"}, "vendor": "VENDORCO"},
            ]},
        ]
        self.assertEqual(
            supplier_map_flow.build_supplier_map_from_history(snapshots),
            {"GRELIN": "VENDORCO"},
        )

    def test_ignores_items_without_supplier_or_vendor(self):
        snapshots = [
            {"exported_items": [
                {"inventory": {"supplier": "GRELIN"}, "vendor": ""},
                {"inventory": {}, "vendor": "VENDORCO"},
            ]},
        ]
        self.assertEqual(supplier_map_flow.build_supplier_map_from_history(snapshots), {})

    def test_aggregates_across_multiple_snapshots(self):
        snapshots = [
            {"exported_items": [{"inventory": {"supplier": "GRELIN"}, "vendor": "A"}]},
            {"exported_items": [{"inventory": {"supplier": "GRELIN"}, "vendor": "B"}]},
            {"exported_items": [{"inventory": {"supplier": "GRELIN"}, "vendor": "B"}]},
        ]
        self.assertEqual(
            supplier_map_flow.build_supplier_map_from_history(snapshots),
            {"GRELIN": "B"},
        )


class MergeSupplierMapsTests(unittest.TestCase):
    def test_base_wins_by_default(self):
        base = {"GRELIN": "MANUAL"}
        overlay = {"GRELIN": "INFERRED", "ACME": "ACME-V"}
        merged = supplier_map_flow.merge_supplier_maps(base, overlay)
        self.assertEqual(merged, {"GRELIN": "MANUAL", "ACME": "ACME-V"})

    def test_overlay_wins_when_flag_set(self):
        base = {"GRELIN": "MANUAL"}
        overlay = {"GRELIN": "INFERRED"}
        merged = supplier_map_flow.merge_supplier_maps(base, overlay, overlay_wins=True)
        self.assertEqual(merged, {"GRELIN": "INFERRED"})

    def test_normalizes_codes(self):
        merged = supplier_map_flow.merge_supplier_maps(
            {" grelin ": "vendorco"},
            {"acme": "acme-v"},
        )
        self.assertEqual(merged, {"GRELIN": "VENDORCO", "ACME": "ACME-V"})


if __name__ == "__main__":
    unittest.main()
