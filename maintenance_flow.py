from models import ItemKey, MaintenanceCandidate, SessionItemState, SourceItemState, SuggestedItemState


def build_maintenance_candidates(
    session,
    *,
    suggest_min_max,
    get_x4_pack_size,
):
    """Build maintenance candidates from merged session and source state."""
    seen_keys = set()
    items_by_key = {}
    for item in session.filtered_items:
        items_by_key[(item["line_code"], item["item_code"])] = dict(item)
    for item in session.assigned_items:
        key = (item["line_code"], item["item_code"])
        merged = dict(items_by_key.get(key, {}))
        merged.update(item)
        items_by_key[key] = merged
    items = list(items_by_key.values()) if items_by_key else list(session.assigned_items)
    candidates = []

    for item in items:
        key = (item["line_code"], item["item_code"])
        seen_keys.add(key)
        x4_inv = session.inventory_source_lookup.get(key, {})
        live_inv = session.inventory_lookup.get(key, {})
        other_lcs = session.duplicate_ic_lookup.get(item["item_code"], set())
        others = tuple(sorted(lc for lc in other_lcs if lc != item["line_code"]))
        sug_min, sug_max = suggest_min_max(key)
        qoh_adj = session.qoh_adjustments.get(key)
        candidates.append(
            MaintenanceCandidate(
                key=ItemKey(item["line_code"], item["item_code"]),
                source=SourceItemState(
                    supplier=x4_inv.get("supplier", ""),
                    order_multiple=get_x4_pack_size(key),
                    min_qty=x4_inv.get("min"),
                    max_qty=x4_inv.get("max"),
                ),
                session=SessionItemState(
                    description=item.get("description", ""),
                    vendor=item.get("vendor", ""),
                    pack_size=item.get("pack_size"),
                    target_min=live_inv.get("min"),
                    target_max=live_inv.get("max"),
                    qoh_old=qoh_adj["old"] if qoh_adj else None,
                    qoh_new=qoh_adj["new"] if qoh_adj else None,
                    data_flags=tuple(item.get("data_flags", [])),
                    order_policy=item.get("order_policy", ""),
                    duplicate_line_codes=others,
                ),
                suggested=SuggestedItemState(
                    min_qty=sug_min,
                    max_qty=sug_max,
                ),
            )
        )

    for key, adj in session.qoh_adjustments.items():
        if key in seen_keys:
            continue
        x4_inv = session.inventory_source_lookup.get(key, {})
        live_inv = session.inventory_lookup.get(key, {})
        candidates.append(
            MaintenanceCandidate(
                key=ItemKey(key[0], key[1]),
                source=SourceItemState(
                    supplier=x4_inv.get("supplier", ""),
                    order_multiple=get_x4_pack_size(key),
                    min_qty=x4_inv.get("min"),
                    max_qty=x4_inv.get("max"),
                ),
                session=SessionItemState(
                    description="",
                    target_min=live_inv.get("min"),
                    target_max=live_inv.get("max"),
                    qoh_old=adj["old"],
                    qoh_new=adj["new"],
                ),
                suggested=SuggestedItemState(),
            )
        )

    return candidates
