import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import persistent_state_flow


class PersistentStateFlowTests(unittest.TestCase):
    def test_save_order_rules_updates_loaded_snapshot_from_storage_payload(self):
        fake_app = SimpleNamespace(
            order_rules={"AER-:GH781-4": {"pack_size": 8}},
            _loaded_order_rules={"AER-:GH781-4": {"pack_size": 6}},
            _data_path=lambda key: str(ROOT / key),
        )

        with patch(
            "persistent_state_flow.storage.save_order_rules",
            return_value={"payload": {"AER-:GH781-4": {"pack_size": 10}}},
        ) as mocked_save:
            persistent_state_flow.save_order_rules(fake_app)

        self.assertEqual(fake_app.order_rules["AER-:GH781-4"]["pack_size"], 10)
        self.assertEqual(fake_app._loaded_order_rules["AER-:GH781-4"]["pack_size"], 10)
        mocked_save.assert_called_once()

    def test_save_vendor_codes_uses_merged_payload_from_storage(self):
        fake_app = SimpleNamespace(
            vendor_codes_used=["MOTION"],
            _loaded_vendor_codes=["MOTION"],
            _data_path=lambda key: str(ROOT / key),
        )

        with patch(
            "persistent_state_flow.storage.save_vendor_codes",
            return_value={"payload": ["GREGDIST", "MOTION"]},
        ) as mocked_save:
            persistent_state_flow.save_vendor_codes(fake_app)

        self.assertEqual(fake_app.vendor_codes_used, ["GREGDIST", "MOTION"])
        self.assertEqual(fake_app._loaded_vendor_codes, ["GREGDIST", "MOTION"])
        mocked_save.assert_called_once()

    def test_save_vendor_policies_uses_merged_payload_from_storage(self):
        fake_app = SimpleNamespace(
            vendor_policies={"MOTION": {"shipping_policy": "hold_for_threshold"}},
            _loaded_vendor_policies={"MOTION": {"shipping_policy": "release_immediately"}},
            _data_path=lambda key: str(ROOT / key),
        )

        with patch(
            "persistent_state_flow.storage.save_vendor_policies",
            return_value={"payload": {"MOTION": {"shipping_policy": "hold_for_free_day"}}},
        ) as mocked_save:
            persistent_state_flow.save_vendor_policies(fake_app)

        self.assertEqual(fake_app.vendor_policies["MOTION"]["shipping_policy"], "hold_for_free_day")
        self.assertEqual(fake_app._loaded_vendor_policies["MOTION"]["shipping_policy"], "hold_for_free_day")
        mocked_save.assert_called_once()

    def test_rename_vendor_code_updates_session_collections_and_persists(self):
        events = []
        fake_app = SimpleNamespace(
            vendor_codes_used=["GREGDIST", "MOTION"],
            vendor_policies={"GREGDIST": {"shipping_policy": "hold_for_threshold"}},
            filtered_items=[{"vendor": "GREGDIST"}],
            individual_items=[{"vendor": "gregdist"}],
            assigned_items=[{"vendor": "GREGDIST"}],
            _normalize_vendor_code=persistent_state_flow.normalize_vendor_code,
            _save_vendor_codes=lambda: events.append("save"),
            _save_vendor_policies=lambda: events.append("save_policy"),
            _refresh_vendor_inputs=lambda: events.append("refresh"),
        )

        result = persistent_state_flow.rename_vendor_code(fake_app, "gregdist", "source")

        self.assertEqual(result, "SOURCE")
        self.assertEqual(fake_app.vendor_codes_used, ["MOTION", "SOURCE"])
        self.assertEqual(fake_app.vendor_policies["SOURCE"]["shipping_policy"], "hold_for_threshold")
        self.assertNotIn("GREGDIST", fake_app.vendor_policies)
        self.assertEqual(fake_app.filtered_items[0]["vendor"], "SOURCE")
        self.assertEqual(fake_app.individual_items[0]["vendor"], "SOURCE")
        self.assertEqual(fake_app.assigned_items[0]["vendor"], "SOURCE")
        self.assertEqual(events, ["save", "save_policy", "refresh"])

    def test_get_suspense_carry_qty_clamps_invalid_values(self):
        fake_app = SimpleNamespace(suspense_carry={("AER-", "GH781-4"): {"qty": "bad"}})

        result = persistent_state_flow.get_suspense_carry_qty(fake_app, ("AER-", "GH781-4"))

        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
