import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_assignment_actions
import ui_bulk


class DummyVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class DummyTree:
    def __init__(self, selected=None, children=None):
        self._selected = tuple(selected or ())
        self._children = tuple(children or ())
        self.set_calls = []

    def selection(self):
        return self._selected

    def get_children(self):
        return self._children

    def set(self, item_id, column, value):
        self.set_calls.append((item_id, column, value))


class AssignmentActionTests(unittest.TestCase):
    def test_flush_pending_bulk_sheet_edit_calls_sheet_hook(self):
        calls = []
        app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(flush_pending_edit=lambda: calls.append("flush")),
        )

        ui_assignment_actions.flush_pending_bulk_sheet_edit(app)

        self.assertEqual(calls, ["flush"])

    def test_bulk_apply_selected_updates_items_and_summary(self):
        calls = []
        app = SimpleNamespace(
            var_bulk_vendor=DummyVar("gregdist"),
            bulk_tree=DummyTree(selected=("0", "1")),
            filtered_items=[{"vendor": ""}, {"vendor": ""}],
            vendor_codes_used=[],
            _capture_bulk_history_state=lambda capture_spec=None: {"before": True, "capture_spec": capture_spec},
            _finalize_bulk_history_action=lambda label, before, coalesce_key=None: calls.append((label, before, coalesce_key)),
            _update_bulk_summary=lambda: calls.append("summary"),
        )

        ui_assignment_actions.bulk_apply_selected(app)

        self.assertEqual(app.filtered_items[0]["vendor"], "GREGDIST")
        self.assertEqual(app.filtered_items[1]["vendor"], "GREGDIST")
        self.assertIn("GREGDIST", app.vendor_codes_used)
        self.assertEqual(
            calls,
            [
                "summary",
                (
                    "vendor:selected",
                    {
                        "before": True,
                        "capture_spec": {
                            "inventory_lookup": False,
                            "qoh_adjustments": False,
                            "order_rules": False,
                            "vendor_codes_used": True,
                            "last_removed_bulk_items": True,
                        },
                    },
                    {"kind": "vendor_selected", "col_name": "vendor", "row_ids": ("0", "1"), "scope": {"vendor": "GREGDIST"}},
                ),
            ],
        )

    def test_bulk_apply_selected_with_bulk_sheet_refreshes_rows_once(self):
        calls = []
        app = SimpleNamespace(
            var_bulk_vendor=DummyVar("gregdist"),
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: calls.append("flush"),
                selected_row_ids=lambda: ("0", "1"),
            ),
            filtered_items=[{"vendor": ""}, {"vendor": ""}],
            _bulk_summary_counts={"total": 2, "assigned": 0, "review": 0, "warning": 0},
            vendor_codes_used=[],
            _capture_bulk_history_state=lambda: {"before": True},
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))),
            _finalize_bulk_history_action=lambda label, before, coalesce_key=None: calls.append((label, before, coalesce_key)),
            _update_bulk_summary=lambda: calls.append("summary"),
        )

        ui_assignment_actions.bulk_apply_selected(app)

        self.assertEqual(app.filtered_items[0]["vendor"], "GREGDIST")
        self.assertEqual(app.filtered_items[1]["vendor"], "GREGDIST")
        self.assertIn("GREGDIST", app.vendor_codes_used)
        self.assertEqual(
            calls,
            [
                "flush",
                ("refresh", ("0", "1")),
                "summary",
                (
                    "vendor:selected",
                    {"before": True},
                    {"kind": "vendor_selected", "col_name": "vendor", "row_ids": ("0", "1"), "scope": {"vendor": "GREGDIST"}},
                ),
            ],
        )
        self.assertEqual(app._bulk_summary_counts, {"total": 2, "assigned": 2, "review": 0, "warning": 0})

    def test_bulk_apply_visible_with_bulk_sheet_refreshes_rows_once(self):
        calls = []
        app = SimpleNamespace(
            var_bulk_vendor=DummyVar("motion"),
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: calls.append("flush"),
                visible_row_ids=lambda: ("0", "1", "2"),
            ),
            filtered_items=[{"vendor": ""}, {"vendor": ""}, {"vendor": ""}],
            vendor_codes_used=[],
            _capture_bulk_history_state=lambda: {"before": True},
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))),
            _finalize_bulk_history_action=lambda label, before, coalesce_key=None: calls.append((label, before, coalesce_key)),
            _update_bulk_summary=lambda: calls.append("summary"),
        )

        ui_assignment_actions.bulk_apply_visible(app)

        self.assertEqual([item["vendor"] for item in app.filtered_items], ["MOTION", "MOTION", "MOTION"])
        self.assertIn("MOTION", app.vendor_codes_used)
        self.assertEqual(
            calls,
            [
                "flush",
                ("refresh", ("0", "1", "2")),
                "summary",
                (
                    "vendor:visible",
                    {"before": True},
                    {"kind": "vendor_visible", "col_name": "vendor", "row_ids": ("0", "1", "2"), "scope": {"vendor": "MOTION"}},
                ),
            ],
        )

    def test_bulk_apply_selected_resolves_stable_bulk_row_ids(self):
        calls = []
        item_a = {"line_code": "AER-", "item_code": "A", "vendor": ""}
        item_b = {"line_code": "MOT-", "item_code": "B", "vendor": ""}
        row_id_a = ui_bulk.bulk_row_id(item_a)
        row_id_b = ui_bulk.bulk_row_id(item_b)
        app = SimpleNamespace(
            var_bulk_vendor=DummyVar("gregdist"),
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: calls.append("flush"),
                selected_row_ids=lambda: (row_id_b, row_id_a),
            ),
            filtered_items=[item_a, item_b],
            vendor_codes_used=[],
            _capture_bulk_history_state=lambda: {"before": True},
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))),
            _finalize_bulk_history_action=lambda label, before, coalesce_key=None: calls.append((label, before, coalesce_key)),
            _update_bulk_summary=lambda: calls.append("summary"),
            _find_filtered_item=lambda key: next((item for item in (item_a, item_b) if (item["line_code"], item["item_code"]) == key), None),
        )

        ui_assignment_actions.bulk_apply_selected(app)

        self.assertEqual(item_a["vendor"], "GREGDIST")
        self.assertEqual(item_b["vendor"], "GREGDIST")
        self.assertEqual(
            calls,
            [
                "flush",
                ("refresh", (row_id_b, row_id_a)),
                "summary",
                (
                    "vendor:selected",
                    {"before": True},
                    {"kind": "vendor_selected", "col_name": "vendor", "row_ids": (row_id_b, row_id_a), "scope": {"vendor": "GREGDIST"}},
                ),
            ],
        )

    def test_bulk_apply_visible_resolves_stable_bulk_row_ids(self):
        calls = []
        item_a = {"line_code": "AER-", "item_code": "A", "vendor": ""}
        item_b = {"line_code": "MOT-", "item_code": "B", "vendor": ""}
        row_id_a = ui_bulk.bulk_row_id(item_a)
        row_id_b = ui_bulk.bulk_row_id(item_b)
        app = SimpleNamespace(
            var_bulk_vendor=DummyVar("motion"),
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: calls.append("flush"),
                visible_row_ids=lambda: (row_id_a, row_id_b),
            ),
            filtered_items=[item_b, item_a],
            vendor_codes_used=[],
            _capture_bulk_history_state=lambda: {"before": True},
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))),
            _finalize_bulk_history_action=lambda label, before, coalesce_key=None: calls.append((label, before, coalesce_key)),
            _update_bulk_summary=lambda: calls.append("summary"),
            _find_filtered_item=lambda key: next((item for item in (item_a, item_b) if (item["line_code"], item["item_code"]) == key), None),
        )

        ui_assignment_actions.bulk_apply_visible(app)

        self.assertEqual(item_a["vendor"], "MOTION")
        self.assertEqual(item_b["vendor"], "MOTION")
        self.assertEqual(
            calls,
            [
                "flush",
                ("refresh", (row_id_a, row_id_b)),
                "summary",
                (
                    "vendor:visible",
                    {"before": True},
                    {"kind": "vendor_visible", "col_name": "vendor", "row_ids": (row_id_a, row_id_b), "scope": {"vendor": "MOTION"}},
                ),
            ],
        )

    def test_bulk_apply_selected_history_key_includes_vendor_value(self):
        calls = []
        app = SimpleNamespace(
            var_bulk_vendor=DummyVar("gregdist"),
            bulk_tree=DummyTree(selected=("0",)),
            filtered_items=[{"vendor": ""}],
            vendor_codes_used=[],
            _capture_bulk_history_state=lambda: {"before": True},
            _finalize_bulk_history_action=lambda label, before, coalesce_key=None: calls.append(coalesce_key),
            _update_bulk_summary=lambda: None,
        )

        ui_assignment_actions.bulk_apply_selected(app)

        self.assertEqual(
            calls,
            [{"kind": "vendor_selected", "col_name": "vendor", "row_ids": ("0",), "scope": {"vendor": "GREGDIST"}}],
        )

    def test_go_to_individual_flushes_pending_sheet_edit_before_switching_tabs(self):
        calls = []
        app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(flush_pending_edit=lambda: calls.append("flush")),
            filtered_items=[{"vendor": ""}, {"vendor": "MOTION"}],
            _check_stock_warnings=lambda: calls.append("warnings") or True,
            _populate_assign_item=lambda: calls.append("populate"),
            notebook=SimpleNamespace(
                tab=lambda idx, state=None: calls.append(("tab", idx, state)),
                select=lambda idx: calls.append(("select", idx)),
            ),
        )

        ui_assignment_actions.go_to_individual(app)

        self.assertEqual(app.assign_index, 0)
        self.assertEqual(app.individual_items, [{"vendor": ""}])
        self.assertEqual(calls, ["flush", "warnings", "populate", ("tab", 4, "normal"), ("select", 4)])

    def test_undo_last_bulk_removal_prefers_structured_bulk_undo_for_latest_removal(self):
        calls = []
        app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(flush_pending_edit=lambda: calls.append("flush")),
            bulk_undo_stack=[{"label": "remove:selected_rows"}],
            _bulk_undo=lambda event=None: calls.append(("bulk_undo", event)),
            last_removed_bulk_items=[(1, {"item_code": "B"})],
        )

        with patch("ui_assignment_actions.messagebox.showinfo") as mocked:
            ui_assignment_actions.undo_last_bulk_removal(app)

        self.assertEqual(calls, ["flush", ("bulk_undo", None)])
        mocked.assert_called_once_with("Undo Complete", "Reverted the most recent bulk removal.")

    def test_undo_last_bulk_removal_blocks_legacy_restore_when_newer_action_exists(self):
        calls = []
        app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(flush_pending_edit=lambda: calls.append("flush")),
            bulk_undo_stack=[{"label": "edit:pack_size"}],
            last_removed_bulk_items=[(1, {"item_code": "B"})],
            filtered_items=[{"item_code": "A"}],
            _apply_bulk_filter=lambda: calls.append("bulk"),
            _update_bulk_summary=lambda: calls.append("summary"),
        )

        with patch("ui_assignment_actions.messagebox.showinfo") as mocked:
            ui_assignment_actions.undo_last_bulk_removal(app)

        self.assertEqual(calls, ["flush"])
        self.assertEqual(app.filtered_items, [{"item_code": "A"}])
        mocked.assert_called_once_with(
            "Nothing to Undo",
            "The most recent bulk action was not a removal. Use Undo for the latest action first.",
        )

    def test_assign_current_advances_until_finish(self):
        populate_calls = []
        finish_calls = []
        app = SimpleNamespace(
            var_vendor_input=DummyVar("source"),
            individual_items=[{"vendor": ""}, {"vendor": ""}],
            assign_index=0,
            vendor_codes_used=[],
            _populate_assign_item=lambda: populate_calls.append("populate"),
            _finish_assign=lambda: finish_calls.append("finish"),
        )

        ui_assignment_actions.assign_current(app)
        self.assertEqual(app.individual_items[0]["vendor"], "SOURCE")
        self.assertEqual(app.assign_index, 1)
        self.assertEqual(populate_calls, ["populate"])

        ui_assignment_actions.assign_current(app)
        self.assertEqual(app.individual_items[1]["vendor"], "SOURCE")
        self.assertEqual(app.assign_index, 2)
        self.assertEqual(finish_calls, ["finish"])

    def test_bulk_apply_visible_warns_when_vendor_missing(self):
        app = SimpleNamespace(
            var_bulk_vendor=DummyVar(""),
            bulk_tree=DummyTree(children=("0",)),
            filtered_items=[{"vendor": ""}],
            vendor_codes_used=[],
            _update_bulk_summary=lambda: None,
        )

        with patch("ui_assignment_actions.messagebox.showinfo") as mocked:
            ui_assignment_actions.bulk_apply_visible(app)

        mocked.assert_called_once()


if __name__ == "__main__":
    unittest.main()
