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

    def test_finalize_bulk_history_action_recompacts_coalesced_entry_to_net_field_change(self):
        fake_app = SimpleNamespace(
            bulk_undo_stack=[
                {
                    "label": "edit:vendor",
                    "before": {"filtered_items_row_patches": [("0", [("vendor", True, "")])]},
                    "after": {"filtered_items_row_patches": [("0", [("vendor", True, "MOTION")])]},
                    "_coalesce_key": ("kind", "sheet_edit"),
                }
            ],
            bulk_redo_stack=[{"label": "redo"}],
            _capture_bulk_history_state=lambda: {
                "filtered_items_rows": [("0", {"vendor": "SOURCE"})],
            },
        )

        changed = session_state_flow.finalize_bulk_history_action(
            fake_app,
            "edit:vendor",
            {"filtered_items_rows": [("0", {"vendor": "MOTION"})]},
            max_bulk_history=5,
            coalesce_key=("kind", "sheet_edit"),
        )

        self.assertTrue(changed)
        self.assertEqual(len(fake_app.bulk_undo_stack), 1)
        self.assertEqual(
            fake_app.bulk_undo_stack[0]["before"],
            {"filtered_items_row_patches": [("0", [("vendor", True, "")])]},
        )
        self.assertEqual(
            fake_app.bulk_undo_stack[0]["after"],
            {"filtered_items_row_patches": [("0", [("vendor", True, "SOURCE")])]},
        )
        self.assertEqual(fake_app.bulk_redo_stack, [])

    def test_finalize_bulk_history_action_drops_coalesced_entry_when_net_state_returns_to_start(self):
        fake_app = SimpleNamespace(
            bulk_undo_stack=[
                {
                    "label": "edit:vendor",
                    "before": {"filtered_items_row_patches": [("0", [("vendor", True, "")])]},
                    "after": {"filtered_items_row_patches": [("0", [("vendor", True, "MOTION")])]},
                    "_coalesce_key": ("kind", "sheet_edit"),
                }
            ],
            bulk_redo_stack=[{"label": "redo"}],
            _capture_bulk_history_state=lambda: {
                "filtered_items_rows": [("0", {"vendor": ""})],
            },
        )

        changed = session_state_flow.finalize_bulk_history_action(
            fake_app,
            "edit:vendor",
            {"filtered_items_rows": [("0", {"vendor": "MOTION"})]},
            max_bulk_history=5,
            coalesce_key=("kind", "sheet_edit"),
        )

        self.assertTrue(changed)
        self.assertEqual(fake_app.bulk_undo_stack, [])
        self.assertEqual(fake_app.bulk_redo_stack, [])

    def test_finalize_bulk_history_action_coalesces_when_previous_after_and_before_are_equivalent_in_mixed_shapes(self):
        fake_app = SimpleNamespace(
            bulk_undo_stack=[
                {
                    "label": "edit:vendor",
                    "before": {"filtered_items_row_patches": [("0", [("vendor", True, "")])]},
                    "after": {"filtered_items_rows": [("0", {"vendor": "MOTION", "why": "keep"})]},
                    "_coalesce_key": ("kind", "sheet_edit"),
                }
            ],
            bulk_redo_stack=[{"label": "redo"}],
            _capture_bulk_history_state=lambda: {
                "filtered_items_rows": [("0", {"vendor": "SOURCE", "why": "keep"})],
            },
        )

        changed = session_state_flow.finalize_bulk_history_action(
            fake_app,
            "edit:vendor",
            {"filtered_items_row_patches": [("0", [("vendor", True, "MOTION"), ("why", True, "keep")])]},
            max_bulk_history=5,
            coalesce_key=("kind", "sheet_edit"),
        )

        self.assertTrue(changed)
        self.assertEqual(len(fake_app.bulk_undo_stack), 1)
        self.assertEqual(
            fake_app.bulk_undo_stack[0]["before"],
            {"filtered_items_row_patches": [("0", [("vendor", True, "")])]},
        )
        self.assertEqual(
            fake_app.bulk_undo_stack[0]["after"],
            {"filtered_items_row_patches": [("0", [("vendor", True, "SOURCE")])]},
        )
        self.assertEqual(fake_app.bulk_redo_stack, [])

    def test_bulk_history_states_equivalent_matches_mixed_mapping_shapes(self):
        self.assertTrue(
            session_state_flow.bulk_history_states_equivalent(
                {"inventory_lookup_entries": [(("AER-", "A"), True, {"qoh": 5, "supplier": "SOURCE"})]},
                {"inventory_lookup_entry_patches": [(("AER-", "A"), [("qoh", True, 5)])]},
            )
        )

    def test_compact_bulk_history_state_pair_normalizes_full_rows_and_row_patches(self):
        before_state, after_state = session_state_flow.compact_bulk_history_state_pair(
            {"filtered_items_rows": [("0", {"vendor": "", "why": "keep"})]},
            {"filtered_items_row_patches": [("0", [("vendor", True, "MOTION")])]},
        )

        self.assertEqual(
            before_state,
            {"filtered_items_row_patches": [("0", [("vendor", True, "")])]},
        )
        self.assertEqual(
            after_state,
            {"filtered_items_row_patches": [("0", [("vendor", True, "MOTION")])]},
        )

    def test_compact_bulk_history_state_pair_normalizes_full_mapping_entries_and_entry_patches(self):
        before_state, after_state = session_state_flow.compact_bulk_history_state_pair(
            {"inventory_lookup_entries": [(("AER-", "A"), True, {"qoh": 5, "supplier": "SOURCE"})]},
            {"inventory_lookup_entry_patches": [(("AER-", "A"), [("qoh", True, 7)])]},
        )

        self.assertEqual(
            before_state,
            {"inventory_lookup_entry_patches": [(("AER-", "A"), [("qoh", True, 5)])]},
        )
        self.assertEqual(
            after_state,
            {"inventory_lookup_entry_patches": [(("AER-", "A"), [("qoh", True, 7)])]},
        )

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

    def test_finalize_bulk_history_action_prunes_unchanged_vendor_codes_from_entry(self):
        capture_spec = session_state_flow.bulk_history_capture_spec_for_columns(("vendor",), row_ids=("0",), include_vendor_codes=True)
        fake_app = SimpleNamespace(
            bulk_undo_stack=[],
            bulk_redo_stack=[],
            _capture_bulk_history_state=lambda capture_spec=None: {
                "filtered_items_rows": [("0", {"vendor": "MOTION"})],
                "vendor_codes_used": ["MOTION"],
            },
        )

        changed = session_state_flow.finalize_bulk_history_action(
            fake_app,
            "edit:vendor",
            {
                "filtered_items_rows": [("0", {"vendor": ""})],
                "vendor_codes_used": ["MOTION"],
            },
            max_bulk_history=5,
            capture_spec=capture_spec,
        )

        self.assertTrue(changed)
        self.assertNotIn("vendor_codes_used", fake_app.bulk_undo_stack[0]["before"])
        self.assertNotIn("vendor_codes_used", fake_app.bulk_undo_stack[0]["after"])

    def test_finalize_bulk_history_action_prunes_unchanged_partial_mapping_entries_from_entry(self):
        capture_spec = session_state_flow.bulk_history_capture_spec_for_columns(("qoh",), row_ids=("0",))
        fake_app = SimpleNamespace(
            bulk_undo_stack=[],
            bulk_redo_stack=[],
            _capture_bulk_history_state=lambda capture_spec=None: {
                "filtered_items_rows": [("0", {"line_code": "AER-", "item_code": "A", "vendor": ""})],
                "inventory_lookup_entries": [(("AER-", "A"), True, {"qoh": 7})],
                "qoh_adjustments_entries": [(("AER-", "A"), False, None)],
            },
        )

        changed = session_state_flow.finalize_bulk_history_action(
            fake_app,
            "edit:qoh",
            {
                "filtered_items_rows": [("0", {"line_code": "AER-", "item_code": "A", "vendor": "MOTION"})],
                "inventory_lookup_entries": [(("AER-", "A"), True, {"qoh": 7})],
                "qoh_adjustments_entries": [(("AER-", "A"), False, None)],
            },
            max_bulk_history=5,
            capture_spec=capture_spec,
        )

        self.assertTrue(changed)
        self.assertNotIn("inventory_lookup_entries", fake_app.bulk_undo_stack[0]["before"])
        self.assertNotIn("inventory_lookup_entries", fake_app.bulk_undo_stack[0]["after"])
        self.assertNotIn("qoh_adjustments_entries", fake_app.bulk_undo_stack[0]["before"])
        self.assertNotIn("qoh_adjustments_entries", fake_app.bulk_undo_stack[0]["after"])

    def test_finalize_bulk_history_action_prunes_only_unchanged_row_scoped_entries(self):
        capture_spec = session_state_flow.bulk_history_capture_spec_for_columns(("vendor",), row_ids=("0", "1"))
        fake_app = SimpleNamespace(
            bulk_undo_stack=[],
            bulk_redo_stack=[],
            _capture_bulk_history_state=lambda capture_spec=None: {
                "filtered_items_rows": [
                    ("0", {"vendor": "MOTION"}),
                    ("1", {"vendor": "SOURCE"}),
                ],
            },
        )

        changed = session_state_flow.finalize_bulk_history_action(
            fake_app,
            "edit:vendor",
            {
                "filtered_items_rows": [
                    ("0", {"vendor": ""}),
                    ("1", {"vendor": "SOURCE"}),
                ],
            },
            max_bulk_history=5,
            capture_spec=capture_spec,
        )

        self.assertTrue(changed)
        self.assertEqual(fake_app.bulk_undo_stack[0]["before"]["filtered_items_row_patches"], [("0", [("vendor", True, "")])])
        self.assertEqual(fake_app.bulk_undo_stack[0]["after"]["filtered_items_row_patches"], [("0", [("vendor", True, "MOTION")])])

    def test_finalize_bulk_history_action_prunes_only_unchanged_vendor_code_entries(self):
        capture_spec = session_state_flow.bulk_history_capture_spec_for_columns(("vendor",), row_ids=("0", "1"), include_vendor_codes=True)
        fake_app = SimpleNamespace(
            bulk_undo_stack=[],
            bulk_redo_stack=[],
            _capture_bulk_history_state=lambda capture_spec=None: {
                "filtered_items_rows": [
                    ("0", {"vendor": "MOTION"}),
                    ("1", {"vendor": "SOURCE"}),
                ],
                "vendor_codes_used_entries": [
                    ("MOTION", True, 0),
                    ("SOURCE", True, 1),
                ],
            },
        )

        changed = session_state_flow.finalize_bulk_history_action(
            fake_app,
            "edit:vendor",
            {
                "filtered_items_rows": [
                    ("0", {"vendor": ""}),
                    ("1", {"vendor": "SOURCE"}),
                ],
                "vendor_codes_used_entries": [
                    ("MOTION", False, None),
                    ("SOURCE", True, 1),
                ],
            },
            max_bulk_history=5,
            capture_spec=capture_spec,
        )

        self.assertTrue(changed)
        self.assertEqual(fake_app.bulk_undo_stack[0]["before"]["vendor_codes_used_entries"], [("MOTION", False, None)])
        self.assertEqual(fake_app.bulk_undo_stack[0]["after"]["vendor_codes_used_entries"], [("MOTION", True, 0)])
        self.assertEqual(fake_app.bulk_undo_stack[0]["before"]["filtered_items_row_patches"], [("0", [("vendor", True, "")])])
        self.assertEqual(fake_app.bulk_undo_stack[0]["after"]["filtered_items_row_patches"], [("0", [("vendor", True, "MOTION")])])

    def test_finalize_bulk_history_action_prunes_only_unchanged_mapping_entries(self):
        capture_spec = session_state_flow.bulk_history_capture_spec_for_columns(("qoh",), row_ids=("0", "1"))
        fake_app = SimpleNamespace(
            bulk_undo_stack=[],
            bulk_redo_stack=[],
            _capture_bulk_history_state=lambda capture_spec=None: {
                "filtered_items_rows": [
                    ("0", {"line_code": "AER-", "item_code": "A", "qoh": 7}),
                    ("1", {"line_code": "MOT-", "item_code": "B", "qoh": 4}),
                ],
                "inventory_lookup_entries": [
                    (("AER-", "A"), True, {"qoh": 7}),
                    (("MOT-", "B"), True, {"qoh": 4}),
                ],
                "qoh_adjustments_entries": [
                    (("AER-", "A"), True, {"new": 7}),
                    (("MOT-", "B"), True, {"new": 4}),
                ],
            },
        )

        changed = session_state_flow.finalize_bulk_history_action(
            fake_app,
            "edit:qoh",
            {
                "filtered_items_rows": [
                    ("0", {"line_code": "AER-", "item_code": "A", "qoh": 5}),
                    ("1", {"line_code": "MOT-", "item_code": "B", "qoh": 4}),
                ],
                "inventory_lookup_entries": [
                    (("AER-", "A"), True, {"qoh": 5}),
                    (("MOT-", "B"), True, {"qoh": 4}),
                ],
                "qoh_adjustments_entries": [
                    (("AER-", "A"), True, {"new": 5}),
                    (("MOT-", "B"), True, {"new": 4}),
                ],
            },
            max_bulk_history=5,
            capture_spec=capture_spec,
        )

        self.assertTrue(changed)
        self.assertEqual(fake_app.bulk_undo_stack[0]["before"]["inventory_lookup_entry_patches"], [(("AER-", "A"), [("qoh", True, 5)])])
        self.assertEqual(fake_app.bulk_undo_stack[0]["after"]["inventory_lookup_entry_patches"], [(("AER-", "A"), [("qoh", True, 7)])])
        self.assertEqual(fake_app.bulk_undo_stack[0]["before"]["qoh_adjustments_entry_patches"], [(("AER-", "A"), [("new", True, 5)])])
        self.assertEqual(fake_app.bulk_undo_stack[0]["after"]["qoh_adjustments_entry_patches"], [(("AER-", "A"), [("new", True, 7)])])
        self.assertEqual(
            fake_app.bulk_undo_stack[0]["before"]["filtered_items_row_patches"],
            [("0", [("qoh", True, 5)])],
        )
        self.assertEqual(
            fake_app.bulk_undo_stack[0]["after"]["filtered_items_row_patches"],
            [("0", [("qoh", True, 7)])],
        )

    def test_finalize_bulk_history_action_compacts_mapping_entries_to_field_patches(self):
        capture_spec = session_state_flow.bulk_history_capture_spec_for_columns(("pack_size",), row_ids=("0",))
        fake_app = SimpleNamespace(
            bulk_undo_stack=[],
            bulk_redo_stack=[],
            _capture_bulk_history_state=lambda capture_spec=None: {
                "filtered_items_rows": [("0", {"line_code": "AER-", "item_code": "A", "pack_size": 6})],
                "order_rules_entries": [("AER-:A", True, {"pack_size": 6, "order_policy": "manual"})],
            },
        )

        changed = session_state_flow.finalize_bulk_history_action(
            fake_app,
            "edit:pack_size",
            {
                "filtered_items_rows": [("0", {"line_code": "AER-", "item_code": "A", "pack_size": 4})],
                "order_rules_entries": [("AER-:A", True, {"pack_size": 4, "order_policy": "manual"})],
            },
            max_bulk_history=5,
            capture_spec=capture_spec,
        )

        self.assertTrue(changed)
        self.assertEqual(
            fake_app.bulk_undo_stack[0]["before"]["order_rules_entry_patches"],
            [("AER-:A", [("pack_size", True, 4)])],
        )
        self.assertEqual(
            fake_app.bulk_undo_stack[0]["after"]["order_rules_entry_patches"],
            [("AER-:A", [("pack_size", True, 6)])],
        )
        self.assertNotIn("order_rules_entries", fake_app.bulk_undo_stack[0]["before"])
        self.assertNotIn("order_rules_entries", fake_app.bulk_undo_stack[0]["after"])

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
                "vendor_codes_used_entries": [("MOTION", False, None)],
                "last_removed_bulk_items": [],
            },
        )

    def test_capture_bulk_history_state_uses_row_scoped_vendor_code_entries_with_index(self):
        item = {"line_code": "MOT-", "item_code": "B", "vendor": "MOTION"}
        fake_app = SimpleNamespace(
            filtered_items=[item],
            inventory_lookup={},
            qoh_adjustments={},
            order_rules={},
            vendor_codes_used=["GREGDIST", "MOTION", "SOURCE"],
            last_removed_bulk_items=[],
        )

        state = session_state_flow.capture_bulk_history_state(
            fake_app,
            capture_spec=session_state_flow.bulk_history_capture_spec_for_columns(
                ("vendor",),
                row_ids=(ui_bulk.bulk_row_id(item),),
                include_vendor_codes=True,
            ),
        )

        self.assertEqual(
            state["vendor_codes_used_entries"],
            [("MOTION", True, 1)],
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
        self.assertEqual(events, ["summary", "status"])

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
        self.assertEqual(events, ["summary", "status"])

    def test_restore_bulk_history_state_applies_row_scoped_filtered_item_patches(self):
        events = []
        item_a = {"line_code": "AER-", "item_code": "A", "vendor": ""}
        item_b = {"line_code": "MOT-", "item_code": "B", "vendor": "SOURCE", "why": "Old"}
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
                "filtered_items_row_patches": [
                    (ui_bulk.bulk_row_id(item_b), [("vendor", True, "MOTION"), ("why", False, None)])
                ],
            },
        )

        self.assertIs(fake_app.filtered_items, filtered_items)
        self.assertEqual(fake_app.filtered_items[1]["vendor"], "MOTION")
        self.assertNotIn("why", fake_app.filtered_items[1])
        self.assertEqual(list(fake_app._bulk_row_render_cache.keys()), [ui_bulk.bulk_row_id(item_a)])
        self.assertEqual(events, ["summary", "status"])

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
        self.assertEqual(events, ["summary", "status"])

    def test_restore_bulk_history_state_applies_row_scoped_mapping_entry_patches(self):
        events = []
        item = {"line_code": "MOT-", "item_code": "B", "vendor": ""}
        inventory_lookup = {("MOT-", "B"): {"qoh": 9, "supplier": "SOURCE"}}
        qoh_adjustments = {("MOT-", "B"): {"old": 1, "new": 9}}
        order_rules = {"MOT-:B": {"pack_size": 10, "order_policy": "manual"}}
        fake_app = SimpleNamespace(
            filtered_items=[item],
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
                "filtered_items_row_patches": [(ui_bulk.bulk_row_id(item), [])],
                "inventory_lookup_entry_patches": [(("MOT-", "B"), [("qoh", True, 2)])],
                "qoh_adjustments_entry_patches": [(("MOT-", "B"), [("new", True, 2)])],
                "order_rules_entry_patches": [("MOT-:B", [("pack_size", True, 4)])],
            },
        )

        self.assertIs(fake_app.inventory_lookup, inventory_lookup)
        self.assertIs(fake_app.qoh_adjustments, qoh_adjustments)
        self.assertIs(fake_app.order_rules, order_rules)
        self.assertEqual(fake_app.inventory_lookup, {("MOT-", "B"): {"qoh": 2, "supplier": "SOURCE"}})
        self.assertEqual(fake_app.qoh_adjustments, {("MOT-", "B"): {"old": 1, "new": 2}})
        self.assertEqual(fake_app.order_rules, {"MOT-:B": {"pack_size": 4, "order_policy": "manual"}})
        self.assertEqual(events, ["summary", "status"])

    def test_restore_bulk_history_state_uses_incremental_refresh_for_row_scoped_restore_when_available(self):
        events = []
        item = {"line_code": "MOT-", "item_code": "B", "vendor": "SOURCE"}
        fake_app = SimpleNamespace(
            filtered_items=[item],
            inventory_lookup={},
            qoh_adjustments={},
            order_rules={},
            vendor_codes_used=[],
            _loaded_order_rules={},
            _loaded_vendor_codes=[],
            last_removed_bulk_items=[],
            bulk_sheet=SimpleNamespace(clear_selection=lambda: events.append("clear")),
            _refresh_bulk_view_after_edit=lambda row_ids, changed_cols=None: events.append(("refresh", tuple(row_ids), tuple(changed_cols or ()))) or True,
            _refresh_vendor_inputs=lambda: events.append("vendors"),
            _apply_bulk_filter=lambda: events.append("bulk"),
            _update_bulk_summary=lambda: events.append("summary"),
            _update_bulk_cell_status=lambda: events.append("status"),
        )
        capture_spec = session_state_flow.bulk_history_capture_spec_for_columns(("vendor",), row_ids=(ui_bulk.bulk_row_id(item),))

        session_state_flow.restore_bulk_history_state(
            fake_app,
            {
                "filtered_items_rows": [
                    (ui_bulk.bulk_row_id(item), {"line_code": "MOT-", "item_code": "B", "vendor": "MOTION"})
                ],
            },
            capture_spec=capture_spec,
        )

        self.assertEqual(item["vendor"], "MOTION")
        self.assertEqual(events, ["clear", ("refresh", (ui_bulk.bulk_row_id(item),), ("vendor",)), "summary", "status"])

    def test_restore_bulk_history_state_falls_back_to_apply_filter_when_incremental_refresh_declines(self):
        events = []
        item = {"line_code": "MOT-", "item_code": "B", "vendor": "SOURCE"}
        fake_app = SimpleNamespace(
            filtered_items=[item],
            inventory_lookup={},
            qoh_adjustments={},
            order_rules={},
            vendor_codes_used=[],
            _loaded_order_rules={},
            _loaded_vendor_codes=[],
            last_removed_bulk_items=[],
            bulk_sheet=None,
            _refresh_bulk_view_after_edit=lambda row_ids, changed_cols=None: events.append(("refresh", tuple(row_ids), tuple(changed_cols or ()))) or False,
            _refresh_vendor_inputs=lambda: events.append("vendors"),
            _apply_bulk_filter=lambda: events.append("bulk"),
            _update_bulk_summary=lambda: events.append("summary"),
            _update_bulk_cell_status=lambda: events.append("status"),
        )
        capture_spec = session_state_flow.bulk_history_capture_spec_for_columns(("vendor",), row_ids=(ui_bulk.bulk_row_id(item),))

        session_state_flow.restore_bulk_history_state(
            fake_app,
            {
                "filtered_items_rows": [
                    (ui_bulk.bulk_row_id(item), {"line_code": "MOT-", "item_code": "B", "vendor": "MOTION"})
                ],
            },
            capture_spec=capture_spec,
        )

        self.assertEqual(events, [("refresh", (ui_bulk.bulk_row_id(item),), ("vendor",)), "summary", "status"])

    def test_restore_bulk_history_state_refreshes_vendor_inputs_when_vendor_codes_change(self):
        events = []
        fake_app = SimpleNamespace(
            filtered_items=[],
            inventory_lookup={},
            qoh_adjustments={},
            order_rules={},
            vendor_codes_used=["OLD"],
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
                "filtered_items": [],
                "vendor_codes_used": ["NEW"],
            },
        )

        self.assertEqual(fake_app.vendor_codes_used, ["NEW"])
        self.assertEqual(events, ["vendors", "summary", "status"])

    def test_restore_bulk_history_state_applies_vendor_code_entries_in_place(self):
        events = []
        fake_app = SimpleNamespace(
            filtered_items=[],
            inventory_lookup={},
            qoh_adjustments={},
            order_rules={},
            vendor_codes_used=["GREGDIST", "SOURCE"],
            _loaded_order_rules={},
            _loaded_vendor_codes=[],
            last_removed_bulk_items=[],
            bulk_sheet=None,
            _refresh_vendor_inputs=lambda: events.append("vendors"),
            _apply_bulk_filter=lambda: events.append("bulk"),
            _update_bulk_summary=lambda: events.append("summary"),
            _update_bulk_cell_status=lambda: events.append("status"),
        )
        vendor_codes_used = fake_app.vendor_codes_used

        session_state_flow.restore_bulk_history_state(
            fake_app,
            {
                "filtered_items": [],
                "vendor_codes_used_entries": [("MOTION", True, 1)],
            },
        )

        self.assertIs(fake_app.vendor_codes_used, vendor_codes_used)
        self.assertEqual(fake_app.vendor_codes_used, ["GREGDIST", "MOTION", "SOURCE"])
        self.assertEqual(events, ["vendors", "summary", "status"])

    def test_restore_bulk_history_state_removes_vendor_code_entries_in_place(self):
        events = []
        fake_app = SimpleNamespace(
            filtered_items=[],
            inventory_lookup={},
            qoh_adjustments={},
            order_rules={},
            vendor_codes_used=["GREGDIST", "MOTION", "SOURCE"],
            _loaded_order_rules={},
            _loaded_vendor_codes=[],
            last_removed_bulk_items=[],
            bulk_sheet=None,
            _refresh_vendor_inputs=lambda: events.append("vendors"),
            _apply_bulk_filter=lambda: events.append("bulk"),
            _update_bulk_summary=lambda: events.append("summary"),
            _update_bulk_cell_status=lambda: events.append("status"),
        )
        vendor_codes_used = fake_app.vendor_codes_used

        session_state_flow.restore_bulk_history_state(
            fake_app,
            {
                "filtered_items": [],
                "vendor_codes_used_entries": [("MOTION", False, None)],
            },
        )

        self.assertIs(fake_app.vendor_codes_used, vendor_codes_used)
        self.assertEqual(fake_app.vendor_codes_used, ["GREGDIST", "SOURCE"])
        self.assertEqual(events, ["vendors", "summary", "status"])

    def test_restore_bulk_history_state_reorders_vendor_code_entries_in_place(self):
        events = []
        fake_app = SimpleNamespace(
            filtered_items=[],
            inventory_lookup={},
            qoh_adjustments={},
            order_rules={},
            vendor_codes_used=["MOTION", "GREGDIST", "SOURCE"],
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
                "filtered_items": [],
                "vendor_codes_used_entries": [("MOTION", True, 1)],
            },
        )

        self.assertEqual(fake_app.vendor_codes_used, ["GREGDIST", "MOTION", "SOURCE"])
        self.assertEqual(events, ["vendors", "summary", "status"])

    def test_restore_bulk_history_state_without_sheet_skips_apply_bulk_filter(self):
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
                "filtered_items": [{"item_code": "ABC123"}],
            },
        )

        self.assertEqual(fake_app.filtered_items, [{"item_code": "ABC123"}])
        self.assertEqual(events, ["summary", "status"])

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
