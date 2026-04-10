"""Auto-assign vendors from receipt history evidence.

Scans all unassigned items after the assignment session is prepared
and fills in the vendor field from receipt_primary_vendor when the
confidence is high.  Returns a summary of what was auto-assigned
so the operator can review exceptions only.
"""

from debug_log import write_debug


def auto_assign_from_receipts(app, *, min_confidence="high"):
    """Auto-assign vendors to unassigned items with strong receipt evidence.

    Returns a dict:
        assigned_count — number of items auto-assigned
        skipped_count — number of items left unassigned
        vendor_counts — {vendor: count} of assignments made
    """
    filtered_items = getattr(app, "filtered_items", []) or []
    remember = getattr(app, "_remember_vendor_code", None)
    vendor_counts = {}
    assigned_count = 0
    skipped_count = 0

    confidence_levels = {"high"} if min_confidence == "high" else {"high", "medium"}

    for item in filtered_items:
        # Skip already-assigned items
        if item.get("vendor"):
            continue

        vendor = str(item.get("receipt_primary_vendor", "") or "").strip().upper()
        confidence = str(item.get("receipt_vendor_confidence", "") or "").strip().lower()

        if vendor and confidence in confidence_levels and not item.get("receipt_vendor_ambiguous"):
            item["vendor"] = vendor
            item["vendor_auto_assigned"] = True
            assigned_count += 1
            vendor_counts[vendor] = vendor_counts.get(vendor, 0) + 1
            if callable(remember):
                try:
                    remember(vendor)
                except Exception:
                    pass
        else:
            skipped_count += 1

    write_debug(
        "auto_assign_from_receipts.done",
        assigned=assigned_count,
        skipped=skipped_count,
        vendors=len(vendor_counts),
    )

    return {
        "assigned_count": assigned_count,
        "skipped_count": skipped_count,
        "vendor_counts": vendor_counts,
    }


def auto_assign_summary_text(result):
    """Build a human-readable summary of the auto-assign result."""
    assigned = result.get("assigned_count", 0)
    skipped = result.get("skipped_count", 0)
    vendors = result.get("vendor_counts", {})

    if assigned == 0:
        return "No items could be auto-assigned (no high-confidence receipt vendor matches)."

    top_vendors = sorted(vendors.items(), key=lambda kv: -kv[1])[:5]
    vendor_parts = ", ".join(f"{v} ({c})" for v, c in top_vendors)
    if len(vendors) > 5:
        vendor_parts += f", +{len(vendors) - 5} more"

    parts = [f"Auto-assigned {assigned} items from receipt history"]
    if skipped > 0:
        parts.append(f"{skipped} need manual assignment")
    parts.append(f"Top vendors: {vendor_parts}")
    return "  ·  ".join(parts)
