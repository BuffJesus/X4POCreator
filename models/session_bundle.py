"""Sub-state dataclasses for AppSessionState.

Splits the ~30-field god-object into four coherent groups:

- ``LoadedData`` — raw parse output, immutable after load
- ``DerivedAnalysis`` — computed lookups, invalidated on edits
- ``UserDecisions`` — operator assignments and rules
- ``SessionMetadata`` — history, vendor codes, snapshot info

AppSessionState gains forwarding properties so existing code like
``state.sales_items`` still works (→ ``state.loaded.sales_items``).
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LoadedData:
    """Raw parse output — set once during load, not mutated afterwards."""
    sales_items: list = field(default_factory=list)
    po_items: list = field(default_factory=list)
    suspended_items: list = field(default_factory=list)
    suspended_set: set = field(default_factory=set)
    suspended_lookup: dict = field(default_factory=dict)
    all_line_codes: list = field(default_factory=list)
    sales_span_days: Optional[int] = None
    sales_window_start: str = ""
    sales_window_end: str = ""
    pack_size_lookup: dict = field(default_factory=dict)
    pack_size_source_lookup: dict = field(default_factory=dict)
    pack_size_by_item: dict = field(default_factory=dict)
    pack_size_conflicts: set = field(default_factory=set)
    on_po_qty: dict = field(default_factory=dict)
    duplicate_ic_lookup: dict = field(default_factory=dict)
    startup_warning_rows: list = field(default_factory=list)


@dataclass
class DerivedAnalysis:
    """Computed lookups derived from loaded data — invalidated on edits."""
    inventory_lookup: dict = field(default_factory=dict)
    inventory_source_lookup: dict = field(default_factory=dict)
    receipt_history_lookup: dict = field(default_factory=dict)
    detailed_sales_stats_lookup: dict = field(default_factory=dict)
    inventory_coverage_missing_keys: set = field(default_factory=set)
    detailed_sales_conflict_keys: set = field(default_factory=set)
    unresolved_detailed_item_codes: set = field(default_factory=set)
    open_po_lookup: dict = field(default_factory=dict)


@dataclass
class UserDecisions:
    """Operator assignments, rules, and adjustments."""
    order_rules: dict = field(default_factory=dict)
    vendor_policies: dict = field(default_factory=dict)
    default_vendor_policy_preset: str = ""
    qoh_adjustments: dict = field(default_factory=dict)
    suspense_carry: dict = field(default_factory=dict)
    filtered_items: list = field(default_factory=list)
    individual_items: list = field(default_factory=list)
    assigned_items: list = field(default_factory=list)


@dataclass
class SessionMetadata:
    """Session history, vendor tracking, and snapshot info."""
    vendor_codes_used: list = field(default_factory=list)
    recent_orders: dict = field(default_factory=dict)
    session_history: dict = field(default_factory=dict)
    full_order_history: dict = field(default_factory=dict)
