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
    def test_export_bucket_classifies_immediate_planned_and_held(self):
        self.assertEqual(export_flow.export_bucket({"release_decision": "release_now"}), "release_now")
        self.assertEqual(export_flow.export_bucket({"release_decision": "release_now_paid_urgent_freight"}), "release_now")
        self.assertEqual(
            export_flow.export_bucket({"release_decision": "export_next_business_day_for_free_day"}),
            "planned_today",
        )
        self.assertEqual(export_flow.export_bucket({"release_decision": "hold_for_threshold"}), "held")

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

    def test_held_item_summary_includes_target_dates_when_present(self):
        summary = export_flow.held_item_summary({
            "vendor": "MOTION",
            "line_code": "AER-",
            "item_code": "GH781-4",
            "release_reason": "Held for vendor free-shipping day",
            "target_order_date": "2026-03-12",
            "target_release_date": "2026-03-13",
        })

        self.assertIn("Held for vendor free-shipping day", summary)
        self.assertIn("target order 2026-03-12", summary)
        self.assertIn("target release 2026-03-13", summary)

    def test_is_critical_shipping_hold_detects_review_sensitive_held_items(self):
        self.assertTrue(export_flow.is_critical_shipping_hold({"release_decision": "hold_for_threshold", "status": "review"}))
        self.assertTrue(export_flow.is_critical_shipping_hold({"release_decision": "hold_for_free_day", "review_required": True}))
        self.assertFalse(export_flow.is_critical_shipping_hold({"release_decision": "hold_for_threshold", "status": "ok"}))

    def test_choose_export_items_returns_all_when_no_planned_items_exist(self):
        items = [
            {"item_code": "A", "release_decision": "release_now"},
            {"item_code": "D", "release_decision": ""},
        ]

        selected = export_flow.choose_export_items(SimpleNamespace(), items)

        self.assertEqual(selected, items)

    def test_choose_export_items_uses_saved_all_exportable_behavior(self):
        items = [
            {"item_code": "A", "release_decision": "release_now"},
            {"item_code": "E", "release_decision": "export_next_business_day_for_free_day"},
        ]

        selected = export_flow.choose_export_items(
            SimpleNamespace(app_settings={"mixed_export_behavior": "all_exportable"}),
            items,
        )

        self.assertEqual([item["item_code"] for item in selected], ["A", "E"])

    def test_choose_export_items_uses_saved_immediate_only_behavior(self):
        items = [
            {"item_code": "A", "release_decision": "release_now"},
            {"item_code": "E", "release_decision": "export_next_business_day_for_free_day"},
        ]

        selected = export_flow.choose_export_items(
            SimpleNamespace(app_settings={"mixed_export_behavior": "immediate_only"}),
            items,
        )

        self.assertEqual([item["item_code"] for item in selected], ["A"])

    def test_choose_export_items_can_limit_to_immediate_items(self):
        items = [
            {"item_code": "A", "release_decision": "release_now"},
            {"item_code": "E", "release_decision": "export_next_business_day_for_free_day"},
        ]

        with patch("export_flow.messagebox.askyesnocancel", return_value=False):
            selected = export_flow.choose_export_items(
                SimpleNamespace(app_settings={"mixed_export_behavior": "ask_when_mixed"}),
                items,
            )

        self.assertEqual([item["item_code"] for item in selected], ["A"])

    def test_choose_export_items_can_export_planned_only_when_no_immediate_items_exist(self):
        items = [
            {"item_code": "E", "release_decision": "export_next_business_day_for_free_day"},
        ]

        selected = export_flow.choose_export_items(
            SimpleNamespace(app_settings={"planned_only_export_behavior": "export_automatically"}),
            items,
        )

        self.assertEqual([item["item_code"] for item in selected], ["E"])

    def test_choose_export_items_can_prompt_when_only_planned_items_exist_if_configured(self):
        items = [
            {"item_code": "E", "release_decision": "export_next_business_day_for_free_day"},
        ]

        with patch("export_flow.messagebox.askyesno", return_value=True):
            selected = export_flow.choose_export_items(
                SimpleNamespace(app_settings={"planned_only_export_behavior": "ask_before_export"}),
                items,
            )

        self.assertEqual([item["item_code"] for item in selected], ["E"])

    def test_select_export_items_supports_explicit_immediate_and_planned_modes(self):
        items = [
            {"item_code": "A", "release_decision": "release_now"},
            {"item_code": "B", "release_decision": "export_next_business_day_for_free_day"},
            {"item_code": "C", "release_decision": "hold_for_threshold"},
        ]

        immediate = export_flow.select_export_items(SimpleNamespace(), items, selection_mode="immediate_only")
        planned = export_flow.select_export_items(SimpleNamespace(), items, selection_mode="planned_only")
        all_exportable = export_flow.select_export_items(SimpleNamespace(), items, selection_mode="all_exportable")

        self.assertEqual([item["item_code"] for item in immediate], ["A"])
        self.assertEqual([item["item_code"] for item in planned], ["B"])
        self.assertEqual([item["item_code"] for item in all_exportable], ["A", "B", "C"])

    def test_choose_output_dir_uses_saved_last_export_dir_when_it_exists(self):
        app = SimpleNamespace(
            app_settings={"last_export_dir": "C:\\Exports"},
            _get_last_export_dir=lambda: "C:\\Exports",
            _set_last_export_dir=lambda path: None,
        )

        with patch("export_flow.os.path.isdir", return_value=True), \
             patch("export_flow.filedialog.askdirectory", return_value="C:\\Exports\\Next") as mocked_dir:
            output_dir = export_flow.choose_output_dir(app)

        self.assertEqual(output_dir, "C:\\Exports\\Next")
        self.assertEqual(mocked_dir.call_args.kwargs["initialdir"], "C:\\Exports")

    def test_choose_output_dir_persists_selected_folder(self):
        saved = {}
        app = SimpleNamespace(
            app_settings={},
            _get_last_export_dir=lambda: "",
            _set_last_export_dir=lambda path: saved.update({"path": path}),
        )

        with patch("export_flow.filedialog.askdirectory", return_value="C:\\Exports\\Next"):
            output_dir = export_flow.choose_output_dir(app)

        self.assertEqual(output_dir, "C:\\Exports\\Next")
        self.assertEqual(saved["path"], "C:\\Exports\\Next")

    def test_choose_output_dir_uses_app_hook_when_available(self):
        app = SimpleNamespace(_choose_output_dir=lambda: "D:\\POs")

        output_dir = export_flow.choose_output_dir(app)

        self.assertEqual(output_dir, "D:\\POs")

    def test_loaded_report_paths_prefers_app_hook(self):
        app = SimpleNamespace(
            _loaded_report_paths_for_snapshot=lambda: {
                "sales": "D:\\Reports\\sales.csv",
                "po": "D:\\Reports\\po.csv",
            }
        )

        paths = export_flow.loaded_report_paths_from_app(app)

        self.assertEqual(paths["sales"], "D:\\Reports\\sales.csv")
        self.assertEqual(paths["po"], "D:\\Reports\\po.csv")

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
        self.assertEqual(snapshot.export_scope_label, "selected items")
        self.assertEqual(snapshot.loaded_report_paths["sales"], "C:\\Reports\\sales.csv")
        self.assertEqual(snapshot.po_files, ("C:\\Exports\\PO_A.xlsx",))
        self.assertEqual(snapshot.exported_items, ())
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
            exported_items=({"line_code": "AER-", "item_code": "GH781-4", "order_qty": 250, "export_batch_type": "planned_release"},),
            export_scope_label="planned today items",
        )

        self.assertEqual(snapshot.loaded_report_paths["sales"], "C:\\Reports\\sales.csv")
        self.assertEqual(snapshot.export_scope_label, "planned today items")
        self.assertEqual(snapshot.exported_items[0]["export_batch_type"], "planned_release")
        self.assertEqual(snapshot.qoh_adjustments[0]["new"], 5)
        self.assertEqual(snapshot.order_rules["AER-:GH781-4"]["pack_size"], 500)

    def test_build_export_audit_items_tags_immediate_and_planned_exports(self):
        audited = export_flow.build_export_audit_items([
            {"item_code": "A", "release_decision": "release_now", "target_order_date": "2026-03-10", "target_release_date": "2026-03-10"},
            {"item_code": "B", "release_decision": "export_next_business_day_for_free_day", "target_order_date": "2026-03-10", "target_release_date": "2026-03-11"},
        ], "selected items")

        self.assertEqual(audited[0]["export_batch_type"], "immediate")
        self.assertEqual(audited[1]["export_batch_type"], "planned_release")
        self.assertEqual(audited[1]["export_scope_label"], "selected items")
        self.assertEqual(audited[1]["exported_for_release_date"], "2026-03-11")

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
            app_settings={"mixed_export_behavior": "ask_when_mixed"},
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
                    "item_code": "GH781-6",
                    "order_qty": 1,
                    "release_decision": "export_next_business_day_for_free_day",
                    "release_reason": "Export today so the PO is ready for vendor free-shipping day",
                },
                {
                    "vendor": "MOTION",
                    "line_code": "AER-",
                    "item_code": "GH781-5",
                    "order_qty": 3,
                    "release_decision": "hold_for_threshold",
                    "release_reason": "Held for freight threshold 2000",
                    "status": "review",
                    "target_order_date": "2026-03-12",
                    "target_release_date": "2026-03-13",
                },
            ],
            startup_warning_rows=[],
            qoh_adjustments={},
            order_rules={},
        )
        app = SimpleNamespace(
            session=session,
            app_settings={"mixed_export_behavior": "ask_when_mixed"},
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
             patch("export_flow.messagebox.askyesnocancel", return_value=True), \
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
        self.assertEqual(len(exported_items), 2)
        self.assertEqual(exported_items[0]["item_code"], "GH781-4")
        self.assertEqual(exported_items[1]["item_code"], "GH781-6")
        self.assertIn("planned-release POs", mocked_info.call_args.args[1])
        self.assertIn("were held by shipping policy and were not exported", mocked_info.call_args.args[1])
        self.assertIn("critical exceptions", mocked_info.call_args.args[1])
        self.assertIn("target order/release dates", mocked_info.call_args.args[1])

    def test_do_export_can_skip_planned_items_and_export_immediate_only(self):
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
                    "item_code": "GH781-6",
                    "order_qty": 1,
                    "release_decision": "export_next_business_day_for_free_day",
                },
            ],
            startup_warning_rows=[],
            qoh_adjustments={},
            order_rules={},
        )
        app = SimpleNamespace(
            session=session,
            app_settings={"mixed_export_behavior": "ask_when_mixed"},
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
             patch("export_flow.messagebox.askyesnocancel", return_value=False), \
             patch("export_flow.filedialog.askdirectory", return_value=tmp), \
             patch("export_flow.storage.append_order_history") as mocked_history, \
             patch("export_flow.storage.save_session_snapshot"), \
             patch("export_flow.messagebox.showinfo"):
            export_flow.do_export(
                app,
                lambda vendor, items, output_dir: str(Path(output_dir) / f"{vendor}_{len(items)}.xlsx"),
                str(Path(tmp) / "order_history.json"),
                str(Path(tmp) / "sessions"),
            )

        mocked_history.assert_called_once()
        exported_items = mocked_history.call_args.args[1]
        self.assertEqual([item["item_code"] for item in exported_items], ["GH781-4"])

    def test_do_export_can_export_planned_only_without_prompt_when_scope_is_explicit(self):
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
                    "item_code": "GH781-6",
                    "order_qty": 1,
                    "release_decision": "export_next_business_day_for_free_day",
                    "target_order_date": "2026-03-10",
                    "target_release_date": "2026-03-11",
                },
            ],
            startup_warning_rows=[],
            qoh_adjustments={},
            order_rules={},
        )
        app = SimpleNamespace(
            session=session,
            app_settings={"mixed_export_behavior": "ask_when_mixed"},
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
             patch("export_flow.messagebox.askyesnocancel") as ask_mixed, \
             patch("export_flow.messagebox.askyesno") as ask_planned, \
             patch("export_flow.filedialog.askdirectory", return_value=tmp), \
             patch("export_flow.storage.append_order_history") as mocked_history, \
             patch("export_flow.storage.save_session_snapshot"), \
             patch("export_flow.messagebox.showinfo"):
            export_flow.do_export(
                app,
                lambda vendor, items, output_dir: str(Path(output_dir) / f"{vendor}_{len(items)}.xlsx"),
                str(Path(tmp) / "order_history.json"),
                str(Path(tmp) / "sessions"),
                assigned_items=[session.assigned_items[1]],
                export_scope_label="planned today items",
                selection_mode="all_exportable",
            )

        ask_mixed.assert_not_called()
        ask_planned.assert_not_called()
        exported_items = mocked_history.call_args.args[1]
        self.assertEqual([item["item_code"] for item in exported_items], ["GH781-6"])
        self.assertEqual(exported_items[0]["export_batch_type"], "planned_release")

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
                    "status": "review",
                    "target_order_date": "2026-03-12",
                    "target_release_date": "2026-03-13",
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
        self.assertIn("critical exceptions", mocked_info.call_args.args[1])
        self.assertIn("target order 2026-03-12", mocked_info.call_args.args[1])
        self.assertIn("target release 2026-03-13", mocked_info.call_args.args[1])

    def test_do_export_can_export_scoped_vendor_items_only(self):
        session = AppSessionState(
            assigned_items=[
                {"vendor": "MOTION", "line_code": "AER-", "item_code": "GH781-4", "order_qty": 2, "release_decision": "release_now"},
                {"vendor": "SOURCE", "line_code": "AER-", "item_code": "GH781-5", "order_qty": 3, "release_decision": "release_now"},
            ],
            startup_warning_rows=[],
            qoh_adjustments={},
            order_rules={},
        )
        app = SimpleNamespace(
            session=session,
            app_settings={"mixed_export_behavior": "all_exportable"},
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

        scoped_items = [session.assigned_items[0]]
        with tempfile.TemporaryDirectory() as tmp, \
             patch("export_flow.filedialog.askdirectory", return_value=tmp), \
             patch("export_flow.storage.append_order_history") as mocked_history, \
             patch("export_flow.storage.save_session_snapshot"), \
             patch("export_flow.messagebox.showinfo"):
            export_flow.do_export(
                app,
                lambda vendor, items, output_dir: str(Path(output_dir) / f"{vendor}_{len(items)}.xlsx"),
                str(Path(tmp) / "order_history.json"),
                str(Path(tmp) / "sessions"),
                assigned_items=scoped_items,
                export_scope_label="MOTION release now items",
            )

        mocked_history.assert_called_once()
        exported_items = mocked_history.call_args.args[1]
        self.assertEqual([item["item_code"] for item in exported_items], ["GH781-4"])

    def test_do_export_uses_app_preview_hook_when_available(self):
        session = AppSessionState(
            assigned_items=[
                {"vendor": "MOTION", "line_code": "AER-", "item_code": "GH781-4", "order_qty": 2, "release_decision": "release_now"},
            ],
            startup_warning_rows=[],
            qoh_adjustments={},
            order_rules={},
        )
        preview_calls = []
        app = SimpleNamespace(
            session=session,
            _choose_output_dir=lambda: "C:\\Exports",
            _show_export_preview_dialog=lambda preview: preview_calls.append(preview) or True,
            _show_loading=lambda message: None,
            _hide_loading=lambda: None,
            _build_maintenance_report=lambda: [],
            _show_maintenance_report=lambda output_dir, issues: None,
            _loaded_report_paths_for_snapshot=lambda: {},
        )

        with patch("export_flow.storage.append_order_history"), \
             patch("export_flow.storage.save_session_snapshot"), \
             patch("export_flow.messagebox.showinfo"):
            export_flow.do_export(
                app,
                lambda vendor, items, output_dir: str(Path(output_dir) / f"{vendor}.xlsx"),
                "order_history.json",
                "sessions",
            )

        self.assertEqual(len(preview_calls), 1)
        self.assertEqual(preview_calls[0]["total_item_count"], 1)


class ExportPreviewTests(unittest.TestCase):
    def test_build_export_preview_groups_by_vendor(self):
        items = [
            {"vendor": "MOTION", "final_qty": 5, "repl_cost": 10.0, "release_decision": "release_now"},
            {"vendor": "SOURCE", "final_qty": 2, "repl_cost": 20.0, "release_decision": "release_now"},
            {"vendor": "MOTION", "final_qty": 3, "repl_cost": 5.0, "release_decision": "release_now"},
        ]
        preview = export_flow.build_export_preview(items)
        vendors = [s["vendor"] for s in preview["vendor_summaries"]]
        self.assertIn("MOTION", vendors)
        self.assertIn("SOURCE", vendors)
        motion_summary = next(s for s in preview["vendor_summaries"] if s["vendor"] == "MOTION")
        self.assertEqual(motion_summary["item_count"], 2)

    def test_build_export_preview_sums_values(self):
        items = [
            {"vendor": "MOTION", "final_qty": 5, "repl_cost": 10.0, "release_decision": "release_now"},
            {"vendor": "MOTION", "final_qty": 3, "repl_cost": 5.0, "release_decision": "release_now"},
        ]
        preview = export_flow.build_export_preview(items)
        motion_summary = next(s for s in preview["vendor_summaries"] if s["vendor"] == "MOTION")
        self.assertAlmostEqual(motion_summary["estimated_value"], 65.0)
        self.assertAlmostEqual(preview["total_estimated_value"], 65.0)
        self.assertEqual(preview["total_item_count"], 2)

    def test_build_export_preview_handles_missing_cost(self):
        items = [
            {"vendor": "MOTION", "final_qty": 5, "release_decision": "release_now"},
            {"vendor": "MOTION", "final_qty": None, "repl_cost": None, "release_decision": "release_now"},
        ]
        preview = export_flow.build_export_preview(items)
        motion_summary = next(s for s in preview["vendor_summaries"] if s["vendor"] == "MOTION")
        self.assertAlmostEqual(motion_summary["estimated_value"], 0.0)

    def test_build_export_preview_empty_items(self):
        preview = export_flow.build_export_preview([])
        self.assertEqual(preview["vendor_summaries"], [])
        self.assertEqual(preview["total_item_count"], 0)
        self.assertAlmostEqual(preview["total_estimated_value"], 0.0)

    def test_po_memo_written_to_export_rows(self):
        # Import the actual export_vendor_po from po_builder
        import sys
        sys.path.insert(0, str(ROOT))
        import po_builder
        import tempfile, openpyxl

        items = [
            {"line_code": "AER-", "item_code": "GH781-4", "order_qty": 5},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = po_builder.export_vendor_po("MOTION", items, tmp, po_memo="Test Memo")
            wb = openpyxl.load_workbook(path)
            ws = wb.active
            headers = [ws.cell(row=1, column=c).value for c in range(1, 5)]
            row2 = [ws.cell(row=2, column=c).value for c in range(1, 5)]

        self.assertIn("Notes", headers)
        self.assertEqual(row2[3], "Test Memo")

    def test_apply_vendor_scope_overrides_excludes_deferred(self):
        app = SimpleNamespace(_vendor_export_scope_overrides={"MOTION": "defer"})
        items = [
            {"vendor": "MOTION", "item_code": "A"},
            {"vendor": "SOURCE", "item_code": "B"},
        ]
        result = export_flow.apply_vendor_scope_overrides(app, items)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["item_code"], "B")

    def test_apply_vendor_scope_overrides_excludes_skipped(self):
        app = SimpleNamespace(_vendor_export_scope_overrides={"SOURCE": "skip"})
        items = [
            {"vendor": "MOTION", "item_code": "A"},
            {"vendor": "SOURCE", "item_code": "B"},
        ]
        result = export_flow.apply_vendor_scope_overrides(app, items)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["item_code"], "A")

    def test_apply_vendor_scope_overrides_includes_default(self):
        app = SimpleNamespace(_vendor_export_scope_overrides={"OTHER": "skip"})
        items = [
            {"vendor": "MOTION", "item_code": "A"},
        ]
        result = export_flow.apply_vendor_scope_overrides(app, items)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["item_code"], "A")

    def test_apply_vendor_scope_overrides_empty_overrides_includes_all(self):
        app = SimpleNamespace(_vendor_export_scope_overrides={})
        items = [
            {"vendor": "MOTION", "item_code": "A"},
            {"vendor": "SOURCE", "item_code": "B"},
        ]
        result = export_flow.apply_vendor_scope_overrides(app, items)
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
