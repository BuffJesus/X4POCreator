import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import session_state_flow


class SessionStateFlowTests(unittest.TestCase):
    def test_is_bulk_removal_history_label_detects_remove_prefix(self):
        self.assertTrue(session_state_flow.is_bulk_removal_history_label("remove:selected_rows"))
        self.assertTrue(session_state_flow.is_bulk_removal_history_label("remove:not_needed:screen"))
        self.assertFalse(session_state_flow.is_bulk_removal_history_label("edit:pack_size"))

    def test_finalize_bulk_history_action_trims_undo_stack_and_clears_redo(self):
        fake_app = SimpleNamespace(
            bulk_undo_stack=[
                {"label": "1", "before": {"n": 1}, "after": {"n": 2}},
                {"label": "2", "before": {"n": 2}, "after": {"n": 3}},
            ],
            bulk_redo_stack=[{"label": "redo"}],
            _capture_bulk_history_state=lambda: {"n": 4},
        )

        changed = session_state_flow.finalize_bulk_history_action(
            fake_app,
            "3",
            {"n": 3},
            max_bulk_history=2,
        )

        self.assertTrue(changed)
        self.assertEqual([entry["label"] for entry in fake_app.bulk_undo_stack], ["2", "3"])
        self.assertEqual(fake_app.bulk_redo_stack, [])

    def test_finalize_bulk_history_action_coalesces_matching_top_entry(self):
        fake_app = SimpleNamespace(
            bulk_undo_stack=[
                {
                    "label": "sheet_edit:pack_size",
                    "before": {"n": 1},
                    "after": {"n": 2},
                    "_coalesce_key": ("kind", "sheet_edit"),
                }
            ],
            bulk_redo_stack=[{"label": "redo"}],
            _capture_bulk_history_state=lambda: {"n": 3},
        )

        changed = session_state_flow.finalize_bulk_history_action(
            fake_app,
            "sheet_edit:pack_size",
            {"n": 2},
            max_bulk_history=5,
            coalesce_key=("kind", "sheet_edit"),
        )

        self.assertTrue(changed)
        self.assertEqual(len(fake_app.bulk_undo_stack), 1)
        self.assertEqual(fake_app.bulk_undo_stack[0]["before"], {"n": 1})
        self.assertEqual(fake_app.bulk_undo_stack[0]["after"], {"n": 3})
        self.assertEqual(fake_app.bulk_redo_stack, [])

    def test_restore_bulk_history_state_rehydrates_state_and_refreshes_views(self):
        events = []

        class BulkSheet:
            def clear_selection(self):
                events.append("clear")

        fake_app = SimpleNamespace(
            filtered_items=[],
            inventory_lookup={},
            qoh_adjustments={},
            order_rules={},
            vendor_codes_used=[],
            _loaded_order_rules={"KEEP": {"pack_size": 4}},
            _loaded_vendor_codes=["KEEPVENDOR"],
            last_removed_bulk_items=[],
            bulk_sheet=BulkSheet(),
            _refresh_vendor_inputs=lambda: events.append("vendors"),
            _apply_bulk_filter=lambda: events.append("bulk"),
            _update_bulk_summary=lambda: events.append("summary"),
            _update_bulk_cell_status=lambda: events.append("status"),
        )

        session_state_flow.restore_bulk_history_state(
            fake_app,
            {
                "filtered_items": [{"item_code": "ABC123"}],
                "inventory_lookup": {("AER-", "ABC123"): {"qoh": 4}},
                "qoh_adjustments": {("AER-", "ABC123"): {"new": 4}},
                "order_rules": {"AER-:ABC123": {"pack_size": 6}},
                "vendor_codes_used": ["MOTION"],
                "last_removed_bulk_items": [{"item_code": "OLD"}],
            },
        )

        self.assertEqual(fake_app.filtered_items, [{"item_code": "ABC123"}])
        self.assertEqual(fake_app.vendor_codes_used, ["MOTION"])
        self.assertEqual(fake_app.last_removed_bulk_items, [{"item_code": "OLD"}])
        self.assertEqual(fake_app._loaded_order_rules, {"KEEP": {"pack_size": 4}})
        self.assertEqual(fake_app._loaded_vendor_codes, ["KEEPVENDOR"])
        self.assertEqual(events, ["vendors", "clear", "bulk", "summary", "status"])

    def test_capture_bulk_history_state_does_not_deepcopy_last_removed_bulk_items(self):
        class NoDeepcopy:
            def __deepcopy__(self, memo):
                raise AssertionError("last_removed_bulk_items should not be deep-copied")

        removed_item = {"item_code": "OLD", "payload": NoDeepcopy()}
        fake_app = SimpleNamespace(
            filtered_items=[{"item_code": "ABC123"}],
            inventory_lookup={},
            qoh_adjustments={},
            order_rules={},
            vendor_codes_used=[],
            _loaded_order_rules={},
            _loaded_vendor_codes=[],
            last_removed_bulk_items=[(3, removed_item)],
        )

        state = session_state_flow.capture_bulk_history_state(fake_app)

        self.assertEqual(state["last_removed_bulk_items"], [(3, removed_item)])
        self.assertIsNot(state["last_removed_bulk_items"], fake_app.last_removed_bulk_items)
        self.assertNotIn("_loaded_order_rules", state)
        self.assertNotIn("_loaded_vendor_codes", state)

    def test_capture_bulk_history_state_strips_runtime_bulk_item_cache_fields(self):
        filtered_item = {
            "line_code": "AER-",
            "item_code": "ABC123",
            "_bulk_row_id": "[\"AER-\",\"ABC123\"]",
            "_bulk_row_id_key": ("AER-", "ABC123"),
            "vendor": "MOTION",
        }
        fake_app = SimpleNamespace(
            filtered_items=[filtered_item],
            inventory_lookup={},
            qoh_adjustments={},
            order_rules={},
            vendor_codes_used=[],
            _loaded_order_rules={},
            _loaded_vendor_codes=[],
            last_removed_bulk_items=[],
        )

        state = session_state_flow.capture_bulk_history_state(fake_app)

        self.assertEqual(state["filtered_items"], [{"line_code": "AER-", "item_code": "ABC123", "vendor": "MOTION"}])

    def test_restore_bulk_history_state_does_not_rehydrate_runtime_bulk_item_cache_fields(self):
        events = []
        fake_app = SimpleNamespace(
            filtered_items=[],
            inventory_lookup={},
            qoh_adjustments={},
            order_rules={},
            vendor_codes_used=[],
            _loaded_order_rules={},
            _loaded_vendor_codes=[],
            last_removed_bulk_items=[],
            bulk_sheet=None,
            _refresh_vendor_inputs=lambda: events.append("vendors"),
            _apply_bulk_filter=lambda: events.append("bulk"),
            _update_bulk_summary=lambda: events.append("summary"),
            _update_bulk_cell_status=lambda: events.append("status"),
        )

        session_state_flow.restore_bulk_history_state(
            fake_app,
            {
                "filtered_items": [{
                    "line_code": "AER-",
                    "item_code": "ABC123",
                    "_bulk_row_id": "[\"AER-\",\"ABC123\"]",
                    "_bulk_row_id_key": ("AER-", "ABC123"),
                    "vendor": "MOTION",
                }],
            },
        )

        self.assertEqual(fake_app.filtered_items, [{"line_code": "AER-", "item_code": "ABC123", "vendor": "MOTION"}])

    def test_ignore_items_by_keys_removes_items_and_refreshes_review_when_present(self):
        events = []
        fake_app = SimpleNamespace(
            ignored_item_keys=set(),
            filtered_items=[{"line_code": "AER-", "item_code": "GH781-4"}],
            assigned_items=[{"line_code": "AER-", "item_code": "GH781-4"}],
            individual_items=[{"line_code": "MOT-", "item_code": "ABC123"}],
            _save_ignored_item_keys=lambda: events.append("save"),
            _apply_bulk_filter=lambda: events.append("bulk"),
            _update_bulk_summary=lambda: events.append("summary"),
            _populate_review_tab=lambda: events.append("review"),
            tree=object(),
        )
        fake_app._ignore_key = session_state_flow.ignore_key

        removed = session_state_flow.ignore_items_by_keys(fake_app, {" AER-:GH781-4 "})

        self.assertEqual(removed, 1)
        self.assertEqual(fake_app.filtered_items, [])
        self.assertEqual(fake_app.assigned_items, [])
        self.assertEqual(fake_app.individual_items, [{"line_code": "MOT-", "item_code": "ABC123"}])
        self.assertIn("AER-:GH781-4", fake_app.ignored_item_keys)
        self.assertEqual(events, ["save", "bulk", "summary", "review"])


if __name__ == "__main__":
    unittest.main()
