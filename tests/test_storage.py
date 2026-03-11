import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import storage
from models import MaintenanceIssue, SessionSnapshot


class StorageTests(unittest.TestCase):
    def test_order_rules_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "order_rules.json"
            payload = {"AER-:GH781-4": {"pack_size": 500, "order_policy": "reel_review"}}
            storage.save_order_rules(str(path), payload)
            self.assertEqual(storage.load_order_rules(str(path)), payload)

    def test_append_and_get_recent_orders(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "order_history.json"
            assigned = [{"line_code": "AER-", "item_code": "GH781-4", "order_qty": 250, "vendor": "GREGDIST"}]
            now = datetime(2026, 3, 10, 12, 0, 0)
            storage.append_order_history(str(path), assigned, now=now)
            recent = storage.get_recent_orders(str(path), lookback_days=14, now=now)
            self.assertIn(("AER-", "GH781-4"), recent)
            self.assertEqual(recent[("AER-", "GH781-4")][0]["qty"], 250)
            self.assertEqual(recent[("AER-", "GH781-4")][0]["vendor"], "GREGDIST")

    def test_duplicate_whitelist_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "duplicate_whitelist.txt"
            values = {"ABC123", "XYZ999"}
            storage.save_duplicate_whitelist(str(path), values)
            self.assertEqual(storage.load_duplicate_whitelist(str(path)), values)

    def test_vendor_codes_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vendor_codes.txt"
            storage.save_vendor_codes(str(path), ["gregdist", "motion", "GREGDIST"])
            self.assertEqual(storage.load_vendor_codes(str(path)), ["GREGDIST", "MOTION"])

    def test_order_rules_merge_preserves_unrelated_remote_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "order_rules.json"
            base = {"AER-:GH781-4": {"pack_size": 500}}
            storage.save_order_rules(str(path), base)
            loaded = storage.load_order_rules(str(path))
            storage.save_order_rules(str(path), {"GDY-:5VX560": {"pack_size": 3}})

            desired = dict(loaded)
            desired["AER-:GH781-4"] = {"pack_size": 600}
            result = storage.save_order_rules(str(path), desired, base_rules=loaded)

            self.assertEqual(result["payload"]["AER-:GH781-4"]["pack_size"], 600)
            self.assertEqual(result["payload"]["GDY-:5VX560"]["pack_size"], 3)

    def test_vendor_codes_merge_local_remove_with_remote_add(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vendor_codes.txt"
            storage.save_vendor_codes(str(path), ["MOTION", "SOURCE"])
            loaded = storage.load_vendor_codes(str(path))
            storage.save_vendor_codes(str(path), ["MOTION", "SOURCE", "GREGDIST"])

            result = storage.save_vendor_codes(str(path), ["MOTION"], base_vendor_codes=loaded)

            self.assertEqual(result["payload"], ["GREGDIST", "MOTION"])

    def test_save_session_snapshot_persists_json_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "sessions"
            snapshot = SessionSnapshot(
                created_at="2026-03-10T12:00:00",
                output_dir="C:\\Exports",
                po_files=("C:\\Exports\\PO_A.xlsx",),
                loaded_report_paths={"sales": "C:\\Reports\\sales.csv"},
                assigned_items=({"line_code": "AER-", "item_code": "GH781-4", "order_qty": 250},),
                maintenance_issues=(
                    MaintenanceIssue(
                        line_code="AER-",
                        item_code="GH781-4",
                        description="HOSE",
                        issue="Set order multiple to 500",
                        assigned_vendor="GREGDIST",
                        x4_supplier="(empty)",
                        pack_size="500",
                        x4_order_multiple="",
                        x4_min="22",
                        x4_max="67",
                        target_min="22",
                        target_max="67",
                        sug_min="22",
                        sug_max="67",
                        qoh_old="",
                        qoh_new="",
                    ),
                ),
                startup_warning_rows=({"warning_type": "Inventory Coverage Warning"},),
                qoh_adjustments=({"line_code": "AER-", "item_code": "GH781-4", "old": 2, "new": 5},),
                order_rules={"AER-:GH781-4": {"pack_size": 500}},
            )
            path = storage.save_session_snapshot(str(directory), snapshot, now=datetime(2026, 3, 10, 12, 0, 0))
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertEqual(payload["created_at"], "2026-03-10T12:00:00")
            self.assertEqual(payload["po_files"][0], "C:\\Exports\\PO_A.xlsx")
            self.assertEqual(payload["maintenance_issues"][0]["pack_size"], "500")
            self.assertTrue(Path(path).name.startswith("Session_20260310_120000_"))

    def test_suspense_carry_round_trip_and_prunes_stale_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "suspense_carry.json"
            now = datetime(2026, 3, 10, 12, 0, 0)
            carry = {
                ("AER-", "GH781-4"): {"qty": 5, "updated_at": now.isoformat()},
                ("OLD-", "STALE"): {"qty": 3, "updated_at": datetime(2026, 2, 1, 12, 0, 0).isoformat()},
            }
            storage.save_suspense_carry(str(path), carry, now=now)
            loaded = storage.load_suspense_carry(str(path), now=now, max_age_days=14)
            self.assertIn(("AER-", "GH781-4"), loaded)
            self.assertEqual(loaded[("AER-", "GH781-4")]["qty"], 5)
            self.assertNotIn(("OLD-", "STALE"), loaded)

    def test_save_order_rules_raises_when_write_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "order_rules.json"
            with patch("storage._atomic_write_text", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    storage.save_order_rules(str(path), {"AER-:GH781-4": {"pack_size": 500}})


if __name__ == "__main__":
    unittest.main()
