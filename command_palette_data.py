"""UI-agnostic index-building and ranking for the command palette.

Extracted from ``ui_command_palette.py`` during the v0.10.0 tkinter
removal so the Qt command palette can import without pulling in tkinter.
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional


_MAX_RESULTS = 120


def _normalize(text: str) -> str:
    return str(text or "").strip().lower()


def build_item_index(filtered_items, jump_callback: Callable[[str, str], None]) -> list[dict]:
    """Index every item in the bulk grid by LC, IC, and description."""
    index = []
    for item in filtered_items or []:
        lc = str(item.get("line_code", "") or "")
        ic = str(item.get("item_code", "") or "")
        desc = str(item.get("description", "") or "")
        vendor = str(item.get("vendor", "") or "")
        haystack = _normalize(f"{lc}{ic} {lc} {ic} {desc} {vendor}")
        if not haystack:
            continue
        def make_run(_lc=lc, _ic=ic):
            return lambda: jump_callback(_lc, _ic)
        sublabel_parts = []
        if desc:
            sublabel_parts.append(desc)
        if vendor:
            sublabel_parts.append(f"vendor {vendor}")
        index.append({
            "kind": "item",
            "label": f"{lc}{ic}",
            "sublabel": " — ".join(sublabel_parts),
            "haystack": haystack,
            "run": make_run(),
            "sort_key": (lc, ic),
        })
    return index


def build_vendor_index(known_vendors, filter_callback: Callable[[str], None]) -> list[dict]:
    seen = set()
    index = []
    for vendor in known_vendors or []:
        vendor = str(vendor or "").strip()
        if not vendor or vendor in seen:
            continue
        seen.add(vendor)
        def make_run(_vendor=vendor):
            return lambda: filter_callback(_vendor)
        index.append({
            "kind": "vendor",
            "label": f"Filter: {vendor}",
            "sublabel": "Filter bulk grid to this vendor",
            "haystack": _normalize(f"{vendor} filter vendor"),
            "run": make_run(),
            "sort_key": (vendor,),
        })
    return index


def _score(entry: dict, query: str) -> Optional[int]:
    """Return a ranking score for ``entry`` given ``query``, or None if no match.

    Lower is better.  0 = prefix match on label, 10 = substring in label,
    20 = substring in haystack, 30 = no query (everything matches), None = no match.
    """
    if not query:
        return 30
    label = _normalize(entry.get("label", ""))
    haystack = entry.get("haystack", "")
    if label.startswith(query):
        return 0
    if query in label:
        return 10
    if query in haystack:
        return 20
    return None


_KIND_ORDER = {"action": 0, "item": 1, "vendor": 2}


def rank_results(query: str, *indexes: Iterable[dict], limit: int = _MAX_RESULTS) -> list[dict]:
    query_norm = _normalize(query)
    scored: list[tuple[int, int, tuple, dict]] = []
    for index in indexes:
        for entry in index:
            score = _score(entry, query_norm)
            if score is None:
                continue
            kind_rank = _KIND_ORDER.get(entry.get("kind", "item"), 9)
            scored.append((score, kind_rank, entry.get("sort_key", ()), entry))
    scored.sort(key=lambda t: (t[0], t[1], t[2]))
    return [entry for _s, _k, _sk, entry in scored[:limit]]
