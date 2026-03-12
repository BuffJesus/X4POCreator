import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import data_folder_flow
import po_builder


class DataFolderFlowTests(unittest.TestCase):
    def test_configure_initial_data_dir_clears_invalid_shared_folder_setting(self):
        events = []
        fake_app = SimpleNamespace(
            app_settings={"shared_data_dir": "Z:\\Missing", "check_for_updates_on_startup": False},
            shared_data_dir="",
            data_dir=str(ROOT),
            _startup_data_dir_warning="",
            _save_app_settings=lambda: events.append("save"),
        )

        with patch("data_folder_flow.storage.validate_storage_directory", return_value=(False, "offline")):
            data_folder_flow.configure_initial_data_dir(fake_app)

        self.assertEqual(fake_app.shared_data_dir, "")
        self.assertEqual(fake_app.data_dir, str(ROOT))
        self.assertEqual(fake_app.app_settings["shared_data_dir"], "")
        self.assertFalse(fake_app.update_check_enabled)
        self.assertEqual(events, ["save"])
        self.assertIn("Shared data folder is unavailable", fake_app._startup_data_dir_warning)

    def test_load_persistent_state_updates_loaded_snapshots_and_refreshes_labels(self):
        fake_app = SimpleNamespace(
            dup_whitelist=set(),
            ignored_item_keys=set(),
            order_rules={},
            suspense_carry={},
            vendor_codes_used=[],
            _loaded_dup_whitelist=set(),
            _loaded_ignored_item_keys=set(),
            _loaded_order_rules={},
            _loaded_suspense_carry={},
            _loaded_vendor_codes=[],
            _data_path=lambda key: str(ROOT / f"{key}.txt"),
            _refresh_data_folder_labels=lambda: None,
        )

        with patch("data_folder_flow.storage.load_duplicate_whitelist", return_value=(["ABC123"], None)), \
             patch("data_folder_flow.storage.load_ignored_items", return_value=(["AER-:GH781-4"], None)), \
             patch("data_folder_flow.storage.load_order_rules_with_meta", return_value=({"AER-:GH781-4": {"pack_size": 8}}, None)), \
             patch("data_folder_flow.storage.load_suspense_carry_with_meta", return_value=({("AER-", "GH781-4"): {"qty": 2}}, None)), \
             patch("data_folder_flow.storage.load_vendor_codes", return_value=(["MOTION"], None)), \
             patch.object(fake_app, "_refresh_data_folder_labels") as mocked_refresh:
            data_folder_flow.load_persistent_state(fake_app, po_builder.KNOWN_VENDORS)

        self.assertEqual(fake_app.dup_whitelist, {"ABC123"})
        self.assertEqual(fake_app.ignored_item_keys, {"AER-:GH781-4"})
        self.assertEqual(fake_app.order_rules["AER-:GH781-4"]["pack_size"], 8)
        self.assertEqual(fake_app.suspense_carry[("AER-", "GH781-4")]["qty"], 2)
        self.assertEqual(fake_app.vendor_codes_used, ["MOTION"])
        self.assertEqual(fake_app._loaded_vendor_codes, ["MOTION"])
        mocked_refresh.assert_called_once_with()

    def test_refresh_active_data_state_uses_default_lookback_when_control_fails(self):
        events = []
        filtered = [{
            "line_code": "MOT-",
            "item_code": "ABC123",
            "pack_size": None,
            "vendor": "SOURCE",
            "final_qty": 4,
            "order_qty": 4,
        }]
        fake_app = SimpleNamespace(
            filtered_items=filtered,
            assigned_items=[],
            individual_items=[],
            ignored_item_keys=set(),
            dup_whitelist=set(),
            inventory_lookup={("MOT-", "ABC123"): {"qoh": 3}},
            order_rules={"MOT-:ABC123": {"pack_size": 6}},
            recent_orders={},
            data_dir=str(ROOT),
            var_lookback_days=SimpleNamespace(get=lambda: (_ for _ in ()).throw(RuntimeError("bad var"))),
            _refresh_vendor_inputs=lambda: events.append("vendors"),
            _resolve_pack_size=lambda key: 12,
            _recalculate_item=lambda item: item.update({"recalculated": True}),
            _sync_review_item_to_filtered=lambda item: item,
            _apply_bulk_filter=lambda: events.append("bulk"),
            _update_bulk_summary=lambda: events.append("summary"),
            _load_persistent_state=lambda: events.append("load"),
            _data_path=lambda key: str(ROOT / f"test_{key}"),
            _has_active_assignment_session=lambda: True,
            _prune_ignored_items_from_session=lambda: False,
            _rebuild_duplicate_ic_lookup=lambda: None,
            _ignore_key=lambda lc, ic: f"{lc}:{ic}",
        )

        with patch("data_folder_flow.storage.get_recent_orders", return_value={}) as mocked_recent, \
             patch("data_folder_flow.messagebox.showinfo") as mocked_info:
            result = data_folder_flow.refresh_active_data_state(
                fake_app,
                po_builder.KNOWN_VENDORS,
                po_builder.get_rule_key,
            )

        self.assertEqual(events, ["load", "vendors", "bulk", "summary"])
        self.assertEqual(filtered[0]["pack_size"], 6)
        self.assertTrue(filtered[0]["recalculated"])
        self.assertEqual(result, {"session_updated": True, "ignored_changed_session": False})
        mocked_recent.assert_called_once_with(str(ROOT / "test_order_history"), 14)
        mocked_info.assert_called_once()


if __name__ == "__main__":
    unittest.main()
