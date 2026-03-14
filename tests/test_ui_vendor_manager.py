import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_vendor_manager


class UIVendorManagerTests(unittest.TestCase):
    def test_apply_vendor_policy_preset_uses_common_template(self):
        events = []
        fake_app = SimpleNamespace(
            vendor_policies={},
            tree=object(),
            _normalize_vendor_code=lambda value: str(value or "").strip().upper(),
            _save_vendor_policies=lambda: events.append("save"),
            _annotate_release_decisions=lambda: events.append("annotate"),
            _apply_bulk_filter=lambda: events.append("bulk"),
            _update_bulk_summary=lambda: events.append("summary"),
            _populate_review_tab=lambda: events.append("review"),
        )

        result = ui_vendor_manager.apply_vendor_policy_preset(fake_app, "motion", "hybrid_friday_2000")

        self.assertTrue(result)
        self.assertEqual(fake_app.vendor_policies["MOTION"]["shipping_policy"], "hybrid_free_day_threshold")
        self.assertEqual(fake_app.vendor_policies["MOTION"]["preferred_free_ship_weekdays"], ["Friday"])
        self.assertEqual(fake_app.vendor_policies["MOTION"]["free_freight_threshold"], 2000.0)
        self.assertEqual(fake_app.vendor_policies["MOTION"]["urgent_release_floor"], 0.0)
        self.assertEqual(fake_app.vendor_policies["MOTION"]["urgent_release_mode"], "release_now")
        self.assertEqual(fake_app.vendor_policies["MOTION"]["release_lead_business_days"], 1)
        self.assertEqual(events, ["save", "annotate", "bulk", "summary", "review"])

    def test_apply_vendor_policy_preset_rejects_unknown_template(self):
        fake_app = SimpleNamespace(vendor_policies={})

        result = ui_vendor_manager.apply_vendor_policy_preset(fake_app, "motion", "missing")

        self.assertFalse(result)

    def test_apply_vendor_policy_changes_persists_and_refreshes_session_annotations(self):
        events = []
        fake_app = SimpleNamespace(
            vendor_policies={},
            tree=object(),
            _normalize_vendor_code=lambda value: str(value or "").strip().upper(),
            _save_vendor_policies=lambda: events.append("save"),
            _annotate_release_decisions=lambda: events.append("annotate"),
            _apply_bulk_filter=lambda: events.append("bulk"),
            _update_bulk_summary=lambda: events.append("summary"),
            _populate_review_tab=lambda: events.append("review"),
        )

        result = ui_vendor_manager.apply_vendor_policy_changes(
            fake_app,
            "motion",
            shipping_policy="hold_for_threshold",
            weekdays="Fri",
            threshold="2000",
            urgent_floor="10",
            urgent_mode="paid_urgent_freight",
            release_lead_days="3",
        )

        self.assertTrue(result)
        self.assertEqual(fake_app.vendor_policies["MOTION"]["shipping_policy"], "hold_for_threshold")
        self.assertEqual(fake_app.vendor_policies["MOTION"]["preferred_free_ship_weekdays"], [])
        self.assertEqual(fake_app.vendor_policies["MOTION"]["free_freight_threshold"], 2000.0)
        self.assertEqual(fake_app.vendor_policies["MOTION"]["urgent_release_floor"], 10.0)
        self.assertEqual(fake_app.vendor_policies["MOTION"]["urgent_release_mode"], "paid_urgent_freight")
        self.assertEqual(fake_app.vendor_policies["MOTION"]["release_lead_business_days"], 1)
        self.assertEqual(events, ["save", "annotate", "bulk", "summary", "review"])

    def test_apply_vendor_policy_changes_clears_default_policy(self):
        events = []
        fake_app = SimpleNamespace(
            vendor_policies={"MOTION": {"shipping_policy": "hold_for_threshold"}},
            _normalize_vendor_code=lambda value: str(value or "").strip().upper(),
            _save_vendor_policies=lambda: events.append("save"),
        )

        result = ui_vendor_manager.apply_vendor_policy_changes(
            fake_app,
            "motion",
            shipping_policy="release_immediately",
            weekdays="",
            threshold="",
            urgent_floor="",
            urgent_mode="release_now",
            release_lead_days="1",
        )

        self.assertTrue(result)
        self.assertNotIn("MOTION", fake_app.vendor_policies)
        self.assertEqual(events, ["save"])

    def test_apply_vendor_policy_changes_normalizes_invalid_and_negative_input(self):
        fake_app = SimpleNamespace(
            vendor_policies={},
            _normalize_vendor_code=lambda value: str(value or "").strip().upper(),
            _save_vendor_policies=lambda: None,
        )

        result = ui_vendor_manager.apply_vendor_policy_changes(
            fake_app,
            "motion",
            shipping_policy="not_real",
            weekdays="Fri, Noday",
            threshold="-2000",
            urgent_floor="-5",
            urgent_mode="bad_mode",
            release_lead_days="-2",
        )

        self.assertTrue(result)
        self.assertNotIn("MOTION", fake_app.vendor_policies)

    def test_apply_vendor_policy_changes_persists_release_lead_days_for_free_day_policy(self):
        fake_app = SimpleNamespace(
            vendor_policies={},
            _normalize_vendor_code=lambda value: str(value or "").strip().upper(),
            _save_vendor_policies=lambda: None,
        )

        result = ui_vendor_manager.apply_vendor_policy_changes(
            fake_app,
            "motion",
            shipping_policy="hold_for_free_day",
            weekdays="Fri",
            threshold="",
            urgent_floor="",
            urgent_mode="release_now",
            release_lead_days="2",
        )

        self.assertTrue(result)
        self.assertEqual(fake_app.vendor_policies["MOTION"]["release_lead_business_days"], 2)


if __name__ == "__main__":
    unittest.main()
