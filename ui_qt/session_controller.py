"""Qt session controller — owns session state and runs the load→assign pipeline.

This is the Qt counterpart of ``app/session_controller.py`` +
``POBuilderApp._proceed_to_assign_inner``.  It wraps the UI-agnostic
flow modules (``load_flow``, ``assignment_flow``, ``reorder_flow``,
``auto_assign_flow``, etc.) so the Qt shell can run the full enrichment
pipeline without any tkinter dependency.

The controller is a plain Python object (no QObject) that the shell
composes.  It communicates back to the UI via callbacks, not signals,
so it can be tested without QApplication.
"""

from __future__ import annotations

import copy
import os
from typing import Optional

from models import AppSessionState

# These modules are UI-agnostic — safe to import from both stacks.
import assignment_flow
import load_flow
import reorder_flow
import shipping_flow
import storage
from debug_log import write_debug
def build_data_paths(data_dir):
    """Build path dict — duplicated from data_folder_flow to avoid tkinter import."""
    return {
        "duplicate_whitelist": os.path.join(data_dir, "duplicate_whitelist.txt"),
        "order_history": os.path.join(data_dir, "order_history.json"),
        "order_rules": os.path.join(data_dir, "order_rules.json"),
        "suspense_carry": os.path.join(data_dir, "suspense_carry.json"),
        "sessions": os.path.join(data_dir, "sessions"),
        "vendor_codes": os.path.join(data_dir, "vendor_codes.txt"),
        "vendor_policies": os.path.join(data_dir, "vendor_policies.json"),
        "ignored_items": os.path.join(data_dir, "ignored_items.txt"),
        "supplier_vendor_map": os.path.join(data_dir, "supplier_vendor_map.json"),
        "item_notes": os.path.join(data_dir, "item_notes.json"),
    }


def get_rule_key(line_code, item_code):
    """Build a consistent key for the order rules dict.

    Duplicated from ``po_builder.get_rule_key`` to avoid importing
    tkinter transitively.
    """
    return f"{line_code}:{item_code}"


# ── Known vendors list (shared with po_builder.py) ───────────────────────
# Import from po_builder would pull in tkinter transitively.  Duplicate
# only the module-level constant; the authoritative list is in
# po_builder.py.  Both builds load vendor_codes.txt at runtime so the
# actual list grows on disk; this seed list just bootstraps the combo.

def _load_known_vendors_seed():
    """Load KNOWN_VENDORS from po_builder.py without importing tkinter.

    Falls back to an empty list if anything goes wrong — the runtime
    vendor_codes.txt file is the real source of truth.
    """
    import importlib.util
    spec_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "po_builder.py")
    try:
        # Read just the KNOWN_VENDORS constant via AST to avoid executing
        # tkinter imports at module level.
        import ast
        with open(spec_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "KNOWN_VENDORS":
                        return ast.literal_eval(node.value)
    except Exception:
        pass
    return []


KNOWN_VENDORS = _load_known_vendors_seed()


# Minimum annualized sales for min/max suggestions (matches po_builder.py)
MIN_ANNUAL_SALES_FOR_SUGGESTIONS = 4
DEFAULT_VENDOR_POLICY_PRESET = "release_all"
DEFAULT_EXCLUDE_DRAFT_POS = True


class QtSessionController:
    """Non-UI session controller for the Qt build.

    Mirrors the subset of ``POBuilderApp`` that flow modules access
    via ``app.*`` attributes — session state, caches, helper methods,
    and persistent config.
    """

    def __init__(self, app_settings: dict | None = None):
        self.app_settings = app_settings if app_settings is not None else {}
        self.session = AppSessionState()

        # Persistent state (loaded from disk)
        self.order_rules: dict = {}
        self.vendor_codes_used: list[str] = list(KNOWN_VENDORS)
        self.vendor_policies: dict = {}
        self.dup_whitelist: set = set()
        self.ignored_item_keys: set = set()
        self.suspense_carry: dict = {}
        self.item_notes: dict = {}
        self.supplier_vendor_map: dict = {}

        # Runtime state
        self.excluded_line_codes: set = set()
        self.excluded_customers: set = set()
        self.last_removed_bulk_items: list = []
        self.last_protected_bulk_items: list = []
        self.qoh_adjustments: dict = {}

        # Caches (invalidated per session)
        self._suggest_min_max_cache: dict | None = None
        self._pack_size_resolution_cache: dict = {}
        self._suggest_min_max_source_cache: dict | None = None

        # Data directory
        self.shared_data_dir = ""
        self.data_dir = self._resolve_data_dir()
        self.data_paths = build_data_paths(self.data_dir)

    def _resolve_data_dir(self) -> str:
        """Determine data directory from app_settings."""
        requested = str(self.app_settings.get("shared_data_dir", "") or "").strip()
        if requested:
            normalized = os.path.abspath(requested)
            ok, _reason = storage.validate_storage_directory(normalized)
            if ok:
                self.shared_data_dir = normalized
                return normalized
        # Fall back to local dir next to the script
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _data_path(self, key: str) -> str:
        return self.data_paths.get(key, "")

    # ── Persistent state ──────────────────────────────────────────

    def load_persistent_state(self):
        """Load order rules, vendor codes, etc. from disk."""
        write_debug("qt.controller.load_persistent_state.begin", data_dir=self.data_dir)
        dp = self._data_path
        self.dup_whitelist = set(storage.load_duplicate_whitelist(dp("duplicate_whitelist")))
        self.ignored_item_keys = set(storage.load_ignored_items(dp("ignored_items")))
        self.order_rules = dict(storage.load_order_rules(dp("order_rules")))
        self.suspense_carry = dict(storage.load_suspense_carry(dp("suspense_carry")))
        self.vendor_codes_used = list(
            storage.load_vendor_codes(dp("vendor_codes"), KNOWN_VENDORS)
        )
        self.vendor_policies = dict(storage.load_vendor_policies(dp("vendor_policies")))
        try:
            import item_notes_flow
            self.item_notes = item_notes_flow.load_notes(dp("item_notes"))
        except Exception:
            self.item_notes = {}
        try:
            self.supplier_vendor_map = dict(
                storage.load_json_file(dp("supplier_vendor_map"), {})
            )
        except Exception:
            self.supplier_vendor_map = {}

        # Mirror onto session
        self.session.order_rules = self.order_rules
        self.session.vendor_policies = self.vendor_policies
        write_debug("qt.controller.load_persistent_state.done",
                     rules=len(self.order_rules),
                     vendors=len(self.vendor_codes_used),
                     ignored=len(self.ignored_item_keys),
                     notes=len(self.item_notes))

    def _save_order_rules(self):
        write_debug("qt.controller.save_order_rules", count=len(self.order_rules))
        storage.save_order_rules(self._data_path("order_rules"), self.order_rules)

    # ── Pack size resolution (memoized per session) ───────────────

    def _resolve_pack_size(self, key):
        pack, _source = self._resolve_pack_size_with_source(key)
        return pack

    def _resolve_pack_size_with_source(self, key):
        cache = self._pack_size_resolution_cache
        hit = cache.get(key)
        if hit is not None:
            return hit

        pack_size_lookup = getattr(self.session, "pack_size_lookup", {}) or {}
        pack = pack_size_lookup.get(key)
        if pack:
            result = (pack, "x4_exact")
            cache[key] = result
            return result
        generic = pack_size_lookup.get(("", key[1]))
        if generic:
            result = (generic, "x4_item")
            cache[key] = result
            return result
        pack_size_by_item = getattr(self.session, "pack_size_by_item", {}) or {}
        fallback = pack_size_by_item.get(key[1])
        if fallback:
            result = (fallback, "x4_item_fallback")
            cache[key] = result
            return result
        receipt_pack = reorder_flow.receipt_pack_size_for_key(self, key)
        if receipt_pack:
            result = (receipt_pack, "receipt_history")
            cache[key] = result
            return result
        result = (None, "")
        cache[key] = result
        return result

    # ── Vendor + suspense helpers ─────────────────────────────────

    def _default_vendor_for_key(self, key):
        return reorder_flow.default_vendor_for_key(self, key)

    def _get_suspense_carry_qty(self, key):
        entry = self.suspense_carry.get(key)
        if entry is None:
            # Also try string key format
            lc, ic = key
            entry = self.suspense_carry.get(f"{lc}:{ic}")
        if entry is None:
            return 0
        if isinstance(entry, dict):
            return entry.get("qty", 0)
        return int(entry) if entry else 0

    def _get_cycle_weeks(self) -> int:
        return getattr(self, "_cycle_weeks", 2)  # Default Biweekly

    def _suggest_min_max(self, key):
        cache = self._suggest_min_max_cache
        if cache is None:
            cache = {}
            self._suggest_min_max_cache = cache
        hit = cache.get(key)
        if hit is not None:
            return hit
        result = reorder_flow.suggest_min_max(self, key, MIN_ANNUAL_SALES_FOR_SUGGESTIONS)
        cache[key] = result
        return result

    def _get_default_vendor_policy_preset(self) -> str:
        return str(self.app_settings.get(
            "default_vendor_policy_preset", DEFAULT_VENDOR_POLICY_PRESET
        ) or DEFAULT_VENDOR_POLICY_PRESET).strip()

    def _get_exclude_draft_pos_from_committed(self) -> bool:
        value = self.app_settings.get(
            "exclude_draft_pos_from_committed", DEFAULT_EXCLUDE_DRAFT_POS
        )
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in ("", "0", "false", "no", "off")
        return DEFAULT_EXCLUDE_DRAFT_POS

    # ── Forwarding properties (flow modules access via app.*) ─────

    @property
    def sales_items(self):
        return self.session.sales_items

    @property
    def filtered_items(self):
        return self.session.filtered_items

    @filtered_items.setter
    def filtered_items(self, value):
        self.session.filtered_items = value

    @property
    def inventory_lookup(self):
        return self.session.inventory_lookup

    @property
    def on_po_qty(self):
        return getattr(self.session, "on_po_qty", {}) or {}

    @property
    def pack_size_lookup(self):
        return getattr(self.session, "pack_size_lookup", {}) or {}

    @property
    def pack_size_by_item(self):
        return getattr(self.session, "pack_size_by_item", {}) or {}

    @property
    def pack_size_conflicts(self):
        return getattr(self.session, "pack_size_conflicts", set()) or set()

    @property
    def receipt_history_lookup(self):
        return getattr(self.session, "receipt_history_lookup", {}) or {}

    @property
    def detailed_sales_stats_lookup(self):
        return getattr(self.session, "detailed_sales_stats_lookup", {}) or {}

    # ── Recalculation (called by bulk_edit_flow) ──────────────────

    def _recalculate_item(self, item, annotate_release=True):
        import item_workflow
        lc = item.get("line_code", "")
        ic = item.get("item_code", "")
        item["reorder_cycle_weeks"] = self._get_cycle_weeks()
        item_workflow.recalculate_item_from_session(
            item, self.session, self._suggest_min_max, get_rule_key,
        )
        if annotate_release:
            shipping_flow.annotate_release_decisions(self.session)
        write_debug("qt.controller.recalculate_item",
                     line_code=lc, item_code=ic,
                     suggested=item.get("suggested_qty"),
                     final=item.get("final_qty"),
                     status=item.get("status"),
                     policy=item.get("order_policy"),
                     pack=item.get("pack_size"))
        return item

    def _set_effective_order_qty(self, item, qty, manual_override=False):
        """Set the effective order quantity on an item (matches po_builder pattern)."""
        import item_workflow
        item_workflow.set_effective_order_qty(item, qty, manual_override=manual_override)

    def _clear_manual_override(self, item):
        import item_workflow
        item_workflow.clear_manual_override(item)

    def _remember_vendor_code(self, vendor: str):
        if vendor and vendor not in self.vendor_codes_used:
            self.vendor_codes_used.append(vendor)
            self.vendor_codes_used.sort()

    # ── Load → Assign pipeline ────────────────────────────────────

    def apply_load_result(self, result: dict):
        """Apply a parsed load result onto the session."""
        write_debug("qt.controller.apply_load_result",
                     sales_items=len(result.get("sales_items", [])),
                     po_items=len(result.get("po_items", [])),
                     suspended=len(result.get("suspended_items", [])))
        load_flow.apply_load_result(self.session, result)
        self.session.order_rules = self.order_rules
        self.session.vendor_policies = self.vendor_policies

    def prepare_assignment(self, progress_cb=None) -> bool:
        """Run the full assignment pipeline.

        Returns True if items are available for assignment.
        ``progress_cb`` receives status strings for UI feedback.
        """
        import time
        _t = time.perf_counter
        write_debug("qt.controller.prepare_assignment.begin",
                     excluded_lc=len(self.excluded_line_codes),
                     excluded_cust=len(self.excluded_customers),
                     sales_items=len(self.session.sales_items),
                     inventory=len(self.session.inventory_lookup),
                     receipts=len(getattr(self.session, "receipt_history_lookup", {}) or {}))
        if progress_cb:
            progress_cb("Preparing session\u2026")

        # Invalidate caches for fresh load
        self._suggest_min_max_cache = {}
        self._pack_size_resolution_cache = {}
        if hasattr(self.session, "_suggest_min_max_source_cache"):
            self.session._suggest_min_max_source_cache = {}

        t0 = _t()
        has_items = assignment_flow.prepare_assignment_session(
            self.session,
            excluded_line_codes=self.excluded_line_codes,
            excluded_customers=self.excluded_customers,
            dup_whitelist=self.dup_whitelist,
            ignored_keys=self.ignored_item_keys,
            lookback_days=14,
            order_history_path=self._data_path("order_history"),
            vendor_codes_path=self._data_path("vendor_codes"),
            known_vendors=KNOWN_VENDORS,
            get_suspense_carry_qty=self._get_suspense_carry_qty,
            default_vendor_for_key=self._default_vendor_for_key,
            resolve_pack_size=self._resolve_pack_size,
            resolve_pack_size_with_source=self._resolve_pack_size_with_source,
            suggest_min_max=self._suggest_min_max,
            get_cycle_weeks=self._get_cycle_weeks,
            get_rule_key=get_rule_key,
            default_vendor_policy_preset=self._get_default_vendor_policy_preset(),
            exclude_draft_pos_from_committed=self._get_exclude_draft_pos_from_committed(),
        )

        t1 = _t()
        write_debug("qt.controller.prepare_assignment.session_done",
                     elapsed_ms=round((t1 - t0) * 1000, 1),
                     has_items=has_items,
                     filtered=len(self.session.filtered_items) if has_items else 0)

        if not has_items:
            return False

        # Log sample item to verify enrichment
        sample = self.session.filtered_items[0] if self.session.filtered_items else {}
        write_debug("qt.controller.prepare_assignment.sample_item",
                     lc=sample.get("line_code", ""),
                     ic=sample.get("item_code", ""),
                     demand_signal=sample.get("demand_signal"),
                     raw_need=sample.get("raw_need"),
                     suggested=sample.get("suggested_qty"),
                     final=sample.get("final_qty"),
                     status=sample.get("status"),
                     vendor=sample.get("vendor"),
                     receipt_vendor=sample.get("receipt_primary_vendor", ""),
                     receipt_confidence=sample.get("receipt_vendor_confidence", ""))

        t2 = _t()
        if progress_cb:
            progress_cb("Normalizing demand\u2026")
        reorder_flow.normalize_items_to_cycle(self)
        t3 = _t()
        write_debug("qt.controller.prepare_assignment.normalize",
                     elapsed_ms=round((t3 - t2) * 1000, 1))

        if progress_cb:
            progress_cb("Applying notes\u2026")
        try:
            import item_notes_flow
            item_notes_flow.apply_notes_to_items(
                self.session.filtered_items, self.item_notes,
            )
        except Exception:
            pass
        t4 = _t()

        if progress_cb:
            progress_cb("Auto-assigning vendors\u2026")
        try:
            import auto_assign_flow
            self._last_auto_assign_result = auto_assign_flow.auto_assign_from_receipts(self)
        except Exception as exc:
            write_debug("qt.controller.auto_assign.error", error=str(exc))
            self._last_auto_assign_result = {}
        t5 = _t()
        write_debug("qt.controller.prepare_assignment.auto_assign",
                     elapsed_ms=round((t5 - t4) * 1000, 1),
                     result=str(self._last_auto_assign_result)[:100])

        # Refresh vendor codes from assigned items
        for item in self.session.filtered_items:
            vendor = str(item.get("vendor", "") or "").strip().upper()
            if vendor and vendor not in self.vendor_codes_used:
                self.vendor_codes_used.append(vendor)
        self.vendor_codes_used.sort()

        auto_count = self._last_auto_assign_result.get("assigned_count", 0)

        # Status breakdown for debugging
        from collections import Counter
        items = self.session.filtered_items
        status_counts = Counter(str(i.get("status", "")).strip().lower() or "blank" for i in items)
        vendor_counts = sum(1 for i in items if i.get("vendor"))
        zero_demand = sum(1 for i in items if (i.get("demand_signal", 0) or 0) <= 0)
        zero_final = sum(1 for i in items if (i.get("final_qty", 0) or 0) <= 0)
        has_suggested = sum(1 for i in items if (i.get("suggested_qty", 0) or 0) > 0)
        write_debug("qt.controller.prepare_assignment.status_breakdown",
                     **{f"st_{k}": v for k, v in status_counts.most_common(10)})
        write_debug("qt.controller.prepare_assignment.done",
                     filtered_items=len(items),
                     vendors=len(self.vendor_codes_used),
                     auto_assigned=auto_count,
                     with_vendor=vendor_counts,
                     zero_demand=zero_demand,
                     zero_final=zero_final,
                     has_suggested=has_suggested,
                     span_days=getattr(self.session, "sales_span_days", None))
        return True
