import copy
from collections import defaultdict
from datetime import datetime

import parsers
import performance_flow
import sales_history_flow


def _sales_line_code_candidates(item_code, *, inventory_lookup, receipt_history_lookup):
    return sorted({
        line_code
        for (line_code, current_item_code) in (inventory_lookup or {})
        if current_item_code == item_code and line_code
    } | {
        line_code
        for (line_code, current_item_code) in (receipt_history_lookup or {})
        if current_item_code == item_code and line_code
    })


def _resolve_sales_line_code(item_code, *, inventory_lookup, receipt_history_lookup):
    candidates = _sales_line_code_candidates(
        item_code,
        inventory_lookup=inventory_lookup,
        receipt_history_lookup=receipt_history_lookup,
    )
    if len(candidates) == 1:
        return candidates[0]
    return ""


def _normalize_detailed_sales_keys(sales_items, detailed_sales_stats_lookup, *, inventory_lookup, receipt_history_lookup):
    normalized_items = {}
    corrected_rows = 0
    corrected_items = set()
    for item in sales_items or []:
        line_code = item.get("line_code", "") or ""
        item_code = item.get("item_code", "") or ""
        if item_code:
            resolved_line_code = _resolve_sales_line_code(
                item_code,
                inventory_lookup=inventory_lookup,
                receipt_history_lookup=receipt_history_lookup,
            )
            if not line_code:
                line_code = resolved_line_code
            elif resolved_line_code and line_code != resolved_line_code:
                line_code = resolved_line_code
                corrected_rows += 1
                corrected_items.add(item_code)
        key = (line_code, item_code)
        entry = normalized_items.setdefault(key, {
            "line_code": line_code,
            "item_code": item_code,
            "description": "",
            "qty_received": 0,
            "qty_sold": 0,
        })
        entry["qty_received"] += max(0, int(item.get("qty_received", 0) or 0))
        entry["qty_sold"] += max(0, int(item.get("qty_sold", 0) or 0))
        if not entry["description"] and item.get("description"):
            entry["description"] = item.get("description", "")

    normalized_stats = {}
    for (line_code, item_code), stats in (detailed_sales_stats_lookup or {}).items():
        resolved_line_code = _resolve_sales_line_code(
            item_code,
            inventory_lookup=inventory_lookup,
            receipt_history_lookup=receipt_history_lookup,
        )
        target_line_code = line_code or resolved_line_code
        if line_code and resolved_line_code and line_code != resolved_line_code:
            target_line_code = resolved_line_code
        normalized_stats[(target_line_code, item_code)] = stats
    return list(normalized_items.values()), normalized_stats, {
        "row_count": corrected_rows,
        "item_count": len(corrected_items),
        "item_codes": sorted(corrected_items),
    }


def _summarize_unresolved_detailed_sales_rows(detailed_sales_rows, *, inventory_lookup, receipt_history_lookup):
    unresolved_by_item = {}
    unresolved_row_count = 0
    for row in detailed_sales_rows or []:
        line_code = str(row.get("line_code", "") or "").strip()
        item_code = str(row.get("item_code", "") or "").strip()
        if not item_code or line_code:
            continue
        resolved_line_code = _resolve_sales_line_code(
            item_code,
            inventory_lookup=inventory_lookup,
            receipt_history_lookup=receipt_history_lookup,
        )
        if resolved_line_code:
            continue
        unresolved_row_count += 1
        entry = unresolved_by_item.setdefault(item_code, {
            "item_code": item_code,
            "description": str(row.get("description", "") or "").strip(),
            "row_count": 0,
            "qty_sold": 0,
        })
        entry["row_count"] += 1
        entry["qty_sold"] += max(0, int(row.get("qty_sold", 0) or 0))
    unresolved_items = sorted(
        unresolved_by_item.values(),
        key=lambda item: (-item["row_count"], -item["qty_sold"], item["item_code"]),
    )
    return {
        "row_count": unresolved_row_count,
        "item_count": len(unresolved_items),
        "items": unresolved_items,
    }


def _summarize_conflicting_detailed_sales_rows(detailed_sales_rows, *, inventory_lookup, receipt_history_lookup):
    conflicting_by_item = {}
    conflicting_row_count = 0
    inventory_lookup = inventory_lookup or {}
    receipt_history_lookup = receipt_history_lookup or {}
    for row in detailed_sales_rows or []:
        parsed_line_code = str(row.get("line_code", "") or "").strip()
        item_code = str(row.get("item_code", "") or "").strip()
        if not item_code or not parsed_line_code:
            continue
        known_candidates = _sales_line_code_candidates(
            item_code,
            inventory_lookup=inventory_lookup,
            receipt_history_lookup=receipt_history_lookup,
        )
        if not known_candidates or parsed_line_code in known_candidates:
            continue
        if len(known_candidates) == 1:
            continue
        conflicting_row_count += 1
        entry = conflicting_by_item.setdefault((parsed_line_code, item_code), {
            "line_code": parsed_line_code,
            "item_code": item_code,
            "description": str(row.get("description", "") or "").strip(),
            "row_count": 0,
            "qty_sold": 0,
            "known_line_codes": known_candidates,
        })
        entry["row_count"] += 1
        entry["qty_sold"] += max(0, int(row.get("qty_sold", 0) or 0))
    conflicting_items = sorted(
        conflicting_by_item.values(),
        key=lambda item: (-item["row_count"], -item["qty_sold"], item["line_code"], item["item_code"]),
    )
    return {
        "row_count": conflicting_row_count,
        "item_count": len(conflicting_items),
        "items": conflicting_items,
    }


def _parse_sales_inputs(paths):
    sales_path = str(paths.get("sales", "") or "").strip()
    detailed_sales_path = str(paths.get("detailedsales", "") or "").strip()
    received_parts_path = str(paths.get("receivedparts", "") or "").strip()

    if detailed_sales_path and received_parts_path:
        detailed_sales_rows = parsers.parse_detailed_part_sales_csv(detailed_sales_path)
        received_rows = parsers.parse_received_parts_detail_csv(received_parts_path)
        return {
            "sales_source_mode": "detailed_pair",
            "detailed_sales_rows": detailed_sales_rows,
            "sales_items": parsers.build_sales_receipt_summary(detailed_sales_rows, received_rows),
            "sales_window": parsers.parse_detailed_sales_date_range(detailed_sales_rows),
            "receipt_history_lookup": parsers.build_receipt_history_lookup(received_rows),
            "detailed_sales_stats_lookup": parsers.build_detailed_sales_stats_lookup(detailed_sales_rows),
        }

    if sales_path:
        return {
            "sales_source_mode": "legacy_combined",
            "detailed_sales_rows": [],
            "sales_items": parsers.parse_part_sales_csv(sales_path),
            "sales_window": parsers.parse_sales_date_range(sales_path),
            "receipt_history_lookup": {},
            "detailed_sales_stats_lookup": {},
        }

    return {
        "sales_source_mode": "none",
        "detailed_sales_rows": [],
        "sales_items": [],
        "sales_window": (None, None),
        "receipt_history_lookup": {},
        "detailed_sales_stats_lookup": {},
    }


def parse_all_files(paths, *, old_po_warning_days, short_sales_window_days, now=None):
    """Parse the selected input files into a single workflow result."""
    warnings = []
    startup_warning_rows = []
    result = {"warnings": warnings, "startup_warning_rows": startup_warning_rows}

    sales_inputs = _parse_sales_inputs(paths)
    result["sales_source_mode"] = sales_inputs.get("sales_source_mode", "none")
    result["detailed_sales_resolution"] = {"row_count": 0, "item_count": 0, "items": []}
    result["detailed_sales_corrections"] = {"row_count": 0, "item_count": 0, "item_codes": []}
    result["detailed_sales_conflicts"] = {"row_count": 0, "item_count": 0, "items": []}
    result["sales_items"] = sales_inputs["sales_items"]
    result["receipt_history_lookup"] = sales_inputs.get("receipt_history_lookup", {})
    result["detailed_sales_stats_lookup"] = sales_inputs.get("detailed_sales_stats_lookup", {})
    if not result["sales_items"]:
        return result

    desc_lookup = {
        (s.get("line_code", ""), s.get("item_code", "")): s.get("description", "")
        for s in result["sales_items"]
    }
    sales_start, sales_end = sales_inputs["sales_window"]
    if sales_start and sales_end:
        span_days = (sales_end.date() - sales_start.date()).days + 1
        result["sales_span_days"] = span_days
        result["sales_window_start"] = sales_start.date().isoformat()
        result["sales_window_end"] = sales_end.date().isoformat()
        for entry in result["detailed_sales_stats_lookup"].values():
            qty_total = float(entry.get("qty_sold_total", 0) or 0)
            entry["annualized_qty_sold"] = (qty_total * 365.25) / float(span_days) if span_days > 0 else None
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

    if result["sales_source_mode"] == "legacy_combined":
        warnings.append((
            "Legacy Sales Source",
            (
                "Using the legacy Part Sales & Receipts report as a compatibility fallback.\n\n"
                "The preferred workflow is Detailed Part Sales + Received Parts Detail, which provides "
                "stronger vendor, receipt, and demand-shape evidence."
            ),
        ))

    all_line_codes = sorted(set(item["line_code"] for item in result["sales_items"]))

    if paths.get("po"):
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

    if paths.get("susp"):
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
    if paths.get("onhand"):
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

    if paths.get("minmax"):
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
    result["sales_items"], result["detailed_sales_stats_lookup"], result["detailed_sales_corrections"] = _normalize_detailed_sales_keys(
        result["sales_items"],
        result["detailed_sales_stats_lookup"],
        inventory_lookup=inventory_lookup,
        receipt_history_lookup=result["receipt_history_lookup"],
    )
    if result["sales_source_mode"] == "detailed_pair":
        corrections = result["detailed_sales_corrections"]
        if corrections["row_count"] > 0:
            sample = ", ".join(corrections["item_codes"][:8])
            extra = "..." if corrections["item_count"] > 8 else ""
            warnings.append((
                "Detailed Sales Line-Code Correction",
                (
                    f"{corrections['row_count']} detailed sales row(s) across {corrections['item_count']} item code(s) "
                    "were auto-corrected to a uniquely supported line code using inventory/receipt-history evidence.\n\n"
                    f"Examples: {sample}{extra}"
                ),
            ))
        result["detailed_sales_resolution"] = _summarize_unresolved_detailed_sales_rows(
            sales_inputs.get("detailed_sales_rows", []),
            inventory_lookup=inventory_lookup,
            receipt_history_lookup=result["receipt_history_lookup"],
        )
        result["detailed_sales_conflicts"] = _summarize_conflicting_detailed_sales_rows(
            sales_inputs.get("detailed_sales_rows", []),
            inventory_lookup=inventory_lookup,
            receipt_history_lookup=result["receipt_history_lookup"],
        )
        unresolved = result["detailed_sales_resolution"]
        if unresolved["row_count"] > 0:
            sample = ", ".join(item["item_code"] for item in unresolved["items"][:8])
            extra = "..." if unresolved["item_count"] > 8 else ""
            warnings.append((
                "Detailed Sales Resolution Warning",
                (
                    f"{unresolved['row_count']} detailed sales row(s) across {unresolved['item_count']} item code(s) "
                    "could not be matched to a line code after inventory and receipt-history resolution.\n\n"
                    "These rows remain excluded from line-code-specific downstream logic until they can be matched.\n\n"
                    f"Examples: {sample}{extra}"
                ),
            ))
            startup_warning_rows.append({
                "warning_type": "Detailed Sales Resolution Warning",
                "severity": "warning",
                "line_code": "",
                "item_code": "",
                "description": "",
                "reference_date": "",
                "qty": str(unresolved["row_count"]),
                "po_reference": "",
                "details": (
                    f"{unresolved['item_count']} unresolved item code(s). "
                    f"Examples: {sample}{extra}"
                ),
            })
        conflicts = result["detailed_sales_conflicts"]
        if conflicts["row_count"] > 0:
            sample = ", ".join(
                f"{item['line_code']}/{item['item_code']}"
                for item in conflicts["items"][:8]
            )
            extra = "..." if conflicts["item_count"] > 8 else ""
            warnings.append((
                "Detailed Sales Line-Code Conflict Warning",
                (
                    f"{conflicts['row_count']} detailed sales row(s) across {conflicts['item_count']} parsed item key(s) "
                    "disagree with known inventory or receipt-history line codes for the same item code.\n\n"
                    "This suggests the combined detailed-sales token may not always split cleanly at the first hyphen.\n\n"
                    f"Examples: {sample}{extra}"
                ),
            ))
            startup_warning_rows.append({
                "warning_type": "Detailed Sales Line-Code Conflict Warning",
                "severity": "warning",
                "line_code": "",
                "item_code": "",
                "description": "",
                "reference_date": "",
                "qty": str(conflicts["row_count"]),
                "po_reference": "",
                "details": (
                    f"{conflicts['item_count']} conflicting parsed item key(s). "
                    f"Examples: {sample}{extra}"
                ),
            })
    sales_history_flow.annotate_sales_items(
        result["sales_items"],
        inventory_lookup=inventory_lookup,
        sales_span_days=result.get("sales_span_days"),
        parse_date=parsers.parse_x4_date,
        now=now,
    )
    for item in result["sales_items"]:
        stats = result["detailed_sales_stats_lookup"].get((item.get("line_code", ""), item.get("item_code", "")), {})
        if stats:
            item.update(stats)
    performance_flow.annotate_items(
        result["sales_items"],
        inventory_lookup=inventory_lookup,
    )
    all_line_codes = sorted(set(
        [line_code for line_code in all_line_codes if line_code] +
        [item.get("line_code", "") for item in result["sales_items"] if item.get("line_code", "")]
    ))
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

    if paths.get("packsize"):
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
    session.receipt_history_lookup = result.get("receipt_history_lookup", {})
    session.detailed_sales_stats_lookup = result.get("detailed_sales_stats_lookup", {})
    session.pack_size_lookup = result.get("pack_size_lookup", {})
    session.pack_size_source_lookup = copy.deepcopy(session.pack_size_lookup)
    session.startup_warning_rows = result.get("startup_warning_rows", [])
    session.sales_span_days = result.get("sales_span_days")
    session.sales_window_start = result.get("sales_window_start", "")
    session.sales_window_end = result.get("sales_window_end", "")
    session.pack_size_by_item, session.pack_size_conflicts = parsers_module.build_pack_size_fallbacks(session.pack_size_lookup)
    return session
