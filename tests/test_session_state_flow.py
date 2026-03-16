import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import session_state_flow
import ui_bulk


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

    def test_finalize_bulk_history_action_stores_capture_spec_on_new_entry(self):
        fake_app = SimpleNamespace(
            bulk_undo_stack=[],
            bulk_redo_stack=[],
            _capture_bulk_history_state=lambda capture_spec=None: {"n": 2, "capture_spec": capture_spec},
        )
        capture_spec = session_state_flow.bulk_history_capture_spec_for_columns(("qoh",))

        changed = session_state_flow.finalize_bulk_history_action(
            fake_app,
            "edit:qoh",
            {"n": 1, "capture_spec": capture_spec},
            max_bulk_history=5,
            capture_spec=capture_spec,
        )

        self.assertTrue(changed)
        self.assertEqual(fake_app.bulk_undo_stack[0]["_capture_spec"], capture_spec)

    def test_capture_bulk_history_state_respects_column_capture_spec(self):
        fake_app = SimpleNamespace(
            filtered_items=[{"item_code": "ABC123"}],
            inventory_lookup={("AER-", "ABC123"): {"qoh": 4}},
            qoh_adjustments={("AER-", "ABC123"): {"new": 4}},
            order_rules={"AER-:ABC123": {"pack_size": 6}},
            vendor_codes_used=["MOTION"],
            last_removed_bulk_items=[(1, {"item_code": "OLD"})],
        )

        state = session_state_flow.capture_bulk_history_state(
            fake_app,
            capture_spec=session_state_flow.bulk_history_capture_spec_for_columns(("final_qty",)),
        )

        self.assertEqual(state, {
            "filtered_items": [{"item_code": "ABC123"}],
            "last_removed_bulk_items": [(1, {"item_code": "OLD"})],
        })

    def test_capture_bulk_history_state_uses_row_scoped_filtered_item_snapshots(self):
        item_a = {"line_code": "AER-", "item_code": "A", "vendor": ""}
        item_b = {"line_code": "MOT-", "item_code": "B", "vendor": "MOTION"}
        fake_app = SimpleNamespace(
            filtered_items=[item_a, item_b],
            inventory_lookup={},
            qoh_adjustments={},
            order_rules={},
            vendor_codes_used=[],
            last_removed_bulk_items=[],
        )

        state = session_state_flow.capture_bulk_history_state(
            fake_app,
            capture_spec=session_state_flow.bulk_history_capture_spec_for_columns(
                ("vendor",),
                row_ids=(ui_bulk.bulk_row_id(item_b),),
            ),
        )

        self.assertEqual(
            state,
            {
                "filtered_items_rows": [(ui_bulk.bulk_row_id(item_b), {"line_code": "MOT-", "item_code": "B", "vendor": "MOTION"})],
                "vendor_codes_used": [],
                "last_removed_bulk_items": [],
            },
        )

    def test_capture_bulk_history_state_uses_row_scoped_mapping_entries_for_qoh_edits(self):
        item_a = {"line_code": "AER-", "item_code": "A", "vendor": ""}
        item_b = {"line_code": "MOT-", "item_code": "B", "vendor": ""}
        fake_app = SimpleNamespace(
            filtered_items=[item_a, item_b],
            inventory_lookup={
                ("AER-", "A"): {"qoh": 1},
                ("MOT-", "B"): {"qoh": 2},
            },
            qoh_adjustments={
                ("MOT-", "B"): {"new": 2},
            },
            order_rules={},
            vendor_codes_used=[],
            last_removed_bulk_items=[],
        )

        state = session_state_flow.capture_bulk_history_state(
            fake_app,
            capture_spec=session_state_flow.bulk_history_capture_spec_for_columns(
                ("qoh",),
                row_ids=(ui_bulk.bulk_row_id(item_b),),
            ),
        )

        self.assertEqual(
            state,
            {
                "filtered_items_rows": [(ui_bulk.bulk_row_id(item_b), {"line_code": "MOT-", "item_code": "B", "vendor": ""})],
                "inventory_lookup_entries": [(("MOT-", "B"), True, {"qoh": 2})],
                "qoh_adjustments_entries": [(("MOT-", "B"), True, {"new": 2})],
                "last_removed_bulk_items": [],
            },
        )

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

    def test_restore_bulk_history_state_preserves_omitted_state_fields(self):
        events = []
        fake_app = SimpleNamespace(
            filtered_items=[],
            inventory_lookup={("KEEP",): {"qoh": 9}},
            qoh_adjustments={("KEEP",): {"new": 9}},
            order_rules={"KEEP": {"pack_size": 4}},
            vendor_codes_used=["KEEPVENDOR"],
            _loaded_order_rules={},
            _loaded_vendor_codes=[],
            last_removed_bulk_items=[("keep", {"item_code": "OLD"})],
            bulk_sheet=None,
            _refresh_vendor_inputs=lambda: events.append("vendors"),
            _apply_bulk_filter=lambda: events.append("bulk"),
            _update_bulk_summary=lambda: events.append("summary"),
            _update_bulk_cell_status=lambda: events.append("status"),
        )

        session_state_flow.restore_bulk_history_state(
            fake_app,
            {
                "filtered_items": [{"item_code": "ABC123"}],
            },
        )

        self.assertEqual(fake_app.filtered_items, [{"item_code": "ABC123"}])
        self.assertEqual(fake_app.inventory_lookup, {("KEEP",): {"qoh": 9}})
        self.assertEqual(fake_app.qoh_adjustments, {("KEEP",): {"new": 9}})
        self.assertEqual(fake_app.order_rules, {"KEEP": {"pack_size": 4}})
        self.assertEqual(fake_app.vendor_codes_used, ["KEEPVENDOR"])
        self.assertEqual(fake_app.last_removed_bulk_items, [("keep", {"item_code": "OLD"})])
        self.assertEqual(events, ["vendors", "bulk", "summary", "status"])

    def test_restore_bulk_history_state_applies_row_scoped_filtered_item_snapshots(self):
        events = []
        item_a = {"line_code": "AER-", "item_code": "A", "vendor": ""}
        item_b = {"line_code": "MOT-", "item_code": "B", "vendor": "SOURCE"}
        filtered_items = [item_a, item_b]
        fake_app = SimpleNamespace(
            filtered_items=filtered_items,
            inventory_lookup={},
            qoh_adjustments={},
            order_rules={},
            vendor_codes_used=[],
            _loaded_order_rules={},
            _loaded_vendor_codes=[],
            last_removed_bulk_items=[],
            _bulk_row_render_cache={
                ui_bulk.bulk_row_id(item_a): (("sig-a",), ("row-a",)),
                ui_bulk.bulk_row_id(item_b): (("sig-b",), ("row-b",)),
            },
            bulk_sheet=None,
            _refresh_vendor_inputs=lambda: events.append("vendors"),
            _apply_bulk_filter=lambda: events.append("bulk"),
            _update_bulk_summary=lambda: events.append("summary"),
            _update_bulk_cell_status=lambda: events.append("status"),
        )

        session_state_flow.restore_bulk_history_state(
            fake_app,
            {
                "filtered_items_rows": [
                    (ui_bulk.bulk_row_id(item_b), {"line_code": "MOT-", "item_code": "B", "vendor": "MOTION"})
                ],
            },
        )

        self.assertIs(fake_app.filtered_items, filtered_items)
        self.assertEqual(fake_app.filtered_items, [item_a, {"line_code": "MOT-", "item_code": "B", "vendor": "MOTION"}])
        self.assertEqual(list(fake_app._bulk_row_render_cache.keys()), [ui_bulk.bulk_row_id(item_a)])
        self.assertEqual(events, ["vendors", "bulk", "summary", "status"])

    def test_restore_bulk_history_state_applies_row_scoped_mapping_entries(self):
        events = []
        item_a = {"line_code": "AER-", "item_code": "A", "vendor": ""}
        item_b = {"line_code": "MOT-", "item_code": "B", "vendor": ""}
        inventory_lookup = {("AER-", "A"): {"qoh": 1}, ("MOT-", "B"): {"qoh": 9}}
        qoh_adjustments = {("MOT-", "B"): {"new": 9}}
        order_rules = {"AER-:A": {"pack_size": 4}, "MOT-:B": {"pack_size": 10}}
        fake_app = SimpleNamespace(
            filtered_items=[item_a, item_b],
            inventory_lookup=inventory_lookup,
            qoh_adjustments=qoh_adjustments,
            order_rules=order_rules,
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
                "filtered_items_rows": [
                    (ui_bulk.bulk_row_id(item_b), {"line_code": "MOT-", "item_code": "B", "vendor": ""})
                ],
                "inventory_lookup_entries": [(("MOT-", "B"), True, {"qoh": 2})],
                "qoh_adjustments_entries": [(("MOT-", "B"), False, None)],
                "order_rules_entries": [("MOT-:B", False, None)],
            },
        )

        self.assertIs(fake_app.inventory_lookup, inventory_lookup)
        self.assertIs(fake_app.qoh_adjustments, qoh_adjustments)
        self.assertIs(fake_app.order_rules, order_rules)
        self.assertEqual(fake_app.inventory_lookup, {("AER-", "A"): {"qoh": 1}, ("MOT-", "B"): {"qoh": 2}})
        self.assertEqual(fake_app.qoh_adjustments, {})
        self.assertEqual(fake_app.order_rules, {"AER-:A": {"pack_size": 4}})
        self.assertEqual(events, ["vendors", "bulk", "summary", "status"])

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
