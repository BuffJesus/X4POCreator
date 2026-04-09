import copy
import csv
from collections import defaultdict
from datetime import datetime
import os
import re
from tkinter import filedialog, messagebox

import perf_trace
import shipping_flow
import storage
from models import SessionSnapshot


def group_assigned_items(assigned_items):
    vendor_groups = defaultdict(list)
    for item in assigned_items:
        vendor_groups[item["vendor"]].append(item)
    return vendor_groups


def export_bucket(item):
    return shipping_flow.release_bucket(item)


def partition_export_items(assigned_items):
    exportable = []
    held = []
    for item in assigned_items:
        if export_bucket(item) == "held":
            held.append(item)
        else:
            exportable.append(item)
    return exportable, held


def held_item_summary(item):
    reason = item.get("release_reason", "Held by shipping policy")
    target_order = str(item.get("target_order_date", "") or "").strip()
    target_release = str(item.get("target_release_date", "") or "").strip()
    planning_parts = []
    if target_order:
        planning_parts.append(f"target order {target_order}")
    if target_release:
        planning_parts.append(f"target release {target_release}")
    if planning_parts:
        reason = f"{reason}; {'; '.join(planning_parts)}"
    return (
        f"  - {item.get('vendor', '')} {item.get('line_code', '')}{item.get('item_code', '')}: {reason}"
    )


def is_critical_shipping_hold(item):
    return shipping_flow.is_critical_shipping_hold(item)


def critical_held_items(held_items):
    return [item for item in held_items if is_critical_shipping_hold(item)]


def choose_export_items(app, exportable_items):
    immediate_items = [item for item in exportable_items if export_bucket(item) == "release_now"]
    planned_items = [item for item in exportable_items if export_bucket(item) == "planned_today"]
    mixed_behavior = "ask_when_mixed"
    get_behavior = getattr(app, "_get_mixed_export_behavior", None)
    if callable(get_behavior):
        mixed_behavior = get_behavior()
    else:
        settings = getattr(app, "app_settings", {}) or {}
        mixed_behavior = str(settings.get("mixed_export_behavior", "all_exportable") or "").strip() or "all_exportable"

    if not planned_items:
        return exportable_items

    if not immediate_items:
        planned_only_behavior = "export_automatically"
        get_planned_only_behavior = getattr(app, "_get_planned_only_export_behavior", None)
        if callable(get_planned_only_behavior):
            planned_only_behavior = get_planned_only_behavior()
        else:
            settings = getattr(app, "app_settings", {}) or {}
            planned_only_behavior = str(
                settings.get("planned_only_export_behavior", "export_automatically") or ""
            ).strip() or "export_automatically"

        if planned_only_behavior == "export_automatically":
            return planned_items

        proceed = messagebox.askyesno(
            "Export Planned POs?",
            (
                f"{len(planned_items)} item(s) are planned-release POs for an upcoming free-freight day.\n\n"
                "Export these planned items now?"
            ),
        )
        return planned_items if proceed else []

    if mixed_behavior == "all_exportable":
        return exportable_items
    if mixed_behavior == "immediate_only":
        return immediate_items

    choice = messagebox.askyesnocancel(
        "Export Scope",
        (
            f"{len(immediate_items)} immediate-release item(s) and {len(planned_items)} planned-release item(s) are exportable.\n\n"
            "Yes = export all exportable items\n"
            "No = export immediate-release items only\n"
            "Cancel = do nothing"
        ),
    )
    if choice is None:
        return []
    if choice:
        return exportable_items
    return immediate_items


def select_export_items(app, exportable_items, *, selection_mode="default"):
    if selection_mode == "all_exportable":
        return list(exportable_items)
    if selection_mode == "immediate_only":
        return [item for item in exportable_items if export_bucket(item) == "release_now"]
    if selection_mode == "planned_only":
        return [item for item in exportable_items if export_bucket(item) == "planned_today"]
    return choose_export_items(app, exportable_items)


def loaded_report_paths_from_app(app):
    def _value(attr_name):
        variable = getattr(app, attr_name, None)
        getter = getattr(variable, "get", None)
        return getter().strip() if callable(getter) else ""

    return {
        "sales": _value("var_sales_path"),
        "detailedsales": _value("var_detailed_sales_path"),
        "receivedparts": _value("var_received_parts_path"),
        "po": _value("var_po_path"),
        "susp": _value("var_susp_path"),
        "onhand": _value("var_onhand_path"),
        "minmax": _value("var_minmax_path"),
        "packsize": _value("var_packsize_path"),
    }


def choose_output_dir(app):
    initialdir = ""
    get_last_export_dir = getattr(app, "_get_last_export_dir", None)
    if callable(get_last_export_dir):
        initialdir = get_last_export_dir()
    elif getattr(app, "app_settings", None):
        initialdir = str(app.app_settings.get("last_export_dir", "") or "").strip()
    dialog_kwargs = {"title": "Select Output Folder for PO Files"}
    if initialdir and os.path.isdir(initialdir):
        dialog_kwargs["initialdir"] = initialdir
    output_dir = filedialog.askdirectory(**dialog_kwargs)
    if output_dir:
        set_last_export_dir = getattr(app, "_set_last_export_dir", None)
        if callable(set_last_export_dir):
            set_last_export_dir(output_dir)
        elif getattr(app, "app_settings", None) is not None:
            app.app_settings["last_export_dir"] = output_dir
    return output_dir


def build_export_audit_items(items, export_scope_label):
    audited = []
    for item in items or []:
        entry = copy.deepcopy(item)
        bucket = export_bucket(item)
        entry["export_batch_type"] = "planned_release" if bucket == "planned_today" else "immediate"
        entry["export_scope_label"] = export_scope_label
        entry["exported_for_order_date"] = str(item.get("target_order_date", "") or "").strip()
        entry["exported_for_release_date"] = str(item.get("target_release_date", "") or "").strip()
        audited.append(entry)
    return audited


@perf_trace.timed("export_flow.do_export")
def do_export(
    app,
    export_vendor_po,
    order_history_file,
    sessions_dir,
    *,
    assigned_items=None,
    export_scope_label="selected items",
    selection_mode="default",
):
    session = getattr(app, "session", app)
    source_items = list(assigned_items if assigned_items is not None else session.assigned_items)
    if not source_items:
        messagebox.showwarning("No Items", "No items to export.")
        return

    exportable_items, held_items = partition_export_items(source_items)
    critical_held = critical_held_items(held_items)
    if not exportable_items:
        if held_items:
            held_lines = "\n".join(
                held_item_summary(item)
                for item in held_items[:8]
            )
            suffix = "\n  - ..." if len(held_items) > 8 else ""
            critical_note = ""
            if critical_held:
                critical_note = (
                    f"\n\n{len(critical_held)} held item(s) are critical exceptions and should be reviewed with the "
                    "'Critical Held' release filter before waiting on shipping policy."
                )
            messagebox.showinfo(
                "No Exportable Items",
                (
                    f"All {export_scope_label} are currently held by vendor shipping policy, so no PO files were exported.\n\n"
                    f"{held_lines}{suffix}{critical_note}\n\n"
                    "These items remain visible in Review & Export until their release decision changes."
                ),
            )
        else:
            messagebox.showwarning("No Items", "No items are currently eligible for export.")
        return

    selected_export_items = select_export_items(app, exportable_items, selection_mode=selection_mode)
    if not selected_export_items:
        return

    # Reset scope overrides so the preview dialog can set them fresh
    if hasattr(app, "_vendor_export_scope_overrides"):
        app._vendor_export_scope_overrides = {}

    # Apply any pre-existing vendor scope overrides before preview
    selected_export_items = apply_vendor_scope_overrides(app, selected_export_items)
    if not selected_export_items:
        return

    # Show export preview dialog; user can set per-vendor scope overrides there
    preview = build_export_preview(selected_export_items)
    try:
        import ui_review as _ui_review
        if not _ui_review.show_export_preview_dialog(app, preview):
            return  # user cancelled
    except Exception:
        pass  # if UI not available (e.g. tests), skip preview

    # Apply vendor scope overrides set by the preview dialog
    selected_export_items = apply_vendor_scope_overrides(app, selected_export_items)
    if not selected_export_items:
        return

    audited_export_items = build_export_audit_items(selected_export_items, export_scope_label)

    planned_items = [item for item in selected_export_items if export_bucket(item) == "planned_today"]
    immediate_items = [item for item in selected_export_items if export_bucket(item) == "release_now"]

    output_dir = choose_output_dir(app)
    if not output_dir:
        return

    app._show_loading("Exporting POs...")
    app.root.update()

    vendor_groups = group_assigned_items(selected_export_items)

    created_files = []
    for vendor, items in sorted(vendor_groups.items()):
        try:
            filepath = export_vendor_po(vendor, items, output_dir)
            created_files.append(filepath)
        except Exception as exc:
            app._hide_loading()
            messagebox.showerror("Export Error", f"Failed to export PO for {vendor}:\n{exc}")
            return

    storage.append_order_history(order_history_file, audited_export_items)
    suspense_carry_result = None
    if hasattr(app, "_persist_suspense_carry"):
        suspense_carry_result = app._persist_suspense_carry()
    maintenance_issues = app._build_maintenance_report()
    session_snapshot = build_session_snapshot(
        app,
        output_dir,
        created_files,
        maintenance_issues,
        exported_items=audited_export_items,
        export_scope_label=export_scope_label,
    )
    try:
        storage.save_session_snapshot(sessions_dir, session_snapshot)
    except Exception as exc:
        app._hide_loading()
        messagebox.showerror("Session Save Error", f"Failed to save session snapshot:\n{exc}")
        return

    app._hide_loading()

    file_list = "\n".join(f"  - {os.path.basename(path)}" for path in created_files)
    shared_merge_note = ""
    if suspense_carry_result and suspense_carry_result.get("conflict"):
        shared_merge_note = (
            "\n\nShared suspense carry changed on disk during export, so PO Builder merged your update with newer shared data."
        )
    held_note = ""
    if held_items:
        dated_holds = sum(
            1 for item in held_items
            if str(item.get("target_order_date", "") or "").strip() or str(item.get("target_release_date", "") or "").strip()
        )
        held_note = f"\n\n{len(held_items)} assigned item(s) were held by shipping policy and were not exported."
        if critical_held:
            held_note += (
                f" {len(critical_held)} of those held item(s) are critical exceptions; review them with the "
                "'Critical Held' release filter."
            )
        if dated_holds:
            held_note += " Review their target order/release dates in Review & Export."
        else:
            held_note += " They remain in Review & Export with their release reason."
    planned_note = ""
    if planned_items:
        planned_note = (
            f"\n\n{len(planned_items)} assigned item(s) were exported as planned-release POs for an upcoming free-freight day."
        )
    messagebox.showinfo(
        "Export Complete",
        f"Created {len(created_files)} PO file(s) in:\n{output_dir}\n\n{file_list}\n\n"
        "Each file is ready for X4 Import from Excel.\n"
        "Remember to set the Vendor field in X4 when importing each file."
        f"\n\nImmediate-release items exported: {len(immediate_items)}"
        f"{planned_note}{shared_merge_note}{held_note}\n\n"
        "A maintenance report will open next if the app found supplier, pack, min/max, or QOH differences worth reviewing in X4.",
    )
    app._show_maintenance_report(output_dir, maintenance_issues)


def build_session_snapshot_from_state(session, loaded_report_paths, output_dir, created_files, maintenance_issues, *, exported_items=(), export_scope_label="selected items"):
    qoh_adjustments = [
        {
            "line_code": key[0],
            "item_code": key[1],
            "old": adj["old"],
            "new": adj["new"],
        }
        for key, adj in sorted(session.qoh_adjustments.items())
    ]
    return SessionSnapshot(
        created_at=datetime.now().isoformat(),
        output_dir=output_dir,
        po_files=tuple(created_files),
        export_scope_label=export_scope_label,
        loaded_report_paths=loaded_report_paths,
        exported_items=tuple(copy.deepcopy(item) for item in exported_items),
        assigned_items=tuple(copy.deepcopy(item) for item in session.assigned_items),
        maintenance_issues=tuple(maintenance_issues),
        startup_warning_rows=tuple(copy.deepcopy(row) for row in session.startup_warning_rows),
        qoh_adjustments=tuple(qoh_adjustments),
        order_rules=copy.deepcopy(session.order_rules),
    )


def build_session_snapshot(app, output_dir, created_files, maintenance_issues, *, exported_items=(), export_scope_label="selected items"):
    session = getattr(app, "session", app)
    return build_session_snapshot_from_state(
        session,
        loaded_report_paths_from_app(app),
        output_dir,
        created_files,
        maintenance_issues,
        exported_items=exported_items,
        export_scope_label=export_scope_label,
    )


def build_export_preview(items):
    """
    Build a preview summary for the given export candidate items.
    Returns a dict with vendor_summaries, total_item_count, total_estimated_value.
    """
    vendor_items = defaultdict(list)
    for item in items:
        vendor = item.get("vendor") or "UNKNOWN"
        vendor_items[vendor].append(item)

    vendor_summaries = []
    total_value = 0.0
    total_count = 0
    for vendor, vitems in sorted(vendor_items.items()):
        est_value = sum(
            (item.get("final_qty") or 0) * (item.get("repl_cost") or 0)
            for item in vitems
        )
        vendor_summaries.append({
            "vendor": vendor,
            "item_count": len(vitems),
            "estimated_value": est_value,
        })
        total_value += est_value
        total_count += len(vitems)

    return {
        "vendor_summaries": vendor_summaries,
        "total_item_count": total_count,
        "total_estimated_value": total_value,
    }


def apply_vendor_scope_overrides(app, items):
    """
    Filter items according to per-vendor scope overrides stored on app.
    Overrides dict: {vendor: "include" | "defer" | "skip"}
    "include" (default) — included in this export
    "defer" — excluded now, remains in session for a later export
    "skip" — excluded for the rest of this session
    Returns the filtered list.
    """
    overrides = getattr(app, "_vendor_export_scope_overrides", {})
    if not overrides:
        return list(items)
    return [
        item for item in items
        if overrides.get(item.get("vendor") or "", "include") == "include"
    ]


def export_maintenance_csv(issues, output_dir):
    def _clean_cell(value):
        if value is None:
            return ""
        text = str(value)
        if any(mark in text for mark in ("Ãƒ", "Ã‚", "Ã¢")):
            try:
                repaired = text.encode("cp1252", errors="ignore").decode("utf-8", errors="ignore")
                if repaired:
                    text = repaired
            except Exception:
                pass

        replacements = {
            "Ã¢â‚¬â€": "-",
            "Ã¢â‚¬â€œ": "-",
            "Ã¢â€ â€™": "->",
            "Ã¢â‚¬Â¢": "-",
            "Ã‚Â·": "-",
            "â€™": "'",
            "â€˜": "'",
            "â€œ": '"',
            "â€": '"',
            "â€”": "-",
            "â€“": "-",
            "â†’": "->",
            "â€¢": "-",
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)

        text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        text = re.sub(r"\s+", " ", text).strip()
        return text.encode("ascii", errors="ignore").decode("ascii")

    timestamp = datetime.now().strftime("%Y%m%d")
    filepath = os.path.join(output_dir, f"X4_Maintenance_{timestamp}.csv")
    with open(filepath, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "Line Code", "Item Code", "Description", "Issue",
            "Assigned Vendor", "X4 Supplier",
            "Pack Size", "X4 Order Multiple",
            "X4 Min", "X4 Max", "Target Min", "Target Max", "Suggested Min", "Suggested Max",
            "QOH (Report)", "QOH (Adjusted)",
        ])
        for row in issues:
            writer.writerow([
                _clean_cell(row.line_code),
                _clean_cell(row.item_code),
                _clean_cell(row.description),
                _clean_cell(row.issue),
                _clean_cell(row.assigned_vendor),
                _clean_cell(row.x4_supplier),
                _clean_cell(row.pack_size),
                _clean_cell(row.x4_order_multiple),
                _clean_cell(row.x4_min),
                _clean_cell(row.x4_max),
                _clean_cell(row.target_min),
                _clean_cell(row.target_max),
                _clean_cell(row.sug_min),
                _clean_cell(row.sug_max),
                _clean_cell(row.qoh_old),
                _clean_cell(row.qoh_new),
            ])
    return filepath
