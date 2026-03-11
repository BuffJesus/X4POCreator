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
    loaded_report_paths: Dict[str, str]
    assigned_items: Tuple[dict, ...]
    maintenance_issues: Tuple[MaintenanceIssue, ...]
    startup_warning_rows: Tuple[dict, ...]
    qoh_adjustments: Tuple[dict, ...]
    order_rules: Dict[str, dict]
