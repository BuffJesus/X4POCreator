import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bulk_sheet_actions_flow


class BulkSheetActionsFlowTests(unittest.TestCase):
    def test_bulk_copy_selection_returns_break_only_when_sheet_copies(self):
        app_true = SimpleNamespace(bulk_sheet=SimpleNamespace(copy_selection_to_clipboard=lambda: True))
        app_false = SimpleNamespace(bulk_sheet=SimpleNamespace(copy_selection_to_clipboard=lambda: False))

        self.assertEqual(bulk_sheet_actions_flow.bulk_copy_selection(app_true), "break")
        self.assertIsNone(bulk_sheet_actions_flow.bulk_copy_selection(app_false))

    def test_bulk_clear_selection_resets_context(self):
        events = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(clear_selection=lambda: events.append("clear")),
            _right_click_bulk_context={"row_id": "1"},
        )

        result = bulk_sheet_actions_flow.bulk_clear_selection(fake_app)

        self.assertEqual(result, "break")
        self.assertEqual(events, ["clear"])
        self.assertIsNone(fake_app._right_click_bulk_context)

    def test_bulk_fill_selection_with_current_value_applies_and_records_history(self):
        events = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                selected_editable_column_name=lambda: "pack_size",
                current_editable_column_name=lambda: "pack_size",
                selected_target_row_ids=lambda col_name: ("0", "1"),
                current_cell_value=lambda: " 6 ",
                clear_selection=lambda: events.append("clear"),
            ),
            _capture_bulk_history_state=lambda: {"before": True},
            _bulk_apply_editor_value=lambda row_id, col_name, value: events.append((row_id, col_name, value)),
            _apply_bulk_filter=lambda: events.append("filter"),
            _update_bulk_summary=lambda: events.append("summary"),
            _update_bulk_cell_status=lambda: events.append("status"),
            _finalize_bulk_history_action=lambda label, before: events.append((label, before)),
        )

        result = bulk_sheet_actions_flow.bulk_fill_selection_with_current_value(
            fake_app,
            ("pack_size",),
            lambda event, **kwargs: events.append((event, kwargs["alias"], kwargs["row_count"], kwargs["value"])),
            alias="fill_down",
        )

        self.assertEqual(result, "break")
        self.assertEqual(
            events,
            [
                ("bulk_shortcut_fill", "fill_down", 2, "6"),
                ("0", "pack_size", "6"),
                ("1", "pack_size", "6"),
                "filter",
                "clear",
                "summary",
                "status",
                ("fill_down:pack_size", {"before": True}),
            ],
        )

    def test_bulk_begin_edit_opens_buy_rule_editor_from_right_click(self):
        events = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                selected_editable_column_name=lambda: "",
                current_editable_column_name=lambda: "",
                selected_target_row_ids=lambda col_name: (),
                selected_row_ids=lambda: (),
            ),
            _right_click_bulk_context={"row_id": "7", "col_name": "buy_rule"},
            _open_buy_rule_editor=lambda idx: events.append(("buy_rule", idx)),
        )

        result = bulk_sheet_actions_flow.bulk_begin_edit(
            fake_app,
            ("pack_size",),
            lambda *args, **kwargs: None,
            lambda event, **kwargs: events.append((event, kwargs)),
        )

        self.assertEqual(result, "break")
        self.assertIn(("buy_rule", 7), events)
        self.assertIn("bulk_begin_edit", [entry[0] for entry in events if isinstance(entry, tuple) and isinstance(entry[0], str)])
        self.assertIn("bulk_begin_edit.buy_rule_editor", [entry[0] for entry in events if isinstance(entry, tuple) and isinstance(entry[0], str)])
        self.assertIsNone(fake_app._right_click_bulk_context)

    def test_bulk_begin_edit_opens_sheet_cell_for_non_editable_column(self):
        events = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                selected_editable_column_name=lambda: "",
                current_editable_column_name=lambda: "",
                selected_target_row_ids=lambda col_name: (),
                selected_row_ids=lambda: (),
                sheet=SimpleNamespace(open_cell=lambda: events.append("open_cell")),
            ),
            _right_click_bulk_context={"row_id": "3", "col_name": "description"},
        )

        result = bulk_sheet_actions_flow.bulk_begin_edit(
            fake_app,
            ("pack_size",),
            lambda *args, **kwargs: None,
            lambda event, **kwargs: events.append((event, kwargs)),
        )

        self.assertEqual(result, "break")
        self.assertIn("open_cell", events)
        self.assertIn("bulk_begin_edit.open_cell", [entry[0] for entry in events if isinstance(entry, tuple)])
        self.assertIsNone(fake_app._right_click_bulk_context)


if __name__ == "__main__":
    unittest.main()
