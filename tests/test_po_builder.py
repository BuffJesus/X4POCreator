import sys
import unittest
import json
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import po_builder
import ui_bulk_dialogs


class POBuilderTests(unittest.TestCase):
    def _make_calc_app(self):
        fake_app = SimpleNamespace(
            inventory_lookup={},
            order_rules={},
            filtered_items=[],
            qoh_adjustments={},
            vendor_codes_used=[],
            _loaded_order_rules={},
            _loaded_vendor_codes=[],
            _suggest_min_max=lambda key: (None, None),
        )
        fake_app._find_filtered_item = lambda key: po_builder.POBuilderApp._find_filtered_item(fake_app, key)
        fake_app._normalize_vendor_code = lambda value: po_builder.POBuilderApp._normalize_vendor_code(value)
        fake_app._get_cycle_weeks = lambda: po_builder.POBuilderApp._get_cycle_weeks(fake_app)
        fake_app._get_effective_order_qty = lambda item: po_builder.POBuilderApp._get_effective_order_qty(fake_app, item)
        fake_app._set_effective_order_qty = (
            lambda item, qty, manual_override=False: po_builder.POBuilderApp._set_effective_order_qty(
                fake_app, item, qty, manual_override=manual_override
            )
        )
        fake_app._remember_vendor_code = lambda vendor: po_builder.POBuilderApp._remember_vendor_code(fake_app, vendor)
        fake_app._rename_vendor_code = (
            lambda old_vendor, new_vendor: po_builder.POBuilderApp._rename_vendor_code(fake_app, old_vendor, new_vendor)
        )
        fake_app._clear_manual_override = lambda item: po_builder.POBuilderApp._clear_manual_override(item)
        fake_app._effective_order_rule = lambda item, rule: po_builder.POBuilderApp._effective_order_rule(fake_app, item, rule)
        fake_app._recalculate_item = lambda item: po_builder.POBuilderApp._recalculate_item(fake_app, item)
        fake_app._sync_review_item_to_filtered = (
            lambda item: po_builder.POBuilderApp._sync_review_item_to_filtered(fake_app, item)
        )
        fake_app._apply_bulk_filter = lambda: po_builder.POBuilderApp._apply_bulk_filter(fake_app)
        fake_app._update_review_summary = lambda: None
        fake_app._update_bulk_summary = lambda: None
        fake_app._refresh_vendor_inputs = lambda: None
        fake_app._save_vendor_codes = lambda: None
        fake_app._data_path = lambda key: str(ROOT / f"test_{key}")
        fake_app._save_order_rules = lambda: None
        return fake_app

    def test_is_newer_version_compares_semver_tags(self):
        self.assertTrue(po_builder.is_newer_version("v1.2.4", "1.2.3"))
        self.assertFalse(po_builder.is_newer_version("v1.2.3", "1.2.3"))
        self.assertFalse(po_builder.is_newer_version("dev", "1.2.3"))

    def test_set_update_check_enabled_persists_setting(self):
        saved = {}
        fake_app = SimpleNamespace(
            var_check_updates=SimpleNamespace(get=lambda: False),
            app_settings={},
            _save_app_settings=lambda: saved.update({"called": True}),
        )

        po_builder.POBuilderApp._set_update_check_enabled(fake_app)

        self.assertFalse(fake_app.update_check_enabled)
        self.assertFalse(fake_app.app_settings["check_for_updates_on_startup"])
        self.assertTrue(saved["called"])

    def test_start_update_check_skips_non_release_versions(self):
        fake_app = SimpleNamespace(update_check_enabled=True)
        fake_app._check_for_updates_worker = lambda: self.fail("worker should not run")

        with patch("po_builder.APP_VERSION", "dev"), patch("po_builder.threading.Thread") as mocked_thread:
            po_builder.POBuilderApp._start_update_check(fake_app)

        mocked_thread.assert_not_called()

    def test_fetch_latest_github_release_parses_expected_fields(self):
        payload = {
            "tag_name": "v1.2.3",
            "html_url": "https://github.com/BuffJesus/X4POCreator/releases/tag/v1.2.3",
            "name": "PO Builder 1.2.3",
            "published_at": "2026-03-11T12:00:00Z",
        }

        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def read(self):
                return json.dumps(payload).encode("utf-8")

        with patch("po_builder.urllib.request.urlopen", return_value=FakeResponse()):
            release = po_builder.fetch_latest_github_release("https://example.com/releases/latest", timeout=1)

        self.assertEqual(release["tag_name"], "v1.2.3")
        self.assertEqual(release["name"], "PO Builder 1.2.3")

    def test_load_app_version_falls_back_to_bundled_version_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundled = Path(tmp) / "VERSION"
            bundled.write_text("0.1.8\n", encoding="utf-8")

            with patch("po_builder._BUNDLE_DIR", tmp):
                version = po_builder.load_app_version(path=str(Path(tmp) / "missing-version"))

        self.assertEqual(version, "0.1.8")

    def test_load_app_version_returns_internal_version_when_no_version_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("po_builder._BUNDLE_DIR", tmp):
                version = po_builder.load_app_version(path=str(Path(tmp) / "missing-version"))

        self.assertEqual(version, po_builder.INTERNAL_APP_VERSION)

    def test_default_vendor_for_key_uses_supplier(self):
        fake_app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"supplier": "motion "}},
        )

        result = po_builder.POBuilderApp._default_vendor_for_key(fake_app, ("AER-", "GH781-4"))

        self.assertEqual(result, "MOTION")

    def test_default_vendor_for_key_returns_blank_without_supplier(self):
        fake_app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"supplier": ""}},
        )

        result = po_builder.POBuilderApp._default_vendor_for_key(fake_app, ("AER-", "GH781-4"))

        self.assertEqual(result, "")

    def test_suggest_min_max_skips_sparse_history(self):
        fake_app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"mo12_sales": 2}},
            _get_cycle_weeks=lambda: 2,
        )

        result = po_builder.POBuilderApp._suggest_min_max(fake_app, ("AER-", "GH781-4"))

        self.assertEqual(result, (None, None))

    def test_suggest_min_max_uses_cycle_for_non_sparse_history(self):
        fake_app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"mo12_sales": 26}},
            _get_cycle_weeks=lambda: 2,
        )

        result = po_builder.POBuilderApp._suggest_min_max(fake_app, ("AER-", "GH781-4"))

        self.assertEqual(result, (1, 2))

    def test_proceed_to_assign_surfaces_assignment_errors_and_hides_loading(self):
        events = []
        fake_app = SimpleNamespace(
            session=SimpleNamespace(),
            excluded_line_codes=set(),
            excluded_customers=set(),
            dup_whitelist=set(),
            var_lookback_days=SimpleNamespace(get=lambda: 14),
            _data_path=lambda key: str(ROOT / f"test_{key}"),
            _get_suspense_carry_qty=lambda key: 0,
            _default_vendor_for_key=lambda key: "",
            _resolve_pack_size=lambda key: None,
            _suggest_min_max=lambda key: (None, None),
            _show_loading=lambda message: events.append(("show", message)),
            _hide_loading=lambda: events.append(("hide", None)),
            _refresh_vendor_inputs=lambda: events.append(("refresh", None)),
            _populate_bulk_tree=lambda: events.append(("populate", None)),
            notebook=SimpleNamespace(
                tab=lambda *args, **kwargs: events.append(("tab", args, kwargs)),
                select=lambda *args, **kwargs: events.append(("select", args, kwargs)),
            ),
            root=SimpleNamespace(update=lambda: events.append(("update", None))),
        )

        with patch("po_builder.assignment_flow.prepare_assignment_session", side_effect=RuntimeError("boom")), \
             patch("po_builder.messagebox.showerror") as mocked_error:
            po_builder.POBuilderApp._proceed_to_assign(fake_app)

        mocked_error.assert_called_once()
        self.assertIn(("show", "Crunching numbers..."), events)
        self.assertIn(("hide", None), events)
        self.assertNotIn(("refresh", None), events)
        self.assertNotIn(("populate", None), events)

    def test_ignore_items_by_keys_persists_and_removes_from_active_collections(self):
        fake_app = SimpleNamespace(
            ignored_item_keys=set(),
            _loaded_ignored_item_keys=set(),
            filtered_items=[
                {"line_code": "AER-", "item_code": "GH781-4"},
                {"line_code": "MOT-", "item_code": "ABC123"},
            ],
            assigned_items=[{"line_code": "AER-", "item_code": "GH781-4"}],
            individual_items=[{"line_code": "AER-", "item_code": "GH781-4"}],
            _save_ignored_item_keys=lambda: None,
            _apply_bulk_filter=lambda: None,
            _update_bulk_summary=lambda: None,
        )
        fake_app._ignore_key = lambda lc, ic: po_builder.POBuilderApp._ignore_key(lc, ic)

        removed = po_builder.POBuilderApp._ignore_items_by_keys(fake_app, {"AER-:GH781-4"})

        self.assertEqual(removed, 1)
        self.assertIn("AER-:GH781-4", fake_app.ignored_item_keys)
        self.assertEqual(fake_app.filtered_items, [{"line_code": "MOT-", "item_code": "ABC123"}])
        self.assertEqual(fake_app.assigned_items, [])
        self.assertEqual(fake_app.individual_items, [])

    def test_refresh_data_folder_labels_updates_all_visible_data_source_labels(self):
        class Label:
            def __init__(self):
                self.text = None

            def config(self, *, text):
                self.text = text

        fake_app = SimpleNamespace(
            shared_data_dir="C:\\Shared",
            data_dir="C:\\Shared",
            lbl_data_source=Label(),
            lbl_bulk_data_source=Label(),
            lbl_assign_data_source=Label(),
            lbl_review_data_source=Label(),
        )
        fake_app._active_data_folder_label = lambda: po_builder.POBuilderApp._active_data_folder_label(fake_app)

        po_builder.POBuilderApp._refresh_data_folder_labels(fake_app)

        self.assertEqual(fake_app.lbl_data_source.text, "Shared Folder: C:\\Shared")
        self.assertEqual(fake_app.lbl_bulk_data_source.text, "Shared Folder: C:\\Shared")
        self.assertEqual(fake_app.lbl_assign_data_source.text, "Shared Folder: C:\\Shared")
        self.assertEqual(fake_app.lbl_review_data_source.text, "Shared Folder: C:\\Shared")

    def test_refresh_active_data_state_without_session_only_reloads_persistent_state(self):
        events = []
        fake_app = SimpleNamespace(
            filtered_items=[],
            assigned_items=[],
            individual_items=[],
            _load_persistent_state=lambda: events.append("load"),
            _refresh_vendor_inputs=lambda: events.append("vendors"),
        )
        fake_app._has_active_assignment_session = lambda: po_builder.POBuilderApp._has_active_assignment_session(fake_app)

        with patch("po_builder.messagebox.showinfo") as mocked_info:
            result = po_builder.POBuilderApp._refresh_active_data_state(fake_app)

        self.assertEqual(events, ["load", "vendors"])
        self.assertEqual(result, {"session_updated": False, "ignored_changed_session": False})
        mocked_info.assert_called_once()

    def test_refresh_active_data_state_updates_session_and_prunes_ignored(self):
        events = []
        filtered = [
            {
                "line_code": "AER-",
                "item_code": "GH781-4",
                "pack_size": None,
                "vendor": "MOTION",
                "final_qty": 6,
                "order_qty": 6,
            },
            {
                "line_code": "MOT-",
                "item_code": "ABC123",
                "pack_size": 4,
                "vendor": "SOURCE",
                "final_qty": 4,
                "order_qty": 4,
            },
        ]
        assigned = [{
            "line_code": "MOT-",
            "item_code": "ABC123",
            "pack_size": 4,
            "vendor": "SOURCE",
            "order_qty": 4,
            "final_qty": 4,
        }]
        fake_app = SimpleNamespace(
            filtered_items=filtered,
            assigned_items=assigned,
            individual_items=[{"line_code": "AER-", "item_code": "GH781-4"}],
            ignored_item_keys={"AER-:GH781-4"},
            dup_whitelist=set(),
            inventory_lookup={
                ("AER-", "GH781-4"): {"qoh": 1},
                ("ALT-", "ABC123"): {"qoh": 2},
                ("MOT-", "ABC123"): {"qoh": 3},
            },
            order_rules={"MOT-:ABC123": {"pack_size": 8}},
            recent_orders={},
            data_dir=str(ROOT),
            assign_index=0,
            var_lookback_days=SimpleNamespace(get=lambda: 21),
            _load_persistent_state=lambda: events.append("load"),
            _refresh_vendor_inputs=lambda: events.append("vendors"),
            _resolve_pack_size=lambda key: 12,
            _recalculate_item=lambda item: item.update({"recalculated": True}),
            _sync_review_item_to_filtered=lambda item: item.update({"synced": True}),
            _populate_assign_item=lambda: events.append("assign"),
            _apply_bulk_filter=lambda: events.append("bulk"),
            _update_bulk_summary=lambda: events.append("summary"),
            _populate_review_tab=lambda: events.append("review"),
            _data_path=lambda key: str(ROOT / f"test_{key}"),
            tree=object(),
        )
        fake_app._ignore_key = lambda lc, ic: po_builder.POBuilderApp._ignore_key(lc, ic)
        fake_app._prune_ignored_items_from_session = lambda: po_builder.POBuilderApp._prune_ignored_items_from_session(fake_app)
        fake_app._rebuild_duplicate_ic_lookup = lambda: po_builder.POBuilderApp._rebuild_duplicate_ic_lookup(fake_app)
        fake_app._has_active_assignment_session = lambda: po_builder.POBuilderApp._has_active_assignment_session(fake_app)

        with patch("po_builder.storage.get_recent_orders", return_value={("MOT-", "ABC123"): [{"qty": 2}]}), \
             patch("po_builder.messagebox.showinfo") as mocked_info:
            result = po_builder.POBuilderApp._refresh_active_data_state(fake_app)

        self.assertEqual(fake_app.filtered_items, [filtered[1]])
        self.assertEqual(fake_app.individual_items, [])
        self.assertEqual(fake_app.filtered_items[0]["pack_size"], 8)
        self.assertTrue(fake_app.assigned_items[0]["synced"])
        self.assertIn("ABC123", fake_app.duplicate_ic_lookup)
        self.assertEqual(fake_app.recent_orders[("MOT-", "ABC123")][0]["qty"], 2)
        self.assertEqual(events, ["load", "vendors", "bulk", "summary", "review"])
        self.assertEqual(result, {"session_updated": True, "ignored_changed_session": True})
        mocked_info.assert_called_once()

    def test_set_shared_data_folder_refreshes_current_session_when_individual_items_exist(self):
        events = []
        fake_app = SimpleNamespace(
            data_dir=str(ROOT),
            shared_data_dir="",
            filtered_items=[],
            assigned_items=[],
            individual_items=[{"line_code": "AER-", "item_code": "GH781-4"}],
            app_settings={},
            _build_data_paths=lambda path: {"order_rules": str(Path(path) / "order_rules.json")},
            _save_app_settings=lambda: events.append("save"),
            _refresh_active_data_state=lambda notify=False: events.append(("refresh", notify)) or {"session_updated": True},
        )

        with patch("po_builder.filedialog.askdirectory", return_value=str(ROOT / "SharedData")), \
             patch("po_builder.storage.validate_storage_directory", return_value=(True, "")), \
             patch("po_builder.messagebox.showinfo") as mocked_info:
            po_builder.POBuilderApp._set_shared_data_folder(fake_app)

        self.assertEqual(fake_app.shared_data_dir, str((ROOT / "SharedData").resolve()))
        self.assertEqual(fake_app.data_dir, str((ROOT / "SharedData").resolve()))
        self.assertEqual(fake_app.app_settings["shared_data_dir"], str((ROOT / "SharedData").resolve()))
        self.assertEqual(events, ["save", ("refresh", False)])
        mocked_info.assert_called_once()
        self.assertIn("refreshed the current session", mocked_info.call_args.args[1])

    def test_use_local_data_folder_refreshes_current_session_when_individual_items_exist(self):
        events = []
        fake_app = SimpleNamespace(
            shared_data_dir=str(ROOT / "SharedData"),
            data_dir=str(ROOT / "SharedData"),
            filtered_items=[],
            assigned_items=[],
            individual_items=[{"line_code": "AER-", "item_code": "GH781-4"}],
            app_settings={"shared_data_dir": str(ROOT / "SharedData")},
            _build_data_paths=lambda path: {"order_rules": str(Path(path) / "order_rules.json")},
            _save_app_settings=lambda: events.append("save"),
            _refresh_active_data_state=lambda notify=False: events.append(("refresh", notify)) or {"session_updated": True},
        )

        with patch("po_builder.messagebox.showinfo") as mocked_info:
            po_builder.POBuilderApp._use_local_data_folder(fake_app)

        self.assertEqual(fake_app.shared_data_dir, "")
        self.assertEqual(fake_app.data_dir, po_builder.LOCAL_DATA_DIR)
        self.assertEqual(fake_app.app_settings["shared_data_dir"], "")
        self.assertEqual(events, ["save", ("refresh", False)])
        mocked_info.assert_called_once()
        self.assertIn("refreshed the current session", mocked_info.call_args.args[1])

    def test_refresh_suggestions_recalculates_filtered_and_assigned_items(self):
        fake_app = self._make_calc_app()
        key = ("AER-", "GH781-4")
        filtered_item = {
            "line_code": key[0],
            "item_code": key[1],
            "description": "HOSE",
            "qty_sold": 10,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 10,
            "vendor": "MOTION",
            "pack_size": 5,
            "final_qty": 5,
            "order_qty": 5,
        }
        assigned_item = dict(filtered_item)
        fake_app.inventory_lookup[key] = {"qoh": 0, "max": 2, "mo12_sales": 52}
        fake_app.filtered_items = [filtered_item]
        fake_app.assigned_items = [assigned_item]
        fake_app.var_reorder_cycle = SimpleNamespace(get=lambda: "Monthly")
        fake_app._suggest_min_max = lambda item_key: po_builder.POBuilderApp._suggest_min_max(fake_app, item_key)
        fake_app.var_bulk_lc_filter = SimpleNamespace(get=lambda: "ALL")
        fake_app.var_bulk_status_filter = SimpleNamespace(get=lambda: "ALL")
        fake_app.var_bulk_source_filter = SimpleNamespace(get=lambda: "ALL")
        fake_app.var_bulk_item_status = SimpleNamespace(get=lambda: "ALL")
        fake_app.bulk_sheet = None

        po_builder.POBuilderApp._refresh_suggestions(fake_app)

        self.assertEqual(filtered_item["suggested_min"], 4)
        self.assertEqual(filtered_item["suggested_max"], 8)
        self.assertEqual(filtered_item["suggested_qty"], 10)
        self.assertEqual(filtered_item["final_qty"], 10)
        self.assertIn("Target stock: 8", filtered_item["why"])
        self.assertEqual(assigned_item["suggested_qty"], 10)
        self.assertEqual(assigned_item["order_qty"], 10)

    def test_review_pack_size_edit_persists_order_rule(self):
        fake_app = self._make_calc_app()
        key = ("AER-", "GH781-4")
        filtered_item = {
            "line_code": key[0],
            "item_code": key[1],
            "description": "HOSE",
            "qty_sold": 8,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 8,
            "vendor": "MOTION",
            "pack_size": 6,
            "final_qty": 12,
            "order_qty": 12,
        }
        assigned_item = dict(filtered_item)
        fake_app.inventory_lookup[key] = {"qoh": 0, "max": 10, "mo12_sales": 26}
        fake_app.filtered_items = [filtered_item]
        fake_app.assigned_items = [assigned_item]
        saved = {}
        fake_app._save_order_rules = lambda: saved.update({"payload": dict(fake_app.order_rules)})

        po_builder.POBuilderApp._review_apply_editor_value(fake_app, "0", "pack_size", "12")

        self.assertEqual(assigned_item["pack_size"], 12)
        self.assertEqual(filtered_item["pack_size"], 12)
        self.assertEqual(fake_app.order_rules["AER-:GH781-4"]["pack_size"], 12)
        self.assertEqual(saved["payload"]["AER-:GH781-4"]["pack_size"], 12)

    def test_quantity_helpers_keep_fields_aligned(self):
        fake_app = self._make_calc_app()
        item = {"order_qty": 7}

        self.assertEqual(po_builder.POBuilderApp._get_effective_order_qty(fake_app, item), 7)
        po_builder.POBuilderApp._set_effective_order_qty(fake_app, item, 3, manual_override=True)

        self.assertEqual(item["final_qty"], 3)
        self.assertEqual(item["order_qty"], 3)
        self.assertTrue(item["manual_override"])

    def test_quantity_helper_clamps_negative_qty_to_zero(self):
        fake_app = self._make_calc_app()
        item = {"order_qty": 7}

        po_builder.POBuilderApp._set_effective_order_qty(fake_app, item, -12, manual_override=True)

        self.assertEqual(item["final_qty"], 0)
        self.assertEqual(item["order_qty"], 0)
        self.assertTrue(item["manual_override"])

    def test_remember_vendor_code_normalizes_and_sorts(self):
        fake_app = self._make_calc_app()
        fake_app.vendor_codes_used = ["MOTION"]

        result = po_builder.POBuilderApp._remember_vendor_code(fake_app, "gregdist")

        self.assertEqual(result, "GREGDIST")
        self.assertEqual(fake_app.vendor_codes_used, ["GREGDIST", "MOTION"])

    def test_rename_vendor_code_updates_current_session_items(self):
        fake_app = self._make_calc_app()
        fake_app.vendor_codes_used = ["GREGDIST", "MOTION"]
        fake_app.filtered_items = [{"vendor": "GREGDIST"}]
        fake_app.individual_items = [{"vendor": "GREGDIST"}]
        fake_app.assigned_items = [{"vendor": "GREGDIST"}]

        result = po_builder.POBuilderApp._rename_vendor_code(fake_app, "gregdist", "source")

        self.assertEqual(result, "SOURCE")
        self.assertEqual(fake_app.vendor_codes_used, ["MOTION", "SOURCE"])
        self.assertEqual(fake_app.filtered_items[0]["vendor"], "SOURCE")
        self.assertEqual(fake_app.individual_items[0]["vendor"], "SOURCE")
        self.assertEqual(fake_app.assigned_items[0]["vendor"], "SOURCE")

    def test_bulk_qoh_edit_recalculates_item_fields(self):
        fake_app = self._make_calc_app()
        key = ("AER-", "GH781-4")
        fake_app.inventory_lookup[key] = {"qoh": 2, "max": 10}
        fake_app.filtered_items = [{
            "line_code": key[0],
            "item_code": key[1],
            "description": "HOSE",
            "qty_sold": 8,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 8,
            "pack_size": 4,
            "final_qty": 8,
            "order_qty": 8,
        }]

        po_builder.POBuilderApp._bulk_apply_editor_value(fake_app, "0", "qoh", "10")

        item = fake_app.filtered_items[0]
        self.assertEqual(fake_app.qoh_adjustments[key]["new"], 10.0)
        self.assertEqual(item["raw_need"], 0)
        self.assertEqual(item["final_qty"], 0)
        self.assertEqual(item["status"], "skip")
        self.assertIn("inventory_covers_target", item["data_flags"])

    def test_bulk_final_qty_edit_preserves_override_and_recalculates_context(self):
        fake_app = self._make_calc_app()
        key = ("AER-", "GH781-4")
        fake_app.inventory_lookup[key] = {"qoh": 2, "max": 10}
        fake_app.filtered_items = [{
            "line_code": key[0],
            "item_code": key[1],
            "description": "HOSE",
            "qty_sold": 8,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 8,
            "pack_size": 4,
            "final_qty": 8,
            "order_qty": 8,
        }]

        po_builder.POBuilderApp._bulk_apply_editor_value(fake_app, "0", "final_qty", "3")

        item = fake_app.filtered_items[0]
        self.assertTrue(item["manual_override"])
        self.assertEqual(item["raw_need"], 8)
        self.assertEqual(item["final_qty"], 3)
        self.assertEqual(item["order_qty"], 3)
        self.assertIn("Target stock: 10", item["why"])

    def test_review_qty_edit_syncs_and_recalculates_status(self):
        fake_app = self._make_calc_app()
        key = ("AER-", "GH781-4")
        filtered_item = {
            "line_code": key[0],
            "item_code": key[1],
            "description": "HOSE",
            "qty_sold": 9,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 9,
            "vendor": "MOTION",
            "pack_size": 6,
            "final_qty": 12,
            "order_qty": 12,
        }
        fake_app.inventory_lookup[key] = {"qoh": 0, "max": 10}
        fake_app.filtered_items = [filtered_item]
        po_builder.POBuilderApp._recalculate_item(fake_app, filtered_item)
        fake_app.assigned_items = [{
            "line_code": key[0],
            "item_code": key[1],
            "description": "HOSE",
            "vendor": "MOTION",
            "pack_size": filtered_item["pack_size"],
            "order_qty": filtered_item["order_qty"],
            "status": filtered_item["status"],
            "why": filtered_item["why"],
            "order_policy": filtered_item["order_policy"],
            "data_flags": list(filtered_item["data_flags"]),
        }]

        po_builder.POBuilderApp._review_apply_editor_value(fake_app, "0", "order_qty", "0")

        assigned = fake_app.assigned_items[0]
        self.assertEqual(filtered_item["final_qty"], 0)
        self.assertEqual(assigned["final_qty"], 0)
        self.assertEqual(assigned["status"], "warning")
        self.assertIn("zero_final", assigned["data_flags"])

    def test_review_negative_qty_edit_is_clamped_to_zero(self):
        fake_app = self._make_calc_app()
        key = ("AER-", "GH781-4")
        filtered_item = {
            "line_code": key[0],
            "item_code": key[1],
            "description": "HOSE",
            "qty_sold": 9,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 9,
            "vendor": "MOTION",
            "pack_size": 6,
            "final_qty": 12,
            "order_qty": 12,
        }
        fake_app.inventory_lookup[key] = {"qoh": 0, "max": 10}
        fake_app.filtered_items = [filtered_item]
        po_builder.POBuilderApp._recalculate_item(fake_app, filtered_item)
        fake_app.assigned_items = [{
            "line_code": key[0],
            "item_code": key[1],
            "description": "HOSE",
            "vendor": "MOTION",
            "pack_size": filtered_item["pack_size"],
            "order_qty": filtered_item["order_qty"],
            "status": filtered_item["status"],
            "why": filtered_item["why"],
            "order_policy": filtered_item["order_policy"],
            "data_flags": list(filtered_item["data_flags"]),
        }]

        po_builder.POBuilderApp._review_apply_editor_value(fake_app, "0", "order_qty", "-12")

        assigned = fake_app.assigned_items[0]
        self.assertEqual(filtered_item["final_qty"], 0)
        self.assertEqual(assigned["final_qty"], 0)
        self.assertEqual(assigned["order_qty"], 0)

    def test_bulk_cur_max_edit_recalculates_raw_need(self):
        fake_app = self._make_calc_app()
        key = ("AER-", "GH781-4")
        fake_app.inventory_lookup[key] = {"qoh": 2, "min": 1, "max": 6}
        fake_app.filtered_items = [{
            "line_code": key[0],
            "item_code": key[1],
            "description": "HOSE",
            "qty_sold": 8,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 8,
            "pack_size": 4,
            "final_qty": 4,
            "order_qty": 4,
        }]
        po_builder.POBuilderApp._recalculate_item(fake_app, fake_app.filtered_items[0])

        po_builder.POBuilderApp._bulk_apply_editor_value(fake_app, "0", "cur_max", "14")

        item = fake_app.filtered_items[0]
        self.assertEqual(fake_app.inventory_lookup[key]["max"], 14)
        self.assertEqual(item["raw_need"], 12)
        self.assertEqual(item["final_qty"], 12)
        self.assertEqual(item["target_stock"], 14)

    def test_bulk_pack_size_edit_recalculates_qty_and_persists_rule(self):
        fake_app = self._make_calc_app()
        key = ("AER-", "GH781-4")
        fake_app.inventory_lookup[key] = {"qoh": 0, "max": 10}
        fake_app.filtered_items = [{
            "line_code": key[0],
            "item_code": key[1],
            "description": "HOSE",
            "qty_sold": 9,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 9,
            "pack_size": 5,
            "final_qty": 10,
            "order_qty": 10,
            "manual_override": True,
        }]
        po_builder.POBuilderApp._recalculate_item(fake_app, fake_app.filtered_items[0])

        saved_rules = {}
        fake_app._save_order_rules = lambda: po_builder.POBuilderApp._save_order_rules(fake_app)
        original_save = po_builder.storage.save_order_rules
        try:
            po_builder.storage.save_order_rules = (
                lambda path, rules, base_rules=None: {"payload": dict(saved_rules, **rules), "meta": None, "conflict": False}
            )
            po_builder.POBuilderApp._bulk_apply_editor_value(fake_app, "0", "pack_size", "6")
        finally:
            po_builder.storage.save_order_rules = original_save

        saved_rules.update(fake_app.order_rules)

        item = fake_app.filtered_items[0]
        self.assertEqual(item["pack_size"], 6)
        self.assertFalse(item["manual_override"])
        self.assertEqual(item["suggested_qty"], 12)
        self.assertEqual(item["final_qty"], 12)
        self.assertEqual(item["order_qty"], 12)
        self.assertEqual(fake_app.order_rules["AER-:GH781-4"]["pack_size"], 6)
        self.assertEqual(saved_rules["AER-:GH781-4"]["pack_size"], 6)

    def test_bulk_pack_size_edit_moves_exact_qty_item_to_pack_rounded_qty(self):
        fake_app = self._make_calc_app()
        key = ("GDY-", "5VX560")
        fake_app.inventory_lookup[key] = {"qoh": 1, "max": 3}
        fake_app.filtered_items = [{
            "line_code": key[0],
            "item_code": key[1],
            "description": "BELT",
            "qty_sold": 2,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 2,
            "pack_size": None,
            "final_qty": 2,
            "order_qty": 2,
        }]
        po_builder.POBuilderApp._recalculate_item(fake_app, fake_app.filtered_items[0])

        po_builder.POBuilderApp._bulk_apply_editor_value(fake_app, "0", "pack_size", "3")

        item = fake_app.filtered_items[0]
        self.assertEqual(item["order_policy"], "standard")
        self.assertEqual(item["raw_need"], 2)
        self.assertEqual(item["suggested_qty"], 3)
        self.assertEqual(item["final_qty"], 3)
        self.assertEqual(item["order_qty"], 3)

    def test_bulk_pack_size_edit_clears_stale_exact_policy_rule(self):
        fake_app = self._make_calc_app()
        key = ("GDY-", "5VX560")
        fake_app.inventory_lookup[key] = {"qoh": 1, "max": 3}
        fake_app.order_rules = {"GDY-:5VX560": {"order_policy": "exact_qty"}}
        fake_app.filtered_items = [{
            "line_code": key[0],
            "item_code": key[1],
            "description": "BELT",
            "qty_sold": 2,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 2,
            "pack_size": None,
            "final_qty": 2,
            "order_qty": 2,
        }]

        po_builder.POBuilderApp._bulk_apply_editor_value(fake_app, "0", "pack_size", "3")

        item = fake_app.filtered_items[0]
        self.assertEqual(item["order_policy"], "standard")
        self.assertEqual(item["suggested_qty"], 3)
        self.assertEqual(item["final_qty"], 3)
        self.assertEqual(fake_app.order_rules["GDY-:5VX560"]["pack_size"], 3)
        self.assertNotIn("order_policy", fake_app.order_rules["GDY-:5VX560"])

    def test_buy_rule_save_allow_below_pack_uses_soft_pack_without_locked_standard(self):
        fake_app = self._make_calc_app()
        fake_app.root = SimpleNamespace()
        fake_app._autosize_dialog = lambda *args, **kwargs: None
        fake_app._bulk_row_values = lambda item: ("",)
        fake_app.bulk_sheet = SimpleNamespace(refresh_row=lambda row_id, values: None)
        fake_app._apply_bulk_filter = lambda: None
        fake_app._update_bulk_summary = lambda: None
        key = ("GDY-", "5VX560")
        fake_app.inventory_lookup[key] = {"qoh": 0, "max": 3}
        fake_app.filtered_items = [{
            "line_code": key[0],
            "item_code": key[1],
            "description": "BELT",
            "qty_sold": 3,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 3,
            "pack_size": 12,
            "final_qty": 12,
            "order_qty": 12,
            "order_policy": "standard",
            "suggested_qty": 12,
            "raw_need": 3,
        }]
        fake_app.order_rules = {}

        created_buttons = {}

        class FakeWidget:
            def __init__(self, *args, **kwargs):
                pass
            def pack(self, *args, **kwargs):
                return self
            def grid(self, *args, **kwargs):
                return self
            def configure(self, *args, **kwargs):
                return self
            config = configure
            def bind(self, *args, **kwargs):
                return self
            def insert(self, *args, **kwargs):
                return self
            def destroy(self):
                return None
            def wait_window(self):
                return None
            def transient(self, *args, **kwargs):
                return self
            def grab_set(self, *args, **kwargs):
                return self
            def title(self, *args, **kwargs):
                return self

        class FakeTopLevel(FakeWidget):
            def configure(self, *args, **kwargs):
                return self

        class FakeStringVar:
            queue = []
            def __init__(self, value=""):
                self.value = FakeStringVar.queue.pop(0) if FakeStringVar.queue else value
            def get(self):
                return self.value
            def set(self, value):
                self.value = value

        class FakeBooleanVar:
            queue = []
            def __init__(self, value=False):
                self.value = FakeBooleanVar.queue.pop(0) if FakeBooleanVar.queue else value
            def get(self):
                return self.value
            def set(self, value):
                self.value = value

        class FakeEntry(FakeWidget):
            values = []
            def __init__(self, *args, **kwargs):
                self.value = FakeEntry.values.pop(0) if FakeEntry.values else ""
            def insert(self, index, text):
                if not self.value:
                    self.value = text
            def get(self):
                return self.value

        class FakeButton(FakeWidget):
            def __init__(self, *args, **kwargs):
                self.command = kwargs.get("command")
                text = kwargs.get("text", "")
                created_buttons[text] = self

        FakeStringVar.queue = ["standard", "2", "12"]
        FakeBooleanVar.queue = [True]
        FakeEntry.values = [""]

        with patch("ui_bulk_dialogs.tk.Toplevel", FakeTopLevel), \
             patch("ui_bulk_dialogs.ttk.Label", lambda *args, **kwargs: FakeWidget()), \
             patch("ui_bulk_dialogs.ttk.LabelFrame", lambda *args, **kwargs: FakeWidget()), \
             patch("ui_bulk_dialogs.ttk.Combobox", lambda *args, **kwargs: FakeWidget()), \
             patch("ui_bulk_dialogs.ttk.Checkbutton", lambda *args, **kwargs: FakeWidget()), \
             patch("ui_bulk_dialogs.ttk.Entry", FakeEntry), \
             patch("ui_bulk_dialogs.ttk.Frame", lambda *args, **kwargs: FakeWidget()), \
             patch("ui_bulk_dialogs.ttk.Button", FakeButton), \
             patch("ui_bulk_dialogs.tk.StringVar", FakeStringVar), \
             patch("ui_bulk_dialogs.tk.BooleanVar", FakeBooleanVar), \
             patch("ui_bulk_dialogs.storage.save_order_rules", lambda *args, **kwargs: None):
            ui_bulk_dialogs.open_buy_rule_editor(fake_app, 0, po_builder.ORDER_RULES_FILE)
            created_buttons["Save Rule"].command()

        item = fake_app.filtered_items[0]
        self.assertEqual(item["order_policy"], "soft_pack")
        self.assertEqual(item["suggested_qty"], 4)
        self.assertEqual(item["final_qty"], 4)
        self.assertTrue(fake_app.order_rules["GDY-:5VX560"]["allow_below_pack"])
        self.assertEqual(fake_app.order_rules["GDY-:5VX560"]["min_order_qty"], 2)
        self.assertNotIn("order_policy", fake_app.order_rules["GDY-:5VX560"])

    def test_buy_rule_save_persists_trigger_and_overstock_fields(self):
        fake_app = self._make_calc_app()
        fake_app.root = SimpleNamespace()
        fake_app._autosize_dialog = lambda *args, **kwargs: None
        fake_app._bulk_row_values = lambda item: ("",)
        fake_app.bulk_sheet = SimpleNamespace(refresh_row=lambda row_id, values: None)
        fake_app._apply_bulk_filter = lambda: None
        fake_app._update_bulk_summary = lambda: None
        key = ("AER-", "GH781-4")
        fake_app.inventory_lookup[key] = {"qoh": 0, "max": 18}
        fake_app.filtered_items = [{
            "line_code": key[0],
            "item_code": key[1],
            "description": "HOSE",
            "qty_sold": 12,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 12,
            "pack_size": 12,
            "final_qty": 12,
            "order_qty": 12,
            "order_policy": "standard",
            "suggested_qty": 12,
            "raw_need": 12,
        }]
        fake_app.order_rules = {}

        created_buttons = {}

        class FakeWidget:
            def __init__(self, *args, **kwargs):
                pass
            def pack(self, *args, **kwargs):
                return self
            def grid(self, *args, **kwargs):
                return self
            def configure(self, *args, **kwargs):
                return self
            config = configure
            def bind(self, *args, **kwargs):
                return self
            def insert(self, *args, **kwargs):
                return self
            def destroy(self):
                return None
            def wait_window(self):
                return None
            def transient(self, *args, **kwargs):
                return self
            def grab_set(self, *args, **kwargs):
                return self
            def title(self, *args, **kwargs):
                return self

        class FakeTopLevel(FakeWidget):
            def configure(self, *args, **kwargs):
                return self

        class FakeStringVar:
            queue = []
            def __init__(self, value=""):
                self.value = FakeStringVar.queue.pop(0) if FakeStringVar.queue else value
            def get(self):
                return self.value
            def set(self, value):
                self.value = value

        class FakeBooleanVar:
            queue = []
            def __init__(self, value=False):
                self.value = FakeBooleanVar.queue.pop(0) if FakeBooleanVar.queue else value
            def get(self):
                return self.value
            def set(self, value):
                self.value = value

        class FakeEntry(FakeWidget):
            values = []
            def __init__(self, *args, **kwargs):
                self.value = FakeEntry.values.pop(0) if FakeEntry.values else ""
            def insert(self, index, text):
                if not self.value:
                    self.value = text
            def get(self):
                return self.value

        class FakeButton(FakeWidget):
            def __init__(self, *args, **kwargs):
                self.command = kwargs.get("command")
                text = kwargs.get("text", "")
                created_buttons[text] = self

        FakeStringVar.queue = ["standard", "2", "12", "60", "20", "12", "10"]
        FakeBooleanVar.queue = [False]
        FakeEntry.values = [""]

        with patch("ui_bulk_dialogs.tk.Toplevel", FakeTopLevel), \
             patch("ui_bulk_dialogs.ttk.Label", lambda *args, **kwargs: FakeWidget()), \
             patch("ui_bulk_dialogs.ttk.LabelFrame", lambda *args, **kwargs: FakeWidget()), \
             patch("ui_bulk_dialogs.ttk.Combobox", lambda *args, **kwargs: FakeWidget()), \
             patch("ui_bulk_dialogs.ttk.Checkbutton", lambda *args, **kwargs: FakeWidget()), \
             patch("ui_bulk_dialogs.ttk.Entry", FakeEntry), \
             patch("ui_bulk_dialogs.ttk.Frame", lambda *args, **kwargs: FakeWidget()), \
             patch("ui_bulk_dialogs.ttk.Button", FakeButton), \
             patch("ui_bulk_dialogs.tk.StringVar", FakeStringVar), \
             patch("ui_bulk_dialogs.tk.BooleanVar", FakeBooleanVar), \
             patch("ui_bulk_dialogs.storage.save_order_rules", lambda *args, **kwargs: None):
            ui_bulk_dialogs.open_buy_rule_editor(fake_app, 0, po_builder.ORDER_RULES_FILE)
            created_buttons["Save Rule"].command()

        saved_rule = fake_app.order_rules["AER-:GH781-4"]
        self.assertEqual(saved_rule["reorder_trigger_qty"], 60)
        self.assertEqual(saved_rule["reorder_trigger_pct"], 20.0)
        self.assertEqual(saved_rule["acceptable_overstock_qty"], 12)
        self.assertEqual(saved_rule["acceptable_overstock_pct"], 10.0)
        self.assertEqual(fake_app.filtered_items[0]["reorder_trigger_qty"], 60)
        self.assertEqual(fake_app.filtered_items[0]["acceptable_overstock_qty"], 12)

    def test_review_pack_size_edit_recalculates_order_qty(self):
        fake_app = self._make_calc_app()
        key = ("AER-", "GH781-4")
        filtered_item = {
            "line_code": key[0],
            "item_code": key[1],
            "description": "HOSE",
            "qty_sold": 9,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 9,
            "vendor": "MOTION",
            "pack_size": 5,
            "final_qty": 10,
            "order_qty": 10,
            "manual_override": True,
        }
        fake_app.inventory_lookup[key] = {"qoh": 0, "max": 10}
        fake_app.filtered_items = [filtered_item]
        po_builder.POBuilderApp._recalculate_item(fake_app, filtered_item)
        fake_app.assigned_items = [{
            "line_code": key[0],
            "item_code": key[1],
            "description": "HOSE",
            "vendor": "MOTION",
            "pack_size": filtered_item["pack_size"],
            "order_qty": filtered_item["order_qty"],
            "final_qty": filtered_item["final_qty"],
            "status": filtered_item["status"],
            "why": filtered_item["why"],
            "order_policy": filtered_item["order_policy"],
            "data_flags": list(filtered_item["data_flags"]),
            "manual_override": True,
        }]

        po_builder.POBuilderApp._review_apply_editor_value(fake_app, "0", "pack_size", "6")

        assigned = fake_app.assigned_items[0]
        self.assertFalse(filtered_item["manual_override"])
        self.assertEqual(filtered_item["pack_size"], 6)
        self.assertEqual(filtered_item["final_qty"], 12)
        self.assertEqual(assigned["final_qty"], 12)
        self.assertEqual(assigned["order_qty"], 12)

if __name__ == "__main__":
    unittest.main()
