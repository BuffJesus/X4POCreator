import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_assignment_actions


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
    def test_bulk_apply_selected_updates_items_and_summary(self):
        calls = []
        app = SimpleNamespace(
            var_bulk_vendor=DummyVar("gregdist"),
            bulk_tree=DummyTree(selected=("0", "1")),
            filtered_items=[{"vendor": ""}, {"vendor": ""}],
            vendor_codes_used=[],
            _capture_bulk_history_state=lambda: {"before": True},
            _finalize_bulk_history_action=lambda label, before: calls.append((label, before)),
            _update_bulk_summary=lambda: calls.append("summary"),
        )

        ui_assignment_actions.bulk_apply_selected(app)

        self.assertEqual(app.filtered_items[0]["vendor"], "GREGDIST")
        self.assertEqual(app.filtered_items[1]["vendor"], "GREGDIST")
        self.assertIn("GREGDIST", app.vendor_codes_used)
        self.assertEqual(calls, ["summary", ("vendor:selected", {"before": True})])

    def test_bulk_apply_selected_with_bulk_sheet_refreshes_rows_once(self):
        calls = []
        app = SimpleNamespace(
            var_bulk_vendor=DummyVar("gregdist"),
            bulk_sheet=SimpleNamespace(selected_row_ids=lambda: ("0", "1")),
            filtered_items=[{"vendor": ""}, {"vendor": ""}],
            vendor_codes_used=[],
            _capture_bulk_history_state=lambda: {"before": True},
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))),
            _finalize_bulk_history_action=lambda label, before: calls.append((label, before)),
            _update_bulk_summary=lambda: calls.append("summary"),
        )

        ui_assignment_actions.bulk_apply_selected(app)

        self.assertEqual(app.filtered_items[0]["vendor"], "GREGDIST")
        self.assertEqual(app.filtered_items[1]["vendor"], "GREGDIST")
        self.assertIn("GREGDIST", app.vendor_codes_used)
        self.assertEqual(calls, [("refresh", ("0", "1")), "summary", ("vendor:selected", {"before": True})])

    def test_bulk_apply_visible_with_bulk_sheet_refreshes_rows_once(self):
        calls = []
        app = SimpleNamespace(
            var_bulk_vendor=DummyVar("motion"),
            bulk_sheet=SimpleNamespace(visible_row_ids=lambda: ("0", "1", "2")),
            filtered_items=[{"vendor": ""}, {"vendor": ""}, {"vendor": ""}],
            vendor_codes_used=[],
            _capture_bulk_history_state=lambda: {"before": True},
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))),
            _finalize_bulk_history_action=lambda label, before: calls.append((label, before)),
            _update_bulk_summary=lambda: calls.append("summary"),
        )

        ui_assignment_actions.bulk_apply_visible(app)

        self.assertEqual([item["vendor"] for item in app.filtered_items], ["MOTION", "MOTION", "MOTION"])
        self.assertIn("MOTION", app.vendor_codes_used)
        self.assertEqual(calls, [("refresh", ("0", "1", "2")), "summary", ("vendor:visible", {"before": True})])

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
