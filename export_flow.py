import copy
import csv
from collections import defaultdict
from datetime import datetime
import os
import re
from tkinter import filedialog, messagebox

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


def loaded_report_paths_from_app(app):
    return {
        "sales": app.var_sales_path.get().strip(),
        "po": app.var_po_path.get().strip(),
        "susp": app.var_susp_path.get().strip(),
        "onhand": app.var_onhand_path.get().strip(),
        "minmax": app.var_minmax_path.get().strip(),
        "packsize": app.var_packsize_path.get().strip(),
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


def do_export(app, export_vendor_po, order_history_file, sessions_dir, *, assigned_items=None, export_scope_label="selected items"):
    session = getattr(app, "session", app)
    source_items = list(assigned_items if assigned_items is not None else session.assigned_items)
    if not source_items:
        messagebox.showwarning("No Items", "No items to export.")
        return

    exportable_items, held_items = partition_export_items(source_items)
    if not exportable_items:
        if held_items:
            held_lines = "\n".join(
                f"  - {item.get('vendor', '')} {item.get('line_code', '')}{item.get('item_code', '')}: {item.get('release_reason', 'Held by shipping policy')}"
                for item in held_items[:8]
            )
            suffix = "\n  - ..." if len(held_items) > 8 else ""
            messagebox.showinfo(
                "No Exportable Items",
                (
                    f"All {export_scope_label} are currently held by vendor shipping policy, so no PO files were exported.\n\n"
                    f"{held_lines}{suffix}\n\n"
                    "These items remain visible in Review & Export until their release decision changes."
                ),
            )
        else:
            messagebox.showwarning("No Items", "No items are currently eligible for export.")
        return

    selected_export_items = choose_export_items(app, exportable_items)
    if not selected_export_items:
        return

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

    storage.append_order_history(order_history_file, selected_export_items)
    suspense_carry_result = None
    if hasattr(app, "_persist_suspense_carry"):
        suspense_carry_result = app._persist_suspense_carry()
    maintenance_issues = app._build_maintenance_report()
    session_snapshot = build_session_snapshot(
        app,
        output_dir,
        created_files,
        maintenance_issues,
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
        held_note = (
            f"\n\n{len(held_items)} assigned item(s) were held by shipping policy and were not exported. "
            "They remain in Review & Export with their release reason."
        )
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


def build_session_snapshot_from_state(session, loaded_report_paths, output_dir, created_files, maintenance_issues):
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
        loaded_report_paths=loaded_report_paths,
        assigned_items=tuple(copy.deepcopy(item) for item in session.assigned_items),
        maintenance_issues=tuple(maintenance_issues),
        startup_warning_rows=tuple(copy.deepcopy(row) for row in session.startup_warning_rows),
        qoh_adjustments=tuple(qoh_adjustments),
        order_rules=copy.deepcopy(session.order_rules),
    )


def build_session_snapshot(app, output_dir, created_files, maintenance_issues):
    session = getattr(app, "session", app)
    return build_session_snapshot_from_state(
        session,
        loaded_report_paths_from_app(app),
        output_dir,
        created_files,
        maintenance_issues,
    )


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
