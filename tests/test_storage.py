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
            assigned = [{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "order_qty": 250,
                "vendor": "GREGDIST",
                "export_batch_type": "planned_release",
                "export_scope_label": "planned today items",
                "release_decision": "export_next_business_day_for_free_day",
                "target_order_date": "2026-03-10",
                "target_release_date": "2026-03-11",
            }]
            now = datetime(2026, 3, 10, 12, 0, 0)
            storage.append_order_history(str(path), assigned, now=now)
            recent = storage.get_recent_orders(str(path), lookback_days=14, now=now)
            self.assertIn(("AER-", "GH781-4"), recent)
            self.assertEqual(recent[("AER-", "GH781-4")][0]["qty"], 250)
            self.assertEqual(recent[("AER-", "GH781-4")][0]["vendor"], "GREGDIST")
            raw_history = storage.load_order_history(str(path))
            self.assertEqual(raw_history[0]["items"][0]["export_batch_type"], "planned_release")
            self.assertEqual(raw_history[0]["items"][0]["release_decision"], "export_next_business_day_for_free_day")

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
                export_scope_label="selected items",
                loaded_report_paths={"sales": "C:\\Reports\\sales.csv"},
                exported_items=({"line_code": "AER-", "item_code": "GH781-4", "order_qty": 250, "export_batch_type": "immediate"},),
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
            self.assertEqual(payload["export_scope_label"], "selected items")
            self.assertEqual(payload["exported_items"][0]["export_batch_type"], "immediate")
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

    # --- Phase 4: session history loading ---

    def test_load_session_snapshots_returns_empty_for_missing_directory(self):
        self.assertEqual(storage.load_session_snapshots("/nonexistent/path/xyz"), [])

    def test_load_session_snapshots_reads_recent_files_most_recent_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap1 = {"assigned_items": [{"line_code": "AER-", "item_code": "X1", "final_qty": 10}]}
            snap2 = {"assigned_items": [{"line_code": "AER-", "item_code": "X1", "final_qty": 20}]}
            p1 = Path(tmp) / "Session_20260301_120000_000001_1.json"
            p2 = Path(tmp) / "Session_20260315_120000_000001_2.json"
            p1.write_text(json.dumps(snap1), encoding="utf-8")
            p2.write_text(json.dumps(snap2), encoding="utf-8")
            import os, time
            os.utime(str(p1), (time.time() - 100, time.time() - 100))
            os.utime(str(p2), (time.time(), time.time()))
            result = storage.load_session_snapshots(tmp, max_count=2)
            self.assertEqual(len(result), 2)
            # Most recent first
            self.assertEqual(result[0]["assigned_items"][0]["final_qty"], 20)

    def test_load_session_snapshots_respects_max_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(5):
                p = Path(tmp) / f"Session_2026030{i}_120000_000001_{i}.json"
                p.write_text(json.dumps({"assigned_items": []}), encoding="utf-8")
            result = storage.load_session_snapshots(tmp, max_count=2)
            self.assertEqual(len(result), 2)

    def test_extract_order_history_builds_per_item_dict(self):
        snapshots = [
            {"assigned_items": [
                {"line_code": "AER-", "item_code": "X1", "final_qty": 10},
                {"line_code": "AER-", "item_code": "X2", "final_qty": 5},
            ]},
            {"assigned_items": [
                {"line_code": "AER-", "item_code": "X1", "final_qty": 20},
            ]},
        ]
        history = storage.extract_order_history(snapshots)
        self.assertIn(("AER-", "X1"), history)
        self.assertIn(("AER-", "X2"), history)
        self.assertCountEqual(history[("AER-", "X1")], [10, 20])
        self.assertEqual(history[("AER-", "X2")], [5])

    def test_extract_order_history_ignores_zero_and_missing_qty(self):
        snapshots = [
            {"assigned_items": [
                {"line_code": "AER-", "item_code": "X1", "final_qty": 0},
                {"line_code": "AER-", "item_code": "X1"},
                {"line_code": "", "item_code": "X1", "final_qty": 10},
            ]}
        ]
        history = storage.extract_order_history(snapshots)
        self.assertNotIn(("AER-", "X1"), history)


class InferVendorLeadTimesTests(unittest.TestCase):
    def _snap(self, created_at, items):
        return {"created_at": created_at, "assigned_items": items}

    def _item(self, lc, ic, vendor="ACME", qty_on_po=0, qty_received=0):
        return {
            "line_code": lc, "item_code": ic, "vendor": vendor,
            "qty_on_po": qty_on_po, "qty_received": qty_received,
        }

    def test_single_snapshot_returns_empty(self):
        snaps = [self._snap("2026-01-20T10:00:00", [self._item("AER-", "X1", qty_on_po=5)])]
        self.assertEqual(storage.infer_vendor_lead_times(snaps), {})

    def test_no_snapshots_returns_empty(self):
        self.assertEqual(storage.infer_vendor_lead_times([]), {})

    def test_basic_lead_time_inferred(self):
        # Item on PO in snap_a (older), received in snap_b (newer), 21 days apart
        # snapshots passed most-recent-first
        snap_b = self._snap("2026-02-10T10:00:00", [self._item("AER-", "X1", vendor="ACME", qty_received=10)])
        snap_a = self._snap("2026-01-20T10:00:00", [self._item("AER-", "X1", vendor="ACME", qty_on_po=5)])
        result = storage.infer_vendor_lead_times([snap_b, snap_a])
        self.assertEqual(result.get("ACME"), 21)

    def test_no_receipt_in_later_snapshot_omits_vendor(self):
        snap_b = self._snap("2026-02-10T10:00:00", [self._item("AER-", "X1", vendor="ACME", qty_received=0)])
        snap_a = self._snap("2026-01-20T10:00:00", [self._item("AER-", "X1", vendor="ACME", qty_on_po=5)])
        self.assertEqual(storage.infer_vendor_lead_times([snap_b, snap_a]), {})

    def test_no_open_po_in_earlier_snapshot_omits_vendor(self):
        snap_b = self._snap("2026-02-10T10:00:00", [self._item("AER-", "X1", vendor="ACME", qty_received=10)])
        snap_a = self._snap("2026-01-20T10:00:00", [self._item("AER-", "X1", vendor="ACME", qty_on_po=0)])
        self.assertEqual(storage.infer_vendor_lead_times([snap_b, snap_a]), {})

    def test_different_item_in_later_snapshot_omits_vendor(self):
        # Received X2, but X1 was on PO — no match
        snap_b = self._snap("2026-02-10T10:00:00", [self._item("AER-", "X2", vendor="ACME", qty_received=10)])
        snap_a = self._snap("2026-01-20T10:00:00", [self._item("AER-", "X1", vendor="ACME", qty_on_po=5)])
        self.assertEqual(storage.infer_vendor_lead_times([snap_b, snap_a]), {})

    def test_vendor_code_normalized_to_uppercase(self):
        snap_b = self._snap("2026-02-10T10:00:00", [self._item("AER-", "X1", vendor="acme", qty_received=5)])
        snap_a = self._snap("2026-01-20T10:00:00", [self._item("AER-", "X1", vendor="acme", qty_on_po=5)])
        result = storage.infer_vendor_lead_times([snap_b, snap_a])
        self.assertIn("ACME", result)

    def test_median_computed_over_multiple_observations(self):
        # Three items received from ACME: gaps of 10, 20, 30 days → median 20
        snap_a = self._snap("2026-01-01T00:00:00", [
            self._item("AER-", "A", vendor="ACME", qty_on_po=1),
            self._item("AER-", "B", vendor="ACME", qty_on_po=1),
            self._item("AER-", "C", vendor="ACME", qty_on_po=1),
        ])
        snap_b = self._snap("2026-01-21T00:00:00", [
            self._item("AER-", "A", vendor="ACME", qty_received=1),
            self._item("AER-", "B", vendor="ACME", qty_received=1),
            self._item("AER-", "C", vendor="ACME", qty_received=1),
        ])
        result = storage.infer_vendor_lead_times([snap_b, snap_a])
        self.assertEqual(result.get("ACME"), 20)

    def test_multiple_vendors_inferred_independently(self):
        snap_a = self._snap("2026-01-01T00:00:00", [
            self._item("AER-", "X1", vendor="ACME", qty_on_po=1),
            self._item("AER-", "X2", vendor="BETA", qty_on_po=1),
        ])
        snap_b = self._snap("2026-01-15T00:00:00", [
            self._item("AER-", "X1", vendor="ACME", qty_received=1),
            self._item("AER-", "X2", vendor="BETA", qty_received=1),
        ])
        result = storage.infer_vendor_lead_times([snap_b, snap_a])
        self.assertEqual(result.get("ACME"), 14)
        self.assertEqual(result.get("BETA"), 14)

    def test_elapsed_days_clamped_to_minimum_1(self):
        # Snapshots on same day should still produce elapsed = 0, skipped
        snap_a = self._snap("2026-01-10T08:00:00", [self._item("AER-", "X1", vendor="ACME", qty_on_po=1)])
        snap_b = self._snap("2026-01-10T10:00:00", [self._item("AER-", "X1", vendor="ACME", qty_received=1)])
        # elapsed_days = 0 → skipped → empty
        self.assertEqual(storage.infer_vendor_lead_times([snap_b, snap_a]), {})

    def test_missing_created_at_skips_pair(self):
        snap_a = {"assigned_items": [self._item("AER-", "X1", vendor="ACME", qty_on_po=5)]}
        snap_b = self._snap("2026-02-01T00:00:00", [self._item("AER-", "X1", vendor="ACME", qty_received=5)])
        self.assertEqual(storage.infer_vendor_lead_times([snap_b, snap_a]), {})

    def test_three_snapshots_uses_consecutive_pairs(self):
        # snap_oldest → snap_mid: 14 days, snap_mid → snap_newest: 10 days
        # X1 on PO in oldest, received in mid → 14 days
        # X2 on PO in mid, received in newest → 10 days
        snap_oldest = self._snap("2026-01-01T00:00:00", [self._item("AER-", "X1", vendor="ACME", qty_on_po=1)])
        snap_mid = self._snap("2026-01-15T00:00:00", [
            self._item("AER-", "X1", vendor="ACME", qty_received=1),
            self._item("AER-", "X2", vendor="ACME", qty_on_po=1),
        ])
        snap_newest = self._snap("2026-01-25T00:00:00", [self._item("AER-", "X2", vendor="ACME", qty_received=1)])
        result = storage.infer_vendor_lead_times([snap_newest, snap_mid, snap_oldest])
        # observations: [14, 10], median of sorted [10, 14] → (10+14)//2 = 12
        self.assertEqual(result.get("ACME"), 12)

    def test_vendor_policies_round_trip_preserves_estimated_lead_days(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vendor_policies.json"
            payload = {
                "ACME": {
                    "shipping_policy": "hold_for_free_day",
                    "preferred_free_ship_weekdays": ["Friday"],
                    "estimated_lead_days": 18,
                }
            }
            storage.save_vendor_policies(str(path), payload)
            loaded = storage.load_vendor_policies(str(path))
            self.assertEqual(loaded["ACME"]["estimated_lead_days"], 18)

    def test_normalize_vendor_policy_strips_invalid_estimated_lead_days(self):
        import shipping_flow
        policy = {"estimated_lead_days": "bad"}
        result = shipping_flow.normalize_vendor_policy(policy)
        self.assertNotIn("estimated_lead_days", result)

    def test_normalize_vendor_policy_clamps_estimated_lead_days_minimum_1(self):
        import shipping_flow
        policy = {"estimated_lead_days": 0}
        result = shipping_flow.normalize_vendor_policy(policy)
        self.assertEqual(result["estimated_lead_days"], 1)


if __name__ == "__main__":
    unittest.main()
