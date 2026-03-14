import csv
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import export_flow
from models import AppSessionState, MaintenanceIssue


class ExportFlowTests(unittest.TestCase):
    def test_group_assigned_items_groups_by_vendor(self):
        grouped = export_flow.group_assigned_items([
            {"vendor": "MOTION", "item_code": "A"},
            {"vendor": "SOURCE", "item_code": "B"},
            {"vendor": "MOTION", "item_code": "C"},
        ])

        self.assertEqual(list(grouped.keys()), ["MOTION", "SOURCE"])
        self.assertEqual([item["item_code"] for item in grouped["MOTION"]], ["A", "C"])

    def test_partition_export_items_separates_held_items(self):
        exportable, held = export_flow.partition_export_items([
            {"item_code": "A", "release_decision": "release_now"},
            {"item_code": "B", "release_decision": "hold_for_free_day"},
            {"item_code": "C", "release_decision": "hold_for_threshold"},
            {"item_code": "E", "release_decision": "export_next_business_day_for_free_day"},
            {"item_code": "D", "release_decision": ""},
        ])

        self.assertEqual([item["item_code"] for item in exportable], ["A", "E", "D"])
        self.assertEqual([item["item_code"] for item in held], ["B", "C"])

    def test_build_session_snapshot_captures_expected_fields(self):
        app = SimpleNamespace(
            var_sales_path=SimpleNamespace(get=lambda: "C:\\Reports\\sales.csv"),
            var_po_path=SimpleNamespace(get=lambda: "C:\\Reports\\po.csv"),
            var_susp_path=SimpleNamespace(get=lambda: "C:\\Reports\\susp.csv"),
            var_onhand_path=SimpleNamespace(get=lambda: "C:\\Reports\\onhand.csv"),
            var_minmax_path=SimpleNamespace(get=lambda: "C:\\Reports\\minmax.csv"),
            var_packsize_path=SimpleNamespace(get=lambda: "C:\\Reports\\packs.csv"),
            qoh_adjustments={("AER-", "GH781-4"): {"old": 2, "new": 5}},
            assigned_items=[{"line_code": "AER-", "item_code": "GH781-4", "order_qty": 250}],
            startup_warning_rows=[{"warning_type": "Pack Fallback Conflict"}],
            order_rules={"AER-:GH781-4": {"pack_size": 500}},
        )
        issues = (
            MaintenanceIssue(
                line_code="AER-",
                item_code="GH781-4",
                description="HOSE",
                issue="Set order multiple to 500",
                assigned_vendor="GREGDIST",
                x4_supplier="",
                pack_size="500",
                x4_order_multiple="",
                x4_min="22",
                x4_max="67",
                target_min="22",
                target_max="67",
                sug_min="22",
                sug_max="67",
                qoh_old="2",
                qoh_new="5",
            ),
        )

        snapshot = export_flow.build_session_snapshot(app, "C:\\Exports", ("C:\\Exports\\PO_A.xlsx",), issues)

        self.assertEqual(snapshot.output_dir, "C:\\Exports")
        self.assertEqual(snapshot.loaded_report_paths["sales"], "C:\\Reports\\sales.csv")
        self.assertEqual(snapshot.po_files, ("C:\\Exports\\PO_A.xlsx",))
        self.assertEqual(snapshot.qoh_adjustments[0]["new"], 5)
        self.assertEqual(snapshot.order_rules["AER-:GH781-4"]["pack_size"], 500)

    def test_build_session_snapshot_from_state_captures_expected_fields(self):
        session = AppSessionState(
            qoh_adjustments={("AER-", "GH781-4"): {"old": 2, "new": 5}},
            assigned_items=[{"line_code": "AER-", "item_code": "GH781-4", "order_qty": 250}],
            startup_warning_rows=[{"warning_type": "Pack Fallback Conflict"}],
            order_rules={"AER-:GH781-4": {"pack_size": 500}},
        )
        issues = (
            MaintenanceIssue(
                line_code="AER-",
                item_code="GH781-4",
                description="HOSE",
                issue="Set order multiple to 500",
                assigned_vendor="GREGDIST",
                x4_supplier="",
                pack_size="500",
                x4_order_multiple="",
                x4_min="22",
                x4_max="67",
                target_min="22",
                target_max="67",
                sug_min="22",
                sug_max="67",
                qoh_old="2",
                qoh_new="5",
            ),
        )

        snapshot = export_flow.build_session_snapshot_from_state(
            session,
            {"sales": "C:\\Reports\\sales.csv"},
            "C:\\Exports",
            ("C:\\Exports\\PO_A.xlsx",),
            issues,
        )

        self.assertEqual(snapshot.loaded_report_paths["sales"], "C:\\Reports\\sales.csv")
        self.assertEqual(snapshot.qoh_adjustments[0]["new"], 5)
        self.assertEqual(snapshot.order_rules["AER-:GH781-4"]["pack_size"], 500)

    def test_export_maintenance_csv_writes_ascii_safe_rows(self):
        issues = [
            MaintenanceIssue(
                line_code="AER-",
                item_code="GH781-4",
                description='Bad â€” text "quote"',
                issue="Fix supplier â†’ pack",
                assigned_vendor="GREGDIST",
                x4_supplier="",
                pack_size="500",
                x4_order_multiple="",
                x4_min="22",
                x4_max="67",
                target_min="22",
                target_max="67",
                sug_min="22",
                sug_max="67",
                qoh_old="2",
                qoh_new="5",
            )
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = export_flow.export_maintenance_csv(issues, tmp)
            with open(path, newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.reader(handle))

        self.assertEqual(rows[0][0], "Line Code")
        self.assertEqual(rows[1][0], "AER-")
        self.assertEqual(rows[1][2], 'Bad - text "quote"')
        self.assertEqual(rows[1][3], "Fix supplier -> pack")

    def test_do_export_surfaces_shared_suspense_carry_merge_note(self):
        session = AppSessionState(
            assigned_items=[{"vendor": "MOTION", "line_code": "AER-", "item_code": "GH781-4", "order_qty": 2}],
            startup_warning_rows=[],
            qoh_adjustments={},
            order_rules={},
        )
        app = SimpleNamespace(
            session=session,
            root=SimpleNamespace(update=lambda: None),
            _show_loading=lambda message: None,
            _hide_loading=lambda: None,
            _persist_suspense_carry=lambda: {"conflict": True},
            _build_maintenance_report=lambda: [],
            _show_maintenance_report=lambda output_dir, issues: None,
            var_sales_path=SimpleNamespace(get=lambda: ""),
            var_po_path=SimpleNamespace(get=lambda: ""),
            var_susp_path=SimpleNamespace(get=lambda: ""),
            var_onhand_path=SimpleNamespace(get=lambda: ""),
            var_minmax_path=SimpleNamespace(get=lambda: ""),
            var_packsize_path=SimpleNamespace(get=lambda: ""),
        )

        with tempfile.TemporaryDirectory() as tmp, \
             patch("export_flow.filedialog.askdirectory", return_value=tmp), \
             patch("export_flow.storage.append_order_history"), \
             patch("export_flow.storage.save_session_snapshot"), \
             patch("export_flow.messagebox.showinfo") as mocked_info:
            export_flow.do_export(
                app,
                lambda vendor, items, output_dir: str(Path(output_dir) / f"{vendor}.xlsx"),
                str(Path(tmp) / "order_history.json"),
                str(Path(tmp) / "sessions"),
            )

        mocked_info.assert_called_once()
        self.assertIn("merged your update with newer shared data", mocked_info.call_args.args[1])

    def test_do_export_skips_held_items_and_notes_them_in_completion_message(self):
        session = AppSessionState(
            assigned_items=[
                {
                    "vendor": "MOTION",
                    "line_code": "AER-",
                    "item_code": "GH781-4",
                    "order_qty": 2,
                    "release_decision": "release_now",
                },
                {
                    "vendor": "MOTION",
                    "line_code": "AER-",
                    "item_code": "GH781-5",
                    "order_qty": 3,
                    "release_decision": "hold_for_threshold",
                    "release_reason": "Held for freight threshold 2000",
                },
            ],
            startup_warning_rows=[],
            qoh_adjustments={},
            order_rules={},
        )
        app = SimpleNamespace(
            session=session,
            root=SimpleNamespace(update=lambda: None),
            _show_loading=lambda message: None,
            _hide_loading=lambda: None,
            _persist_suspense_carry=lambda: {"conflict": False},
            _build_maintenance_report=lambda: [],
            _show_maintenance_report=lambda output_dir, issues: None,
            var_sales_path=SimpleNamespace(get=lambda: ""),
            var_po_path=SimpleNamespace(get=lambda: ""),
            var_susp_path=SimpleNamespace(get=lambda: ""),
            var_onhand_path=SimpleNamespace(get=lambda: ""),
            var_minmax_path=SimpleNamespace(get=lambda: ""),
            var_packsize_path=SimpleNamespace(get=lambda: ""),
        )

        with tempfile.TemporaryDirectory() as tmp, \
             patch("export_flow.filedialog.askdirectory", return_value=tmp), \
             patch("export_flow.storage.append_order_history") as mocked_history, \
             patch("export_flow.storage.save_session_snapshot"), \
             patch("export_flow.messagebox.showinfo") as mocked_info:
            export_flow.do_export(
                app,
                lambda vendor, items, output_dir: str(Path(output_dir) / f"{vendor}_{len(items)}.xlsx"),
                str(Path(tmp) / "order_history.json"),
                str(Path(tmp) / "sessions"),
            )

        mocked_history.assert_called_once()
        exported_items = mocked_history.call_args.args[1]
        self.assertEqual(len(exported_items), 1)
        self.assertEqual(exported_items[0]["item_code"], "GH781-4")
        self.assertIn("were held by shipping policy and were not exported", mocked_info.call_args.args[1])

    def test_do_export_stops_when_all_items_are_held(self):
        session = AppSessionState(
            assigned_items=[
                {
                    "vendor": "MOTION",
                    "line_code": "AER-",
                    "item_code": "GH781-5",
                    "order_qty": 3,
                    "release_decision": "hold_for_threshold",
                    "release_reason": "Held for freight threshold 2000",
                },
            ],
        )
        app = SimpleNamespace(session=session)

        with patch("export_flow.filedialog.askdirectory") as mocked_dir, \
             patch("export_flow.messagebox.showinfo") as mocked_info:
            export_flow.do_export(
                app,
                lambda vendor, items, output_dir: output_dir,
                str(ROOT / "order_history.json"),
                str(ROOT / "sessions"),
            )

        mocked_dir.assert_not_called()
        mocked_info.assert_called_once()
        self.assertIn("currently held by vendor shipping policy", mocked_info.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
