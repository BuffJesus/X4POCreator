"""Perf baseline regression tests for the bulk grid hot paths.

These tests run against a synthetic 8,000-item fixture and assert
that the pure-Python layers of the bulk grid stay under a wall-clock
budget.  The budgets are deliberately loose (5-10× the measured time
on a typical dev machine) so the suite stays stable across CI
environments but still catches catastrophic regressions — e.g. an
O(n²) loop introduced by a future bucket rewrite.

Measured on the user's real 8,409-item `Order/` dataset (2026-04-08):

    sync_bulk_session_metadata           33 ms
    bulk_row_values        x8409         86 ms (10 us/row)
    bulk_row_render_signature x8409      35 ms (4 us/row)
    cached_bulk_row_values second pass   47 ms
    filtered_candidate_items (single)  0.01 ms
    item_matches_bulk_filter x8409      6 ms

The budgets below give ~5-10× headroom on the measured time.  If
a future change blows through them, either the optimization goal
slipped or a real regression landed — either way the test fails
loudly instead of silently degrading operator UX.
"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_bulk

ITEM_COUNT = 8000


def _build_fixture_items():
    """8,000 synthetic items with the field shape the bulk grid reads."""
    items = []
    for i in range(ITEM_COUNT):
        line_code = f"L{i // 200:03d}-"
        item_code = f"IC{i:05d}"
        # Spread items across status buckets so the Skip / OK / No Pack
        # filters each hit non-trivial subsets.
        status = "skip" if i % 3 == 0 else ("review" if i % 3 == 1 else "ok")
        data_flags = ["missing_pack"] if i % 2 == 0 else []
        items.append({
            "line_code": line_code,
            "item_code": item_code,
            "description": f"ITEM {i}",
            "vendor": "V1" if i % 4 == 0 else "",
            "status": status,
            "data_flags": data_flags,
            "performance_profile": "steady",
            "sales_health_signal": "active",
            "reorder_attention_signal": "normal",
            "stockout_risk_score": 0.1 + (i % 10) * 0.08,
            "raw_need": 0 if status == "skip" else 5,
            "suggested_qty": 0 if status == "skip" else 5,
            "final_qty": 0 if status == "skip" else 5,
            "order_qty": 5,
            "pack_size": None,
            "why": "",
            "order_policy": "standard",
        })
    return items


def _build_fixture_app(items):
    app = SimpleNamespace(
        filtered_items=items,
        inventory_lookup={
            (it["line_code"], it["item_code"]): {"supplier": "V1", "qoh": 0, "min": None, "max": None}
            for it in items
        },
        order_rules={},
        var_reorder_cycle=SimpleNamespace(get=lambda: "Biweekly"),
    )
    app._suggest_min_max = lambda key: (None, None)
    app._bulk_row_render_cache = None
    return app


def _default_filter_state(**overrides):
    state = {
        "lc": "ALL", "status": "ALL", "source": "ALL",
        "item_status": "ALL", "performance": "ALL",
        "sales_health": "ALL", "attention": "ALL", "text": "",
    }
    state.update(overrides)
    return state


class BulkPerfBaselineTests(unittest.TestCase):
    def setUp(self):
        self.items = _build_fixture_items()
        self.app = _build_fixture_app(self.items)

    def _time(self, fn):
        start = time.perf_counter()
        fn()
        return (time.perf_counter() - start) * 1000  # milliseconds

    def test_sync_bulk_session_metadata_under_200ms(self):
        # Measured: ~33ms on 8,409 items.  Budget: 200ms (6× headroom).
        elapsed = self._time(lambda: ui_bulk.sync_bulk_session_metadata(self.app, self.items))
        self.assertLess(elapsed, 200, f"metadata build took {elapsed:.0f}ms")

    def test_bulk_row_render_signature_under_250ms(self):
        # Measured: ~35ms on 8,409 items.  Budget: 250ms (7× headroom).
        def run():
            for item in self.items:
                ui_bulk.bulk_row_render_signature(self.app, item)
        elapsed = self._time(run)
        self.assertLess(elapsed, 250, f"signature loop took {elapsed:.0f}ms")

    def test_item_matches_bulk_filter_under_100ms(self):
        # Measured: ~6ms on 8,409 items.  Budget: 100ms (15× headroom).
        state = _default_filter_state(item_status="Skip")
        def run():
            for item in self.items:
                ui_bulk.item_matches_bulk_filter(item, state)
        elapsed = self._time(run)
        self.assertLess(elapsed, 100, f"matcher loop took {elapsed:.0f}ms")

    def test_filtered_candidate_items_fast_path_under_50ms(self):
        # Measured: <1ms single call.  Budget: 50ms (very loose — the
        # fast path is index-lookup bound).
        ui_bulk.sync_bulk_session_metadata(self.app, self.items)
        state = _default_filter_state(item_status="Skip")
        elapsed = self._time(lambda: ui_bulk.filtered_candidate_items(self.app, state))
        self.assertLess(elapsed, 50, f"fast path took {elapsed:.0f}ms")

    def test_matcher_and_fast_path_agree_on_fixture(self):
        # Perf test doubles as a correctness guard: every single-dim
        # filter must produce identical sets via matcher and fast path.
        ui_bulk.sync_bulk_session_metadata(self.app, self.items)
        for item_status in ("OK", "Review", "Skip", "No Pack"):
            state = _default_filter_state(item_status=item_status)
            matcher = {
                (i["line_code"], i["item_code"])
                for i in self.items
                if ui_bulk.item_matches_bulk_filter(i, state)
            }
            fast = {
                (i["line_code"], i["item_code"])
                for i in ui_bulk.filtered_candidate_items(self.app, state)
            }
            self.assertEqual(
                matcher, fast,
                f"matcher/fast-path drift for item_status={item_status}: "
                f"matcher={len(matcher)} fast={len(fast)}",
            )


if __name__ == "__main__":
    unittest.main()
