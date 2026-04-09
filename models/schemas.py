"""Typed row schemas for the major data structures.

These TypedDicts document the expected shape of item dicts, inventory
entries, and sales rows.  They're not enforced at runtime — their
value is in editor autocompletion, static analysis, and serving as
living documentation of which fields exist.

Usage::

    from models.schemas import BulkItem, InventoryEntry
    def process_item(item: BulkItem) -> None:
        vendor = item["vendor"]  # autocomplete + type checking
"""

from typing import Any, List, Optional
try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict


class InventoryEntry(TypedDict, total=False):
    """A row from the Min/Max or On-Hand report."""
    qoh: float
    repl_cost: float
    min: Optional[int]
    max: Optional[int]
    ytd_sales: float
    mo12_sales: float
    supplier: str
    last_receipt: str
    last_sale: str
    description: str


class SalesItem(TypedDict, total=False):
    """A row from the Part Sales & Receipts summary."""
    line_code: str
    item_code: str
    description: str
    qty_sold: int
    qty_received: int
    qty_suspended: int


class ReceiptHistoryEntry(TypedDict, total=False):
    """Per-item receipt history aggregated from Received Parts Detail."""
    last_receipt_date: str
    primary_vendor: str
    most_recent_vendor: str
    vendor_confidence: str
    vendor_confidence_reason: str
    vendor_ambiguous: bool
    primary_vendor_qty_share: float
    primary_vendor_receipt_share: float
    receipt_count: int
    qty_received_total: int
    first_receipt_date: str
    avg_units_per_receipt: Optional[float]
    median_units_per_receipt: Optional[float]
    max_units_per_receipt: Optional[int]
    avg_days_between_receipts: Optional[float]
    vendors: dict


class BulkItem(TypedDict, total=False):
    """An item on the bulk assignment grid.

    This is the central data dict that flows through enrich_item,
    the bulk grid, and export.  Fields are stamped progressively
    by parsers, assignment_flow, rules.enrich_item, and the UI.
    """
    # Identity
    line_code: str
    item_code: str
    description: str

    # Source data
    qty_sold: int
    qty_received: int
    qty_suspended: int
    qty_on_po: int
    demand_signal: float
    pack_size: Optional[int]
    pack_size_source: str

    # Inventory
    inventory: InventoryEntry

    # Calculated by enrich_item
    inventory_position: float
    target_stock: float
    target_basis: str
    effective_target_stock: float
    effective_order_floor: float
    raw_need: int
    suggested_qty: int
    final_qty: int
    order_qty: int
    order_policy: str
    replenishment_unit_mode: str
    package_profile: str

    # Status and classification
    status: str
    data_flags: List[str]
    reason_codes: List[str]
    why: str
    core_why: str
    review_required: bool
    review_resolved: bool
    manual_override: bool
    reorder_needed: bool
    dead_stock: bool

    # Confidence and risk
    recency_confidence: str
    heuristic_confidence: float
    data_completeness: str
    recency_review_bucket: Optional[str]
    stockout_risk_score: float
    confirmed_stocking: bool
    confirmed_stocking_expired: bool

    # Vendor
    vendor: str
    receipt_primary_vendor: str
    receipt_most_recent_vendor: str
    receipt_vendor_confidence: str

    # Overstock
    projected_overstock_qty: float
    overstock_within_tolerance: bool
    acceptable_overstock_qty_effective: int

    # User annotations
    notes: str

    # Runtime cache (not persisted)
    _text_haystack: str


class ExportItem(TypedDict, total=False):
    """An item in the export pipeline (assigned_items)."""
    line_code: str
    item_code: str
    description: str
    order_qty: int
    final_qty: int
    vendor: str
    pack_size: Optional[int]
    status: str
    why: str
    core_why: str
    notes: str
