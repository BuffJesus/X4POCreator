"""Qt table model for the bulk assignment grid.

Wraps ``session.filtered_items`` (a list of dicts) behind a
``QAbstractTableModel`` so ``QTableView`` can display 63K+ items with
native scrolling performance.  A ``QSortFilterProxyModel`` subclass
handles text search + dropdown filters without touching the source data.

Column definitions are shared with the tkinter build via the same
tuple/dict literals so both UIs stay in lock-step.

Performance notes (from CLAUDE.md):
- Never put O(n) scans inside per-item hot loops.
- The model's ``data()`` method is called per-visible-cell on every
  scroll frame — keep it O(1) with no allocation.
- Row value tuples are cached by generation counter (same pattern as
  ``ui_bulk.cached_bulk_row_values``).
"""

from __future__ import annotations

import json
from typing import Any, Optional, Sequence

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
)

import theme as t
from debug_log import write_debug

# ─── Column definitions (mirrored from ui_bulk.py) ────────────────────────

COLUMNS = (
    "vendor", "line_code", "item_code", "description", "source",
    "status", "raw_need", "suggested_qty", "final_qty", "buy_rule",
    "qoh", "cur_min", "cur_max", "sug_min", "sug_max",
    "pack_size", "supplier", "why", "notes", "risk",
)

LABELS = {
    "vendor": "Vendor", "line_code": "LC", "item_code": "Item Code",
    "description": "Description", "source": "Src", "status": "Status",
    "raw_need": "Qty Needed Before Pack", "suggested_qty": "Suggested Qty",
    "final_qty": "Final Qty", "buy_rule": "Buy Rule",
    "qoh": "QOH", "cur_min": "Min", "cur_max": "Max",
    "sug_min": "Sug Min", "sug_max": "Sug Max", "pack_size": "Pack",
    "supplier": "Supplier", "why": "Why This Qty", "notes": "Notes",
    "risk": "Risk",
}

WIDTHS = {
    "vendor": 80, "line_code": 48, "item_code": 92, "description": 150,
    "source": 40, "status": 52, "raw_need": 44, "suggested_qty": 54,
    "final_qty": 64, "buy_rule": 72, "qoh": 44, "cur_min": 44,
    "cur_max": 44, "sug_min": 48, "sug_max": 48, "pack_size": 40,
    "supplier": 72, "why": 180, "notes": 100, "risk": 44,
}

EDITABLE_COLS = frozenset({"vendor", "final_qty", "qoh", "cur_min", "cur_max", "pack_size", "notes"})

# Columns hidden by default — matches tkinter's ADHD-friendly defaults.
DEFAULT_HIDDEN = frozenset({
    "raw_need", "sug_min", "sug_max", "source", "supplier",
    "risk", "buy_rule", "cur_min", "cur_max",
})

COL_INDEX = {name: idx for idx, name in enumerate(COLUMNS)}


# ─── Row value builder ────────────────────────────────────────────────────

def _item_source(item: dict) -> str:
    has_sales = item.get("qty_sold", 0) > 0
    has_susp = item.get("qty_suspended", 0) > 0
    return "Both" if (has_sales and has_susp) else ("Susp" if has_susp else "Sales")


def _short_why(item: dict) -> str:
    """Concise why summary for the grid cell."""
    raw = item.get("raw_need", 0) or 0
    suggested = item.get("suggested_qty", 0) or 0
    final = item.get("final_qty", 0) or 0
    pack = item.get("pack_size")
    policy = item.get("order_policy", "")
    status = item.get("status", "")
    inv = item.get("inventory") or {}
    qoh = inv.get("qoh", 0) or 0
    target = item.get("target_stock", 0) or 0
    position = item.get("inventory_position", 0) or 0

    if status == "skip" or (raw <= 0 and final <= 0):
        if item.get("stale_demand_below_threshold"):
            ann = item.get("annualized_demand", 0)
            return f"Very low demand ({ann:.1f}/yr) — not worth ordering"
        if position >= target and target > 0:
            return f"Stock OK ({int(position)} on hand, target {int(target)})"
        return "No order needed"
    if policy == "manual_only":
        reason = item.get("recency_review_bucket", "")
        if reason == "stale_or_likely_dead":
            return "Needs review — may be dead stock"
        if reason == "new_or_sparse":
            return "Needs review — new or low-volume item"
        if reason == "receipt_heavy_unverified":
            return "Needs review — more received than sold"
        return "Needs review before ordering"
    if policy in ("reel_review", "large_pack_review"):
        return f"Needs review — large pack ({pack or '?'} per pack, need {raw})"

    parts = []
    if raw > 0:
        parts.append(f"Low stock: have {int(position)}, need {int(target)}")
    if suggested != raw and suggested > 0 and pack:
        parts.append(f"ordering {suggested} (pack of {pack})")
    elif suggested > 0:
        parts.append(f"ordering {suggested}")
    if item.get("zero_demand_min_protection"):
        parts.append("no recent sales, ordering to min")
    if item.get("reorder_trigger_high_vs_max"):
        parts.append("trigger much higher than max")
    return " \u2192 ".join(parts) if parts else item.get("why", "")[:80]


def build_row_values(item: dict, inventory_lookup: dict, order_rules: dict,
                     suggest_min_max_fn=None) -> tuple:
    """Build display-value tuple for one item.  Matches ui_bulk.bulk_row_values."""
    line_code = item["line_code"]
    item_code = item["item_code"]
    key = (line_code, item_code)
    inventory = inventory_lookup.get(key) or {}
    supplier = inventory.get("supplier", "")
    qoh = inventory.get("qoh", "")
    if qoh not in ("", None):
        qoh = f"{qoh:g}"
    else:
        qoh = ""
    cur_min = inventory.get("min")
    cur_max = inventory.get("max")
    if suggest_min_max_fn is not None:
        sug_min, sug_max = suggest_min_max_fn(key)
    else:
        sug_min, sug_max = None, None
    pack_size = item.get("pack_size")
    source = _item_source(item)
    status = item.get("status", "").upper()[:6]
    raw_need = item.get("raw_need", item.get("order_qty", 0))
    suggested_qty = item.get("suggested_qty", raw_need)
    final_qty = item.get("final_qty", item.get("order_qty", 0))
    rule_key = f"{line_code}:{item_code}"
    rule = order_rules.get(rule_key)
    try:
        from rules import get_buy_rule_summary
        buy_rule = get_buy_rule_summary(item, rule)
    except ImportError:
        buy_rule = ""
    why = _short_why(item)
    notes = item.get("notes", "")
    risk_score = item.get("stockout_risk_score")
    risk_display = f"{int(round(risk_score * 100))}%" if isinstance(risk_score, float) else ""
    return (
        item.get("vendor", ""),      # 0  vendor
        line_code,                    # 1  line_code
        item_code,                    # 2  item_code
        item["description"],          # 3  description
        source,                       # 4  source
        status,                       # 5  status
        raw_need,                     # 6  raw_need
        suggested_qty,                # 7  suggested_qty
        final_qty,                    # 8  final_qty
        buy_rule,                     # 9  buy_rule
        qoh,                          # 10 qoh
        cur_min if cur_min is not None else "",   # 11
        cur_max if cur_max is not None else "",   # 12
        sug_min if sug_min is not None else "",   # 13
        sug_max if sug_max is not None else "",   # 14
        pack_size if pack_size else "",           # 15
        supplier,                     # 16 supplier
        why,                          # 17 why
        notes,                        # 18 notes
        risk_display,                 # 19 risk
    )


def bulk_row_id(item: dict) -> str:
    """Canonical row ID — matches ui_bulk.bulk_row_id."""
    key = (item.get("line_code", ""), item.get("item_code", ""))
    cached_key = item.get("_bulk_row_id_key")
    cached_row_id = item.get("_bulk_row_id")
    if cached_key == key and cached_row_id:
        return cached_row_id
    row_id = json.dumps([key[0], key[1]], separators=(",", ":"))
    item["_bulk_row_id_key"] = key
    item["_bulk_row_id"] = row_id
    return row_id


# ─── Row zone (for tinting) ──────────────────────────────────────────────

def row_zone(item: dict) -> str:
    """Return the zone name for row tinting.  Mirrors BulkSheetView._apply_row_colors."""
    status = str(item.get("status", "")).strip().upper()
    vendor = str(item.get("vendor", "")).strip()
    if vendor and status not in ("REVIEW", "WARN", "WARNING"):
        return "assigned"
    if status == "REVIEW":
        return "review"
    if status in ("WARN", "WARNING"):
        return "warning"
    if status == "SKIP":
        return "skip"
    return ""


# Custom role for row tint color — used by the delegate.
ROW_TINT_ROLE = Qt.UserRole + 1
ITEM_DICT_ROLE = Qt.UserRole + 2


# ─── Table model ──────────────────────────────────────────────────────────

class BulkTableModel(QAbstractTableModel):
    """Flat table model backed by a list of item dicts.

    Each row is one item from ``filtered_items``.  Column values are
    computed via ``build_row_values`` and cached per generation counter
    (same eviction strategy as the tkinter build).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_items: list[dict] = []
        self._visible_indices: list[int] = []  # indices into _all_items
        self._inventory_lookup: dict = {}
        self._order_rules: dict = {}
        self._suggest_min_max_fn = None
        # Generation-keyed row cache: row_id → (generation, values_tuple)
        self._cache: dict[str, tuple[int, tuple]] = {}
        self._generation: int = 0
        # Edit callback: (item_dict, col_name, new_value) → None
        self.edit_callback = None
        # Undo capture callback: (source_row_index, col_name) → None
        self.before_edit_callback = None
        # Filter state (managed by the model, not a proxy)
        self._filter_text: str = ""
        self._filter_line_code: str = "ALL"
        self._filter_status: str = "ALL"
        self._filter_source: str = "ALL"
        self._filter_item_status: str = "ALL"
        self._filter_vendor_ws: str = ""

    # ── Data loading ──────────────────────────────────────────────

    def set_data(
        self,
        items: list[dict],
        inventory_lookup: dict,
        order_rules: dict,
        suggest_min_max_fn=None,
    ):
        """Replace the full dataset.  Called once after prepare_assignment_session."""
        write_debug("qt.model.set_data", items=len(items), generation=self._generation + 1)
        self.beginResetModel()
        self._all_items = list(items)
        self._inventory_lookup = inventory_lookup
        self._order_rules = order_rules
        self._suggest_min_max_fn = suggest_min_max_fn
        self._generation += 1
        self._cache.clear()
        self._rebuild_visible()
        self.endResetModel()

    def bump_generation(self):
        """Invalidate all cached row renders (O(1))."""
        self._generation += 1

    def invalidate_rows(self, row_ids: Sequence[str]):
        """Evict specific rows from the render cache."""
        for rid in row_ids:
            self._cache.pop(rid, None)

    @property
    def items(self) -> list[dict]:
        """The full (unfiltered) item list."""
        return self._all_items

    @property
    def total_count(self) -> int:
        return len(self._all_items)

    @property
    def visible_count(self) -> int:
        return len(self._visible_indices)

    # ── QAbstractTableModel interface ─────────────────────────────

    def rowCount(self, parent=QModelIndex()):
        return len(self._visible_indices) if not parent.isValid() else 0

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS) if not parent.isValid() else 0

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal and 0 <= section < len(COLUMNS):
                return LABELS.get(COLUMNS[section], COLUMNS[section])
            if orientation == Qt.Vertical:
                return str(section + 1)
        return None

    def _source_index(self, visible_row: int) -> int:
        """Map a visible row to the source _all_items index."""
        return self._visible_indices[visible_row]

    def _row_values(self, row: int) -> tuple:
        """Cached row-value tuple lookup (row is a visible row index)."""
        item = self._all_items[self._visible_indices[row]]
        rid = bulk_row_id(item)
        cached = self._cache.get(rid)
        if cached is not None and cached[0] == self._generation:
            return cached[1]
        values = build_row_values(
            item, self._inventory_lookup, self._order_rules,
            self._suggest_min_max_fn,
        )
        self._cache[rid] = (self._generation, values)
        return values

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if row < 0 or row >= len(self._visible_indices):
            return None
        src = self._visible_indices[row]

        if role == Qt.DisplayRole or role == Qt.EditRole:
            values = self._row_values(row)
            if 0 <= col < len(values):
                val = values[col]
                return "" if val is None else str(val) if not isinstance(val, str) else val
            return ""

        if role == ROW_TINT_ROLE:
            zone = row_zone(self._all_items[src])
            if zone:
                return t.zone_fill(zone)
            return None

        if role == ITEM_DICT_ROLE:
            return self._all_items[src]

        if role == Qt.TextAlignmentRole:
            col_name = COLUMNS[col] if 0 <= col < len(COLUMNS) else ""
            if col_name in ("raw_need", "suggested_qty", "final_qty", "qoh",
                            "cur_min", "cur_max", "sug_min", "sug_max",
                            "pack_size", "risk"):
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)

        if role == Qt.ToolTipRole:
            item = self._all_items[src]
            col_name = COLUMNS[col] if 0 <= col < len(COLUMNS) else ""
            if col_name == "why":
                return item.get("why", "")
            if col_name == "description":
                return item.get("description", "")
            return None

        return None

    def flags(self, index: QModelIndex):
        base = super().flags(index)
        if not index.isValid():
            return base
        col = index.column()
        if 0 <= col < len(COLUMNS) and COLUMNS[col] in EDITABLE_COLS:
            return base | Qt.ItemIsEditable
        return base

    def setData(self, index: QModelIndex, value, role=Qt.EditRole) -> bool:
        if role != Qt.EditRole or not index.isValid():
            return False
        row, col = index.row(), index.column()
        if row < 0 or row >= len(self._visible_indices):
            return False
        if col < 0 or col >= len(COLUMNS):
            return False
        col_name = COLUMNS[col]
        if col_name not in EDITABLE_COLS:
            return False

        src = self._visible_indices[row]
        item = self._all_items[src]

        # Notify before-edit for undo capture (pass source index)
        if self.before_edit_callback is not None:
            try:
                self.before_edit_callback(src, col_name)
            except Exception:
                pass

        # Route through the edit callback if wired
        if self.edit_callback is not None:
            try:
                self.edit_callback(item, col_name, str(value))
            except Exception:
                return False
        else:
            # Direct mutation fallback (for tests without controller)
            if col_name == "vendor":
                item["vendor"] = str(value).strip().upper()
            elif col_name == "notes":
                item["notes"] = str(value).strip()
            elif col_name in ("final_qty", "qoh", "cur_min", "cur_max", "pack_size"):
                try:
                    item[col_name] = int(float(value)) if value else 0
                except (ValueError, TypeError):
                    return False

        # Evict cache and notify views
        rid = bulk_row_id(self._all_items[src])
        self._cache.pop(rid, None)
        self.dataChanged.emit(
            self.index(row, 0),
            self.index(row, len(COLUMNS) - 1),
        )
        return True

    def item_at(self, row: int) -> Optional[dict]:
        """Return item at visible row index."""
        if 0 <= row < len(self._visible_indices):
            return self._all_items[self._visible_indices[row]]
        return None

    def source_item_at(self, source_row: int) -> Optional[dict]:
        """Return item at source (unfiltered) index."""
        if 0 <= source_row < len(self._all_items):
            return self._all_items[source_row]
        return None

    def row_id_at(self, row: int) -> Optional[str]:
        item = self.item_at(row)
        return bulk_row_id(item) if item else None

    def visible_row_for_source(self, source_row: int) -> int:
        """Map a source index to a visible row, or -1 if filtered out."""
        try:
            return self._visible_indices.index(source_row)
        except ValueError:
            return -1

    # ── Fast Python-side filtering ──────────────────────────────

    def _rebuild_visible(self):
        """Rebuild _visible_indices from filter state — pure Python, no Qt callbacks."""
        text = self._filter_text
        lc = self._filter_line_code
        status = self._filter_status
        source = self._filter_source
        item_st = self._filter_item_status
        vendor_ws = self._filter_vendor_ws

        indices = []
        for i, item in enumerate(self._all_items):
            if vendor_ws:
                if str(item.get("vendor", "") or "").strip().upper() != vendor_ws:
                    continue
            if lc != "ALL" and item.get("line_code", "") != lc:
                continue
            if status == "Assigned" and not item.get("vendor"):
                continue
            if status == "Unassigned" and item.get("vendor"):
                continue
            if source != "ALL":
                has_sales = item.get("qty_sold", 0) > 0
                has_susp = item.get("qty_suspended", 0) > 0
                src = "Both" if (has_sales and has_susp) else ("Susp" if has_susp else "Sales")
                if src != source:
                    continue
            if item_st != "ALL":
                ist = str(item.get("status", "")).strip().upper()
                target = item_st.upper()
                if target == "REVIEW" and ist != "REVIEW":
                    continue
                if target == "WARNING" and ist not in ("WARN", "WARNING"):
                    continue
                if target == "SKIP" and ist != "SKIP":
                    continue
                if target == "OK" and ist not in ("OK", "ORDER"):
                    continue
            if text:
                haystack = item.get("_text_haystack")
                if haystack is None:
                    haystack = " ".join(filter(None, [
                        str(item.get("item_code", "")).lower(),
                        str(item.get("description", "")).lower(),
                        str(item.get("vendor", "")).lower(),
                        str(item.get("supplier_name", item.get("supplier", ""))).lower(),
                    ])).strip()
                if text not in haystack:
                    continue
            indices.append(i)
        self._visible_indices = indices

    def apply_filters(self, *, text=None, line_code=None, status=None,
                      source=None, item_status=None, vendor_ws=None):
        """Set one or more filters and rebuild visible indices in one batch."""
        import time
        changed = False
        if text is not None:
            v = text.strip().lower()
            if v != self._filter_text:
                self._filter_text = v
                changed = True
        if line_code is not None and line_code != self._filter_line_code:
            self._filter_line_code = line_code
            changed = True
        if status is not None and status != self._filter_status:
            self._filter_status = status
            changed = True
        if source is not None and source != self._filter_source:
            self._filter_source = source
            changed = True
        if item_status is not None and item_status != self._filter_item_status:
            self._filter_item_status = item_status
            changed = True
        if vendor_ws is not None:
            v = vendor_ws.strip().upper()
            if v != self._filter_vendor_ws:
                self._filter_vendor_ws = v
                changed = True
        if not changed:
            return
        t0 = time.perf_counter()
        self.beginResetModel()
        self._rebuild_visible()
        self.endResetModel()
        elapsed = (time.perf_counter() - t0) * 1000
        write_debug("qt.filter.applied",
                     text=self._filter_text[:20], lc=self._filter_line_code,
                     status=self._filter_status, source=self._filter_source,
                     item_status=self._filter_item_status,
                     vendor_ws=self._filter_vendor_ws,
                     visible=len(self._visible_indices),
                     total=len(self._all_items),
                     elapsed_ms=round(elapsed, 1))

    def reset_all_filters(self):
        self.apply_filters(text="", line_code="ALL", status="ALL",
                          source="ALL", item_status="ALL", vendor_ws="")

    def refresh_rows(self, source_rows: Sequence[int]):
        """Notify views that specific source rows changed (after edit/recalc)."""
        if not source_rows:
            return
        for src in source_rows:
            if 0 <= src < len(self._all_items):
                self._cache.pop(bulk_row_id(self._all_items[src]), None)
        # Map to visible rows for the signal
        vis_rows = [self.visible_row_for_source(s) for s in source_rows]
        vis_rows = [r for r in vis_rows if r >= 0]
        if vis_rows:
            self.dataChanged.emit(
                self.index(min(vis_rows), 0),
                self.index(max(vis_rows), len(COLUMNS) - 1),
            )


# ─── Filter proxy model ──────────────────────────────────────────────────

class BulkFilterProxyModel(QSortFilterProxyModel):
    """Multi-criteria filter for the bulk grid.

    Filters:
    - text: free-text search across item_code, description, supplier, vendor
    - line_code: exact match or "ALL"
    - status: "ALL", "Assigned", "Unassigned"
    - source: "ALL", "Sales", "Susp", "Both"
    - item_status: "ALL", "Review", "Warning", "Skip", "OK"
    - vendor_worksheet: specific vendor or "" (all)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        self._line_code = "ALL"
        self._status = "ALL"
        self._source = "ALL"
        self._item_status = "ALL"
        self._vendor_worksheet = ""

    # ── Filter setters (each invalidates + logs timing) ─────────────

    def set_text_filter(self, text: str):
        import time
        text = text.strip().lower()
        if text != self._text:
            self._text = text
            t0 = time.perf_counter()
            self.invalidate()
            elapsed = (time.perf_counter() - t0) * 1000
            write_debug("qt.filter.text", query=text[:20], elapsed_ms=round(elapsed, 1))

    def set_line_code_filter(self, lc: str):
        import time
        if lc != self._line_code:
            self._line_code = lc
            t0 = time.perf_counter()
            self.invalidate()
            elapsed = (time.perf_counter() - t0) * 1000
            write_debug("qt.filter.line_code", lc=lc, elapsed_ms=round(elapsed, 1))

    def set_status_filter(self, status: str):
        import time
        if status != self._status:
            self._status = status
            t0 = time.perf_counter()
            self.invalidate()
            elapsed = (time.perf_counter() - t0) * 1000
            write_debug("qt.filter.status", status=status, elapsed_ms=round(elapsed, 1))

    def set_source_filter(self, source: str):
        import time
        if source != self._source:
            self._source = source
            t0 = time.perf_counter()
            self.invalidate()
            elapsed = (time.perf_counter() - t0) * 1000
            write_debug("qt.filter.source", source=source, elapsed_ms=round(elapsed, 1))

    def set_item_status_filter(self, item_status: str):
        import time
        if item_status != self._item_status:
            self._item_status = item_status
            t0 = time.perf_counter()
            self.invalidate()
            elapsed = (time.perf_counter() - t0) * 1000
            write_debug("qt.filter.item_status", item_status=item_status, elapsed_ms=round(elapsed, 1))

    def set_vendor_worksheet(self, vendor: str):
        import time
        vendor = vendor.strip().upper()
        if vendor != self._vendor_worksheet:
            self._vendor_worksheet = vendor
            t0 = time.perf_counter()
            self.invalidate()
            elapsed = (time.perf_counter() - t0) * 1000
            write_debug("qt.filter.vendor_worksheet", vendor=vendor, elapsed_ms=round(elapsed, 1))

    def reset_all_filters(self):
        import time
        self._text = ""
        self._line_code = "ALL"
        self._status = "ALL"
        self._source = "ALL"
        self._item_status = "ALL"
        self._vendor_worksheet = ""
        t0 = time.perf_counter()
        self.invalidate()
        elapsed = (time.perf_counter() - t0) * 1000
        write_debug("qt.filter.reset_all", elapsed_ms=round(elapsed, 1))

    # ── Core filter logic ─────────────────────────────────────────

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if model is None:
            return True
        item = model.item_at(source_row)
        if item is None:
            return False

        # Vendor worksheet filter
        if self._vendor_worksheet:
            item_vendor = str(item.get("vendor", "") or "").strip().upper()
            if item_vendor != self._vendor_worksheet:
                return False

        # Line code
        if self._line_code != "ALL":
            if item.get("line_code", "") != self._line_code:
                return False

        # Assignment status
        if self._status == "Assigned" and not item.get("vendor"):
            return False
        if self._status == "Unassigned" and item.get("vendor"):
            return False

        # Source
        if self._source != "ALL":
            source = _item_source(item)
            if source != self._source:
                return False

        # Item status
        if self._item_status != "ALL":
            item_st = str(item.get("status", "")).strip().upper()
            target = self._item_status.upper()
            if target == "REVIEW" and item_st != "REVIEW":
                return False
            if target == "WARNING" and item_st not in ("WARN", "WARNING"):
                return False
            if target == "SKIP" and item_st != "SKIP":
                return False
            if target == "OK" and item_st not in ("OK", "ORDER"):
                return False

        # Text search — use pre-built haystack when available
        if self._text:
            haystack = item.get("_text_haystack")
            if haystack is None:
                haystack = " ".join(filter(None, [
                    str(item.get("item_code", "")).lower(),
                    str(item.get("description", "")).lower(),
                    str(item.get("vendor", "")).lower(),
                    str(item.get("supplier_name", item.get("supplier", ""))).lower(),
                ])).strip()
            if self._text not in haystack:
                return False

        return True
