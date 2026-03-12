import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_state_flow


class UIStateFlowTests(unittest.TestCase):
    def test_refresh_vendor_inputs_populates_bulk_vendor_filter_values(self):
        combo_bulk_vendor = {}
        combo_vendor = {}
        combo_vendor_filter = {}
        fake_app = SimpleNamespace(
            vendor_codes_used=["MOTION", "SOURCE"],
            assigned_items=[
                {"vendor": "SOURCE"},
                {"vendor": "MOTION"},
                {"vendor": ""},
                {},
            ],
            combo_bulk_vendor=combo_bulk_vendor,
            combo_vendor=combo_vendor,
            combo_vendor_filter=combo_vendor_filter,
        )

        ui_state_flow.refresh_vendor_inputs(fake_app)

        self.assertEqual(combo_bulk_vendor["values"], ["MOTION", "SOURCE"])
        self.assertEqual(combo_vendor["values"], ["MOTION", "SOURCE"])
        self.assertEqual(combo_vendor_filter["values"], ["ALL", "MOTION", "SOURCE"])

    def test_remove_vendor_code_normalizes_and_refreshes(self):
        events = []
        fake_app = SimpleNamespace(
            vendor_codes_used=["GREGDIST", "MOTION"],
            _normalize_vendor_code=lambda value: str(value or "").strip().upper(),
            _save_vendor_codes=lambda: events.append("save"),
            _refresh_vendor_inputs=lambda: events.append("refresh"),
        )

        ui_state_flow.remove_vendor_code(fake_app, " gregdist ")

        self.assertEqual(fake_app.vendor_codes_used, ["MOTION"])
        self.assertEqual(events, ["save", "refresh"])


if __name__ == "__main__":
    unittest.main()
