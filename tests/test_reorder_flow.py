import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import reorder_flow


class ReorderFlowTests(unittest.TestCase):
    def test_get_cycle_weeks_defaults_to_biweekly_for_unknown_value(self):
        fake_app = SimpleNamespace(var_reorder_cycle=SimpleNamespace(get=lambda: "Quarterly"))

        result = reorder_flow.get_cycle_weeks(fake_app)

        self.assertEqual(result, 2)

    def test_default_vendor_for_key_normalizes_supplier(self):
        fake_app = SimpleNamespace(inventory_lookup={("AER-", "GH781-4"): {"supplier": " motion "}})

        result = reorder_flow.default_vendor_for_key(fake_app, ("AER-", "GH781-4"))

        self.assertEqual(result, "MOTION")

    def test_refresh_recent_orders_uses_default_lookback_on_control_error(self):
        events = []
        fake_app = SimpleNamespace(
            var_lookback_days=SimpleNamespace(get=lambda: (_ for _ in ()).throw(RuntimeError("bad"))),
            _data_path=lambda key: str(ROOT / f"{key}.json"),
            _apply_bulk_filter=lambda: events.append("bulk"),
            recent_orders={},
        )

        with patch("reorder_flow.storage.get_recent_orders", return_value={"ok": True}) as mocked_recent:
            reorder_flow.refresh_recent_orders(fake_app)

        self.assertEqual(fake_app.recent_orders, {"ok": True})
        mocked_recent.assert_called_once_with(str(ROOT / "order_history.json"), 14)
        self.assertEqual(events, ["bulk"])

    def test_refresh_suggestions_recalculates_filtered_and_assigned_then_filters(self):
        events = []
        filtered = [{"item_code": "A"}]
        assigned = [{"item_code": "A"}]
        fake_app = SimpleNamespace(
            filtered_items=filtered,
            assigned_items=assigned,
            _recalculate_item=lambda item: events.append(("recalc", item["item_code"])),
            _sync_review_item_to_filtered=lambda item: events.append(("sync", item["item_code"])),
            _apply_bulk_filter=lambda: events.append(("bulk", None)),
        )

        reorder_flow.refresh_suggestions(fake_app)

        self.assertEqual(events, [("recalc", "A"), ("sync", "A"), ("bulk", None)])


if __name__ == "__main__":
    unittest.main()
