from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class ItemKey:
    line_code: str
    item_code: str


@dataclass(frozen=True)
class SourceItemState:
    supplier: str = ""
    order_multiple: Optional[int] = None
    min_qty: Optional[int] = None
    max_qty: Optional[int] = None


@dataclass(frozen=True)
class SuggestedItemState:
    min_qty: Optional[int] = None
    max_qty: Optional[int] = None


@dataclass(frozen=True)
class SessionItemState:
    description: str = ""
    vendor: str = ""
    pack_size: Optional[int] = None
    target_min: Optional[int] = None
    target_max: Optional[int] = None
    qoh_old: Optional[float] = None
    qoh_new: Optional[float] = None
    data_flags: Tuple[str, ...] = field(default_factory=tuple)
    order_policy: str = ""
    duplicate_line_codes: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MaintenanceCandidate:
    key: ItemKey
    source: SourceItemState
    session: SessionItemState
    suggested: SuggestedItemState


@dataclass(frozen=True)
class MaintenanceIssue:
    line_code: str
    item_code: str
    description: str
    issue: str
    assigned_vendor: str
    x4_supplier: str
    pack_size: str
    x4_order_multiple: str
    x4_min: str
    x4_max: str
    target_min: str
    target_max: str
    sug_min: str
    sug_max: str
    qoh_old: str
    qoh_new: str


@dataclass(frozen=True)
class SessionSnapshot:
    created_at: str
    output_dir: str
    po_files: Tuple[str, ...]
    export_scope_label: str
    loaded_report_paths: Dict[str, str]
    exported_items: Tuple[dict, ...]
    assigned_items: Tuple[dict, ...]
    maintenance_issues: Tuple[MaintenanceIssue, ...]
    startup_warning_rows: Tuple[dict, ...]
    qoh_adjustments: Tuple[dict, ...]
    order_rules: Dict[str, dict]


from models.session_bundle import LoadedData, DerivedAnalysis, UserDecisions, SessionMetadata


class AppSessionState:
    """Central mutable session state.

    Fields are grouped into four sub-states (``loaded``, ``derived``,
    ``decisions``, ``metadata``) for new code.  All fields are also
    accessible as flat attributes for backwards compatibility — e.g.
    ``state.sales_items`` delegates to ``state.loaded.sales_items``.
    """

    # Sub-state fields forwarded to flat attributes for compat.
    _LOADED_FIELDS = {
        "sales_items", "po_items", "suspended_items", "suspended_set",
        "suspended_lookup", "all_line_codes", "sales_span_days",
        "sales_window_start", "sales_window_end", "pack_size_lookup",
        "pack_size_source_lookup", "pack_size_by_item", "pack_size_conflicts",
        "on_po_qty", "duplicate_ic_lookup", "startup_warning_rows",
    }
    _DERIVED_FIELDS = {
        "inventory_lookup", "inventory_source_lookup", "receipt_history_lookup",
        "detailed_sales_stats_lookup", "inventory_coverage_missing_keys",
        "detailed_sales_conflict_keys", "unresolved_detailed_item_codes",
        "open_po_lookup",
    }
    _DECISIONS_FIELDS = {
        "order_rules", "vendor_policies", "default_vendor_policy_preset",
        "qoh_adjustments", "suspense_carry", "filtered_items",
        "individual_items", "assigned_items",
    }
    _METADATA_FIELDS = {
        "vendor_codes_used", "recent_orders", "session_history",
        "full_order_history",
    }

    def __init__(self, **kwargs):
        self.loaded = LoadedData()
        self.derived = DerivedAnalysis()
        self.decisions = UserDecisions()
        self.metadata = SessionMetadata()
        for name, value in kwargs.items():
            setattr(self, name, value)

    def _sub_for(self, name):
        if name in self._LOADED_FIELDS:
            return self.loaded
        if name in self._DERIVED_FIELDS:
            return self.derived
        if name in self._DECISIONS_FIELDS:
            return self.decisions
        if name in self._METADATA_FIELDS:
            return self.metadata
        return None

    def __getattr__(self, name):
        sub = object.__getattribute__(self, "_sub_for")(name)
        if sub is not None:
            return getattr(sub, name)
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

    def __setattr__(self, name, value):
        if name in ("loaded", "derived", "decisions", "metadata"):
            object.__setattr__(self, name, value)
            return
        try:
            sub = object.__getattribute__(self, "_sub_for")(name)
        except AttributeError:
            sub = None
        if sub is not None:
            setattr(sub, name, value)
        else:
            object.__setattr__(self, name, value)
