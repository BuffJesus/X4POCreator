import copy
from collections import defaultdict
from datetime import datetime

import parsers


def parse_all_files(paths, *, old_po_warning_days, short_sales_window_days, now=None):
    """Parse the selected input files into a single workflow result."""
    warnings = []
    startup_warning_rows = []
    result = {"warnings": warnings, "startup_warning_rows": startup_warning_rows}

    result["sales_items"] = parsers.parse_part_sales_csv(paths["sales"])
    if not result["sales_items"]:
        return result

    desc_lookup = {
        (s.get("line_code", ""), s.get("item_code", "")): s.get("description", "")
        for s in result["sales_items"]
    }
    sales_start, sales_end = parsers.parse_sales_date_range(paths["sales"])
    if sales_start and sales_end:
        span_days = (sales_end.date() - sales_start.date()).days + 1
        if span_days < short_sales_window_days:
            warnings.append((
                "Sales Window Warning",
                (
                    f"Part Sales date range is only {span_days} day(s): "
                    f"{sales_start.strftime('%Y-%m-%d')} to {sales_end.strftime('%Y-%m-%d')}.\n\n"
                    "This can produce noisy reorder suggestions. You can continue, but a wider sales date range is recommended."
                ),
            ))
            startup_warning_rows.append({
                "warning_type": "Sales Window Warning",
                "severity": "warning",
                "line_code": "",
                "item_code": "",
                "description": "",
                "reference_date": f"{sales_start.strftime('%Y-%m-%d')} to {sales_end.strftime('%Y-%m-%d')}",
                "qty": "",
                "po_reference": "",
                "details": f"Sales window is {span_days} day(s), below recommended {short_sales_window_days}+.",
            })

    all_line_codes = sorted(set(item["line_code"] for item in result["sales_items"]))

    if paths["po"]:
        try:
            po_items = parsers.parse_po_listing_csv(paths["po"])
            open_po_lookup = defaultdict(list)
            for po in po_items:
                open_po_lookup[(po["line_code"], po["item_code"])].append(po)
            for po in po_items:
                if po["line_code"] not in all_line_codes:
                    all_line_codes.append(po["line_code"])
            all_line_codes = sorted(set(all_line_codes))
            result["po_items"] = po_items
            result["open_po_lookup"] = open_po_lookup

            by_key = defaultdict(list)
            for po in po_items:
                po_dt = parsers.parse_x4_date(po.get("date_issued", ""))
                if po_dt:
                    by_key[(po["line_code"], po["item_code"])].append(po)
            old_keys = []
            today = now or datetime.now()
            for key, rows in by_key.items():
                dated = [(parsers.parse_x4_date(r.get("date_issued", "")), r) for r in rows]
                dated = [(dt, r) for dt, r in dated if dt is not None]
                if not dated:
                    continue
                oldest = min(dt for dt, _ in dated)
                age_days = (today - oldest).days
                if age_days >= old_po_warning_days:
                    total_qty = sum(float(r.get("qty", 0) or 0) for _, r in dated)
                    old_keys.append((age_days, key, total_qty, [r for _, r in dated]))
            if old_keys:
                old_keys.sort(reverse=True)
                sample = "\n".join(
                    f"  {lc}/{ic}: oldest {age} days, qty {qty:g}"
                    for age, (lc, ic), qty, _ in old_keys[:8]
                )
                warnings.append((
                    "Old Open PO Warning",
                    (
                        f"{len(old_keys)} item(s) have open PO history older than "
                        f"{old_po_warning_days} days.\n"
                        "You can continue, but review these items to confirm receipt or PO closure status in X4 so you do not reorder something already received.\n\n"
                        f"Examples:\n{sample}"
                    ),
                ))
                for age, (lc, ic), qty, po_rows in old_keys:
                    refs = []
                    for po in sorted(po_rows, key=lambda x: x.get("date_issued", "")):
                        po_num = po.get("po_number", "")
                        po_type = po.get("po_type", "") or "PO"
                        po_date = po.get("date_issued", "")
                        po_qty = po.get("qty", 0)
                        if po_num:
                            refs.append(f"{po_num}/{po_type} {po_date} qty {po_qty:g}")
                        else:
                            refs.append(f"{po_type} {po_date} qty {po_qty:g}")
                    po_ref = "; ".join(refs[:8])
                    if len(refs) > 8:
                        po_ref += f"; ... +{len(refs) - 8} more"
                    startup_warning_rows.append({
                        "warning_type": "Old Open PO Warning",
                        "severity": "warning",
                        "line_code": lc,
                        "item_code": ic,
                        "description": desc_lookup.get((lc, ic), ""),
                        "reference_date": f"{age} days old",
                        "qty": f"{qty:g}",
                        "po_reference": po_ref,
                        "details": "Open PO age exceeds review threshold; verify receipt/closure in X4.",
                    })
        except Exception as exc:
            warnings.append(("PO Parse Warning", f"Could not parse PO listing:\n{exc}\nContinuing without it."))

    if paths["susp"]:
        try:
            susp_items, susp_set = parsers.parse_suspended_csv(paths["susp"])
            susp_lookup = defaultdict(list)
            for si in susp_items:
                susp_lookup[(si["line_code"], si["item_code"])].append(si)
                key = (si["line_code"], si["item_code"])
                if not desc_lookup.get(key) and si.get("description"):
                    desc_lookup[key] = si.get("description")
            for si in susp_items:
                if si["line_code"] not in all_line_codes:
                    all_line_codes.append(si["line_code"])
            all_line_codes = sorted(set(all_line_codes))
            result["suspended_items"] = susp_items
            result["suspended_set"] = susp_set
            result["suspended_lookup"] = susp_lookup
        except Exception as exc:
            warnings.append(("Suspended Parse Warning", f"Could not parse suspended items:\n{exc}\nContinuing without it."))

    inventory_lookup = {}
    if paths["onhand"]:
        try:
            oh_data = parsers.parse_on_hand_report(paths["onhand"])
            for key, info in oh_data.items():
                inventory_lookup[key] = {
                    "qoh": info["qoh"],
                    "repl_cost": info["repl_cost"],
                    "min": None,
                    "max": None,
                    "ytd_sales": 0,
                    "mo12_sales": 0,
                    "supplier": "",
                    "last_receipt": "",
                    "last_sale": "",
                }
        except Exception as exc:
            warnings.append(("On Hand Parse Warning", f"Could not parse On Hand Report:\n{exc}\nContinuing without it."))

    if paths["minmax"]:
        try:
            mm_data = parsers.parse_on_hand_min_max(paths["minmax"])
            for key, info in mm_data.items():
                existing = inventory_lookup.get(key, {})
                merged = dict(existing)
                merged.update(info)
                if info.get("qoh") is None and "qoh" in existing:
                    merged["qoh"] = existing.get("qoh")
                if info.get("repl_cost") is None and "repl_cost" in existing:
                    merged["repl_cost"] = existing.get("repl_cost")
                inventory_lookup[key] = merged
        except Exception as exc:
            warnings.append(("Min/Max Parse Warning", f"Could not parse Min/Max report:\n{exc}\nContinuing without it."))

    result["inventory_lookup"] = inventory_lookup
    if inventory_lookup:
        negative_qoh = [
            ((line_code, item_code), info)
            for (line_code, item_code), info in inventory_lookup.items()
            if isinstance(info.get("qoh"), (int, float)) and info.get("qoh", 0) < 0
        ]
        if negative_qoh:
            negative_qoh.sort(key=lambda entry: (entry[0][0], entry[0][1]))
            sample = "\n".join(
                f"  {line_code}/{item_code}: QOH {info.get('qoh', 0):g}"
                for (line_code, item_code), info in negative_qoh[:8]
            )
            warnings.append((
                "Negative QOH Warning",
                (
                    f"{len(negative_qoh)} item(s) have negative QOH in the inventory source data.\n"
                    "You can continue, but these items should be checked in X4 because suggestions may be distorted until the quantity is corrected.\n\n"
                    f"Examples:\n{sample}"
                ),
            ))
            for (line_code, item_code), info in negative_qoh:
                startup_warning_rows.append({
                    "warning_type": "Negative QOH Warning",
                    "severity": "warning",
                    "line_code": line_code,
                    "item_code": item_code,
                    "description": desc_lookup.get((line_code, item_code), ""),
                    "reference_date": "",
                    "qty": f"{info.get('qoh', 0):g}",
                    "po_reference": "",
                    "details": "Inventory source data shows negative QOH; verify the on-hand balance in X4.",
                })

        missing = [s for s in result["sales_items"] if (s["line_code"], s["item_code"]) not in inventory_lookup]
        if missing:
            missing_qty = sum(s.get("qty_sold", 0) for s in missing)
            sample = ", ".join(f"{s['line_code']}/{s['item_code']}" for s in missing[:12])
            extra = "..." if len(missing) > 12 else ""
            warnings.append((
                "Inventory Coverage Warning",
                (
                    f"{len(missing)} sales item(s) were not found in inventory/min-max data "
                    f"(total sold qty {missing_qty}).\n"
                    "Those items can still be reviewed, but their ordering guidance will be weaker until inventory/min-max data is available.\n\n"
                    f"Examples: {sample}{extra}"
                ),
            ))
            for s in missing:
                startup_warning_rows.append({
                    "warning_type": "Inventory Coverage Warning",
                    "severity": "warning",
                    "line_code": s.get("line_code", ""),
                    "item_code": s.get("item_code", ""),
                    "description": s.get("description", "") or desc_lookup.get(
                        (s.get("line_code", ""), s.get("item_code", "")), ""
                    ),
                    "reference_date": "",
                    "qty": s.get("qty_sold", 0),
                    "po_reference": "",
                    "details": "Sales item missing from inventory/min-max data.",
                })

    if paths["packsize"]:
        try:
            result["pack_size_lookup"] = parsers.parse_pack_sizes_csv(paths["packsize"])
        except Exception as exc:
            warnings.append(("Pack Size Parse Warning", f"Could not parse pack sizes:\n{exc}\nContinuing without it."))

    result["all_line_codes"] = all_line_codes
    return result


def apply_load_result(session, result, *, parsers_module=parsers):
    """Apply a parsed load result onto the current session state."""
    session.sales_items = result["sales_items"]
    session.all_line_codes = result["all_line_codes"]
    session.po_items = result.get("po_items", [])
    session.open_po_lookup = result.get("open_po_lookup", {})
    session.suspended_items = result.get("suspended_items", [])
    session.suspended_set = result.get("suspended_set", set())
    session.suspended_lookup = result.get("suspended_lookup", {})
    session.inventory_lookup = result.get("inventory_lookup", {})
    session.inventory_source_lookup = copy.deepcopy(session.inventory_lookup)
    session.pack_size_lookup = result.get("pack_size_lookup", {})
    session.pack_size_source_lookup = copy.deepcopy(session.pack_size_lookup)
    session.startup_warning_rows = result.get("startup_warning_rows", [])
    session.pack_size_by_item, session.pack_size_conflicts = parsers_module.build_pack_size_fallbacks(session.pack_size_lookup)
    return session
