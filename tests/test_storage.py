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

    def test_vendor_policies_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vendor_policies.json"
            payload = {"MOTION": {"shipping_policy": "hold_for_threshold", "free_freight_threshold": 2000}}
            storage.save_vendor_policies(str(path), payload)
            self.assertEqual(storage.load_vendor_policies(str(path)), {
                "MOTION": {
                    "shipping_policy": "hold_for_threshold",
                    "preferred_free_ship_weekdays": [],
                    "free_freight_threshold": 2000.0,
                    "urgent_release_floor": 0.0,
                    "urgent_release_mode": "release_now",
                    "release_lead_business_days": 1,
                }
            })

    def test_vendor_policies_round_trip_normalizes_vendor_codes_and_policy_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vendor_policies.json"
            payload = {
                " motion ": {
                    "shipping_policy": "hold_for_threshold",
                    "preferred_free_ship_weekdays": ["Fri"],
                    "free_freight_threshold": "-2000",
                    "urgent_release_floor": "-4",
                    "urgent_release_mode": "bad_mode",
                },
                "": {"shipping_policy": "hold_for_free_day"},
            }

            result = storage.save_vendor_policies(str(path), payload)

            self.assertEqual(result["payload"], {
                "MOTION": {
                    "shipping_policy": "hold_for_threshold",
                    "preferred_free_ship_weekdays": [],
                    "free_freight_threshold": 0.0,
                    "urgent_release_floor": 0.0,
                    "urgent_release_mode": "release_now",
                    "release_lead_business_days": 1,
                }
            })
            self.assertEqual(storage.load_vendor_policies(str(path)), result["payload"])

    def test_load_vendor_policies_normalizes_stale_disk_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vendor_policies.json"
            path.write_text(json.dumps({
                " motion ": {
                    "shipping_policy": "not_real",
                    "preferred_free_ship_weekdays": "Fri, Noday",
                    "free_freight_threshold": -2000,
                    "urgent_release_floor": -1,
                    "urgent_release_mode": "bad_mode",
                }
            }), encoding="utf-8")

            payload = storage.load_vendor_policies(str(path))

            self.assertEqual(payload, {
                "MOTION": {
                    "shipping_policy": "release_immediately",
                    "preferred_free_ship_weekdays": [],
                    "free_freight_threshold": 0.0,
                    "urgent_release_floor": 0.0,
                    "urgent_release_mode": "release_now",
                    "release_lead_business_days": 1,
                }
            })

    def test_vendor_policies_preserve_release_lead_days_for_free_day_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vendor_policies.json"
            payload = {
                "MOTION": {
                    "shipping_policy": "hold_for_free_day",
                    "preferred_free_ship_weekdays": ["Friday"],
                    "release_lead_business_days": 2,
                }
            }

            storage.save_vendor_policies(str(path), payload)

            self.assertEqual(storage.load_vendor_policies(str(path))["MOTION"]["release_lead_business_days"], 2)

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

    def test_append_order_history_skips_zero_qty_and_blank_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "order_history.json"
            now = datetime(2026, 3, 10, 12, 0, 0)
            assigned = [
                {"line_code": "AER-", "item_code": "GH781-4", "order_qty": 250, "vendor": "gregdist"},
                {"line_code": "AER-", "item_code": "ZERO-1", "order_qty": 0, "vendor": "MOTION"},
                {"line_code": "", "item_code": "BAD-1", "order_qty": 5, "vendor": "SOURCE"},
            ]

            result = storage.append_order_history(str(path), assigned, now=now)
            payload = storage.load_order_history(str(path))

            self.assertEqual(len(result["payload"]), 1)
            self.assertEqual(len(payload[0]["items"]), 1)
            self.assertEqual(payload[0]["items"][0]["vendor"], "GREGDIST")

    def test_append_order_history_does_not_create_empty_session_for_non_orders(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "order_history.json"
            now = datetime(2026, 3, 10, 12, 0, 0)

            result = storage.append_order_history(
                str(path),
                [{"line_code": "AER-", "item_code": "ZERO-1", "order_qty": 0, "vendor": "MOTION"}],
                now=now,
            )

            self.assertEqual(result["payload"], [])
            self.assertEqual(storage.load_order_history(str(path)), [])

    def test_get_recent_orders_ignores_zero_qty_and_normalizes_vendor(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "order_history.json"
            path.write_text(
                json.dumps([
                    {
                        "date": "2026-03-10T12:00:00",
                        "items": [
                            {"line_code": "AER-", "item_code": "GH781-4", "qty": "250", "vendor": "gregdist "},
                            {"line_code": "AER-", "item_code": "ZERO-1", "qty": 0, "vendor": "MOTION"},
                        ],
                    }
                ]),
                encoding="utf-8",
            )

            recent = storage.get_recent_orders(str(path), lookback_days=14, now=datetime(2026, 3, 10, 12, 0, 0))

            self.assertIn(("AER-", "GH781-4"), recent)
            self.assertNotIn(("AER-", "ZERO-1"), recent)
            self.assertEqual(recent[("AER-", "GH781-4")][0]["vendor"], "GREGDIST")

    def test_duplicate_whitelist_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "duplicate_whitelist.txt"
            values = {"ABC123", "XYZ999"}
            storage.save_duplicate_whitelist(str(path), values)
            self.assertEqual(storage.load_duplicate_whitelist(str(path)), values)

    def test_ignored_items_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ignored_items.txt"
            values = {"AER-:GH781-4", "MOT-:ABC123"}
            storage.save_ignored_items(str(path), values)
            self.assertEqual(storage.load_ignored_items(str(path)), values)

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

    def test_save_suspense_carry_prunes_stale_disk_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "suspense_carry.json"
            now = datetime(2026, 3, 10, 12, 0, 0)
            path.write_text(
                json.dumps({
                    "AER-:GH781-4": {"qty": 5, "updated_at": now.isoformat()},
                    "OLD-:STALE": {"qty": 3, "updated_at": "2026-02-01T12:00:00"},
                }),
                encoding="utf-8",
            )

            result = storage.save_suspense_carry(
                str(path),
                {("AER-", "GH781-4"): {"qty": 5, "updated_at": now.isoformat()}},
                now=now,
                base_carry={("AER-", "GH781-4"): {"qty": 5, "updated_at": now.isoformat()}},
            )

            raw_payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(result["payload"], {("AER-", "GH781-4"): {"qty": 5, "updated_at": now.isoformat()}})
            self.assertIn("AER-:GH781-4", raw_payload)
            self.assertNotIn("OLD-:STALE", raw_payload)

    def test_save_order_rules_raises_when_write_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "order_rules.json"
            with patch("storage._atomic_write_text", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    storage.save_order_rules(str(path), {"AER-:GH781-4": {"pack_size": 500}})

    def test_load_json_file_rejects_wrong_top_level_type_for_dict_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "order_rules.json"
            path.write_text('["not", "a", "dict"]', encoding="utf-8")

            payload = storage.load_json_file(str(path), {"fallback": True})

            self.assertEqual(payload, {"fallback": True})

    def test_load_json_file_rejects_wrong_top_level_type_for_list_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "order_history.json"
            path.write_text('{"not": "a list"}', encoding="utf-8")

            payload = storage.load_json_file(str(path), [])

            self.assertEqual(payload, [])

    def test_load_suspense_carry_ignores_non_dict_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "suspense_carry.json"
            path.write_text('["bad", "payload"]', encoding="utf-8")

            loaded = storage.load_suspense_carry(str(path), now=datetime(2026, 3, 10, 12, 0, 0))

            self.assertEqual(loaded, {})


if __name__ == "__main__":
    unittest.main()
