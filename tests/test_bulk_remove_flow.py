import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bulk_remove_flow


class BulkRemoveFlowTests(unittest.TestCase):
    def test_remove_filtered_rows_updates_payload_and_history_once(self):
        events = []
        app = SimpleNamespace(
            filtered_items=[
                {"item_code": "A"},
                {"item_code": "B"},
                {"item_code": "C"},
            ],
            last_removed_bulk_items=[],
            last_protected_bulk_items=[],
            _capture_bulk_history_state=lambda capture_spec=None: {"before": True, "capture_spec": capture_spec},
            _finalize_bulk_history_action=lambda label, before, capture_spec=None: events.append((label, before, capture_spec)),
        )

        removed = bulk_remove_flow.remove_filtered_rows(
            app,
            [2, 1, 1],
            lambda value: dict(value),
            history_label="remove:selected_rows",
        )

        self.assertEqual(app.filtered_items, [{"item_code": "A"}])
        self.assertEqual(removed, [(2, {"item_code": "C"}), (1, {"item_code": "B"})])
        self.assertEqual(app.last_removed_bulk_items, removed)
        self.assertEqual(
            events,
            [(
                "remove:selected_rows",
                {
                    "before": True,
                    "capture_spec": {
                        "inventory_lookup": False,
                        "qoh_adjustments": False,
                        "order_rules": False,
                        "vendor_codes_used": False,
                        "last_removed_bulk_items": True,
                        "filtered_items_row_ids": (),
                        "changed_columns": (),
                    },
                },
                {
                    "inventory_lookup": False,
                    "qoh_adjustments": False,
                    "order_rules": False,
                    "vendor_codes_used": False,
                    "last_removed_bulk_items": True,
                    "filtered_items_row_ids": (),
                    "changed_columns": (),
                },
            )],
        )

    def test_remove_filtered_rows_invalidates_bulk_row_index(self):
        item_a = {"line_code": "AER-", "item_code": "A"}
        item_b = {"line_code": "AER-", "item_code": "B"}
        app = SimpleNamespace(
            filtered_items=[item_a, item_b],
            last_removed_bulk_items=[],
            last_protected_bulk_items=[],
            _capture_bulk_history_state=lambda: {"before": True},
            _finalize_bulk_history_action=lambda label, before: None,
            _bulk_row_index_generation=0,
            _bulk_row_index_cache={"generation": 0, "by_row_id": {}, "by_key": {}},
            _bulk_row_render_cache={
                "[\"AER-\",\"A\"]": (("sig",), ("row",)),
                "[\"AER-\",\"B\"]": (("sig",), ("row",)),
            },
        )

        bulk_remove_flow.remove_filtered_rows(
            app,
            [1],
            lambda value: dict(value),
            history_label="remove:selected_rows",
        )

        self.assertIsNone(app._bulk_row_index_cache)
        self.assertEqual(app._bulk_row_index_generation, 1)
        self.assertEqual(list(app._bulk_row_render_cache.keys()), ["[\"AER-\",\"A\"]"])

    def test_remove_filtered_rows_skips_history_when_nothing_removed(self):
        events = []
        app = SimpleNamespace(
            filtered_items=[{"item_code": "A"}],
            last_removed_bulk_items=[],
            last_protected_bulk_items=[],
            _capture_bulk_history_state=lambda: {"before": True},
            _finalize_bulk_history_action=lambda label, before: events.append((label, before)),
        )

        removed = bulk_remove_flow.remove_filtered_rows(
            app,
            [9],
            lambda value: dict(value),
            history_label="remove:selected_rows",
        )

        self.assertEqual(removed, [])
        self.assertEqual(app.filtered_items, [{"item_code": "A"}])
        self.assertEqual(app.last_removed_bulk_items, [])
        self.assertEqual(events, [])

    def test_remove_filtered_rows_skips_protected_not_needed_candidates(self):
        events = []
        app = SimpleNamespace(
            filtered_items=[
                {"item_code": "A", "candidate_preserved_reason": "below_current_min"},
                {"item_code": "B"},
            ],
            last_removed_bulk_items=[],
            last_protected_bulk_items=[],
            _capture_bulk_history_state=lambda capture_spec=None: {"before": True, "capture_spec": capture_spec},
            _finalize_bulk_history_action=lambda label, before, capture_spec=None: events.append((label, before, capture_spec)),
            _is_bulk_removal_protected=lambda item, history_label="": (
                bool(item.get("candidate_preserved_reason")) and str(history_label).startswith("remove:not_needed"),
                "candidate_preserved:below_current_min" if item.get("candidate_preserved_reason") else "",
            ),
        )

        removed = bulk_remove_flow.remove_filtered_rows(
            app,
            [1, 0],
            lambda value: dict(value),
            history_label="remove:not_needed:filtered",
        )

        self.assertEqual(app.filtered_items, [{"item_code": "A", "candidate_preserved_reason": "below_current_min"}])
        self.assertEqual(removed, [(1, {"item_code": "B"})])
        self.assertEqual(
            app.last_protected_bulk_items,
            [(0, {"item_code": "A", "candidate_preserved_reason": "below_current_min", "_removal_protection_reason": "candidate_preserved:below_current_min"})],
        )
        self.assertEqual(len(events), 1)

    def test_remove_filtered_rows_skips_index_when_expected_key_mismatches(self):
        app = SimpleNamespace(
            filtered_items=[
                {"line_code": "AER-", "item_code": "A"},
                {"line_code": "AER-", "item_code": "B"},
                {"line_code": "AER-", "item_code": "C"},
            ],
            last_removed_bulk_items=[],
            last_protected_bulk_items=[],
            _capture_bulk_history_state=lambda capture_spec=None: {},
            _finalize_bulk_history_action=lambda label, before, capture_spec=None: None,
        )

        # Index 1 is "B" but we claim it should be "Z" — mismatch, so skip it.
        removed = bulk_remove_flow.remove_filtered_rows(
            app,
            [2, 1, 0],
            lambda value: dict(value),
            history_label="remove:selected_rows",
            expected_keys={2: ("AER-", "C"), 1: ("AER-", "Z"), 0: ("AER-", "A")},
        )

        # Only indices 2 (C) and 0 (A) matched; index 1 (B vs expected Z) was skipped.
        removed_items = [item["item_code"] for _idx, item in removed]
        self.assertIn("C", removed_items)
        self.assertIn("A", removed_items)
        self.assertNotIn("B", removed_items)
        self.assertEqual(app.filtered_items, [{"line_code": "AER-", "item_code": "B"}])

    def test_remove_filtered_rows_passes_when_expected_keys_all_match(self):
        app = SimpleNamespace(
            filtered_items=[
                {"line_code": "AER-", "item_code": "A"},
                {"line_code": "AER-", "item_code": "B"},
            ],
            last_removed_bulk_items=[],
            last_protected_bulk_items=[],
            _capture_bulk_history_state=lambda capture_spec=None: {},
            _finalize_bulk_history_action=lambda label, before, capture_spec=None: None,
        )

        removed = bulk_remove_flow.remove_filtered_rows(
            app,
            [1, 0],
            lambda value: dict(value),
            history_label="remove:selected_rows",
            expected_keys={0: ("AER-", "A"), 1: ("AER-", "B")},
        )

        self.assertEqual(len(removed), 2)
        self.assertEqual(app.filtered_items, [])

    def test_remove_filtered_rows_skips_protection_for_suspense_carry(self):
        app = SimpleNamespace(
            filtered_items=[
                {"line_code": "AER-", "item_code": "A", "suspense_carry_qty": 2},
                {"line_code": "AER-", "item_code": "B"},
            ],
            last_removed_bulk_items=[],
            last_protected_bulk_items=[],
            _capture_bulk_history_state=lambda capture_spec=None: {},
            _finalize_bulk_history_action=lambda label, before, capture_spec=None: None,
            _is_bulk_removal_protected=lambda item, history_label="": (
                (item.get("suspense_carry_qty", 0) or 0) > 0
                and str(history_label).startswith("remove:not_needed"),
                "active_suspense_carry" if (item.get("suspense_carry_qty", 0) or 0) > 0 else "",
            ),
        )

        removed = bulk_remove_flow.remove_filtered_rows(
            app,
            [1, 0],
            lambda value: dict(value),
            history_label="remove:not_needed:filtered",
        )

        # Item A (suspense carry) is protected; only B is removed.
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0][1]["item_code"], "B")
        self.assertEqual(len(app.last_protected_bulk_items), 1)
        self.assertEqual(app.last_protected_bulk_items[0][1]["item_code"], "A")
        self.assertEqual(
            app.last_protected_bulk_items[0][1]["_removal_protection_reason"],
            "active_suspense_carry",
        )


    def test_no_op_removal_clears_stale_last_removed_payload(self):
        # Regression: when a call removes nothing (all indices out of range
        # or all candidates protected), prior last_removed_bulk_items used
        # to be left in place, so undo and status banners surfaced a stale
        # record from an earlier call.  Verify it's reset.
        prior = [(0, {"item_code": "PRIOR"})]
        app = SimpleNamespace(
            filtered_items=[{"item_code": "A"}],
            last_removed_bulk_items=list(prior),
            last_protected_bulk_items=[],
            _capture_bulk_history_state=lambda capture_spec=None: {"before": True},
            _finalize_bulk_history_action=lambda label, before, capture_spec=None: None,
        )

        removed = bulk_remove_flow.remove_filtered_rows(
            app,
            [9],  # out of range
            lambda value: dict(value),
            history_label="remove:selected_rows",
        )

        self.assertEqual(removed, [])
        self.assertEqual(app.last_removed_bulk_items, [])
        self.assertEqual(app.filtered_items, [{"item_code": "A"}])

    def test_skipped_payload_records_out_of_range_and_key_mismatch(self):
        # Regression: silently-dropped indices left callers unable to tell
        # the user that part of their request didn't apply.  The flow now
        # records each skip on app.last_skipped_bulk_removals.
        app = SimpleNamespace(
            filtered_items=[
                {"line_code": "AER-", "item_code": "A"},
                {"line_code": "AER-", "item_code": "B"},
            ],
            last_removed_bulk_items=[],
            last_protected_bulk_items=[],
            _capture_bulk_history_state=lambda capture_spec=None: {},
            _finalize_bulk_history_action=lambda label, before, capture_spec=None: None,
        )

        bulk_remove_flow.remove_filtered_rows(
            app,
            [9, 1, 0],  # 9 is OOR, 1 is mismatch, 0 matches
            lambda value: dict(value),
            history_label="remove:selected_rows",
            expected_keys={1: ("AER-", "ZZZ"), 0: ("AER-", "A")},
        )

        skipped = sorted(app.last_skipped_bulk_removals)
        self.assertEqual(skipped, [(1, "key_mismatch"), (9, "out_of_range")])
        self.assertEqual(app.filtered_items, [{"line_code": "AER-", "item_code": "B"}])


if __name__ == "__main__":
    unittest.main()
