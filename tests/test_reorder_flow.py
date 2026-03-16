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

    def test_default_vendor_for_key_prefers_unique_receipt_vendor_over_supplier(self):
        fake_app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"supplier": " source "}},
            receipt_history_lookup={("AER-", "GH781-4"): {"vendor_candidates": ["MOTION"], "primary_vendor": "MOTION", "vendor_confidence": "high"}},
        )

        result = reorder_flow.default_vendor_for_key(fake_app, ("AER-", "GH781-4"))

        self.assertEqual(result, "MOTION")

    def test_default_vendor_for_key_uses_high_confidence_dominant_receipt_vendor(self):
        fake_app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"supplier": " source "}},
            receipt_history_lookup={("AER-", "GH781-4"): {
                "vendor_candidates": ["MOTION", "SOURCE"],
                "primary_vendor": "MOTION",
                "vendor_confidence": "high",
                "vendor_confidence_reason": "dominant_recent_vendor",
                "primary_vendor_qty_share": 0.83,
                "primary_vendor_receipt_share": 0.67,
            }},
        )

        result = reorder_flow.default_vendor_for_key(fake_app, ("AER-", "GH781-4"))

        self.assertEqual(result, "MOTION")

    def test_default_vendor_for_key_returns_blank_when_receipt_history_is_mixed(self):
        fake_app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"supplier": " source "}},
            receipt_history_lookup={("AER-", "GH781-4"): {"vendor_candidates": ["MOTION", "GREGDIST"], "primary_vendor": "MOTION", "vendor_confidence": "medium"}},
        )

        result = reorder_flow.default_vendor_for_key(fake_app, ("AER-", "GH781-4"))

        self.assertEqual(result, "")

    def test_suggest_min_max_uses_detailed_sales_stats_when_mo12_sales_missing(self):
        fake_app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"mo12_sales": 0}},
            detailed_sales_stats_lookup={("AER-", "GH781-4"): {"annualized_qty_sold": 104}},
            _get_cycle_weeks=lambda: 2,
        )

        result = reorder_flow.suggest_min_max(fake_app, ("AER-", "GH781-4"), min_annual_sales_for_suggestions=12)

        self.assertEqual(result, (4, 8))

    def test_suggest_min_max_prefers_mo12_sales_over_detailed_sales_stats(self):
        fake_app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"mo12_sales": 52}},
            detailed_sales_stats_lookup={("AER-", "GH781-4"): {"annualized_qty_sold": 104}},
            _get_cycle_weeks=lambda: 2,
        )

        result = reorder_flow.suggest_min_max(fake_app, ("AER-", "GH781-4"), min_annual_sales_for_suggestions=12)

        self.assertEqual(result, (2, 4))

    def test_suggest_min_max_suppresses_sparse_detailed_sales_fallback(self):
        fake_app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"mo12_sales": 0}},
            detailed_sales_stats_lookup={("AER-", "GH781-4"): {
                "annualized_qty_sold": 104,
                "transaction_count": 2,
                "sale_day_count": 2,
                "avg_units_per_transaction": 52.0,
                "median_units_per_transaction": 52.0,
                "max_units_per_transaction": 52.0,
                "avg_days_between_sales": 45.0,
            }},
            _get_cycle_weeks=lambda: 2,
        )

        result = reorder_flow.suggest_min_max(fake_app, ("AER-", "GH781-4"), min_annual_sales_for_suggestions=12)

        self.assertEqual(result, (None, None))

    def test_suggest_min_max_suppresses_lumpy_detailed_sales_fallback(self):
        fake_app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"mo12_sales": 0}},
            detailed_sales_stats_lookup={("AER-", "GH781-4"): {
                "annualized_qty_sold": 104,
                "transaction_count": 4,
                "sale_day_count": 4,
                "avg_units_per_transaction": 6.0,
                "median_units_per_transaction": 4.0,
                "max_units_per_transaction": 18.0,
                "avg_days_between_sales": 28.0,
            }},
            _get_cycle_weeks=lambda: 2,
        )

        result = reorder_flow.suggest_min_max(fake_app, ("AER-", "GH781-4"), min_annual_sales_for_suggestions=12)

        self.assertEqual(result, (None, None))

    def test_suggest_min_max_raises_steady_repeat_fallback_to_transaction_floor(self):
        fake_app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"mo12_sales": 0}},
            detailed_sales_stats_lookup={("AER-", "GH781-4"): {
                "annualized_qty_sold": 26,
                "transaction_count": 6,
                "sale_day_count": 5,
                "avg_units_per_transaction": 3.0,
                "median_units_per_transaction": 3.0,
                "max_units_per_transaction": 4.0,
                "avg_days_between_sales": 7.0,
            }},
            _get_cycle_weeks=lambda: 2,
        )

        result = reorder_flow.suggest_min_max(fake_app, ("AER-", "GH781-4"), min_annual_sales_for_suggestions=12)

        self.assertEqual(result, (3, 6))

    def test_refresh_recent_orders_uses_default_lookback_on_control_error(self):
        events = []
        fake_app = SimpleNamespace(
            var_lookback_days=SimpleNamespace(get=lambda: (_ for _ in ()).throw(RuntimeError("bad"))),
            _data_path=lambda key: str(ROOT / f"{key}.json"),
            _apply_bulk_filter=lambda: events.append("bulk"),
            _recalculate_item=lambda item, annotate_release=False: events.append(("recalc", item["item_code"], annotate_release)),
            _annotate_release_decisions=lambda: events.append(("annotate", None)),
            recent_orders={},
            filtered_items=[{"line_code": "AER-", "item_code": "GH781-4"}],
            assigned_items=[{"line_code": "AER-", "item_code": "GH781-4"}],
        )

        with patch("reorder_flow.storage.get_recent_orders", return_value={
            ("AER-", "GH781-4"): [{"qty": 2, "vendor": "MOTION", "date": "2026-03-10"}]
        }) as mocked_recent:
            reorder_flow.refresh_recent_orders(fake_app)

        self.assertIn(("AER-", "GH781-4"), fake_app.recent_orders)
        mocked_recent.assert_called_once_with(str(ROOT / "order_history.json"), 14)
        self.assertEqual(fake_app.filtered_items[0]["recent_local_order_count"], 1)
        self.assertEqual(fake_app.filtered_items[0]["recent_local_order_qty"], 2)
        self.assertTrue(fake_app.assigned_items[0]["has_recent_local_order"])
        self.assertIn(("recalc", "GH781-4", False), events)
        self.assertIn(("annotate", None), events)
        self.assertEqual(events[-1], "bulk")

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
