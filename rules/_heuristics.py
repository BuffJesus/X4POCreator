"""Hardware-buffer inference heuristics.

These functions were previously defined only in the top (dead-shadowed) block
of ``rules/__init__.py`` — they are the handful of names in that block that are
NOT re-imported from calc/policy/_helpers, and so were the only *live* code in
it. They are extracted here so the rest of that stale duplicate block can be
deleted without losing them. ``enrich_item`` imports the three public ones.
"""

from rules._constants import (
    HEURISTIC_MIN_SALES_SPAN_DAYS,
    HEURISTIC_SHORT_SPAN_DAYS,
    HEURISTIC_MAX_DAYS_SINCE_SALE,
    HEURISTIC_HIGH_CONFIDENCE_THRESHOLD,
    HEURISTIC_WEEKLY_PACK_RATIO,
    HEURISTIC_WEEKLY_MAX_RATIO,
    HEURISTIC_ANNUAL_PACK_RATIO,
    HEURISTIC_ANNUAL_MAX_RATIO,
    HEURISTIC_COVER_WEEKLY_PACK_RATIO,
    HEURISTIC_COVER_WEEKLY_MAX_RATIO,
    HEURISTIC_COVER_ANNUAL_PACK_RATIO,
    HEURISTIC_COVER_ANNUAL_MAX_RATIO,
    LARGE_PACK_REVIEW_MIN_PACK_QTY,
    PACK_MAX_RATIO_FOR_LARGE_PACK,
)
from rules.policy import looks_like_hardware_pack_item, should_large_pack_review


def _demand_is_volatile(item):
    """Return True when demand shape or signals indicate volatile/unreliable demand."""
    shape = (item.get("detailed_sales_shape") or "").lower()
    if shape in ("erratic", "lumpy"):
        return True
    health = (item.get("sales_health_signal") or "").lower()
    if health in ("declining", "dormant"):
        return True
    profile = (item.get("performance_profile") or "").lower()
    span = item.get("sales_span_days") or 0
    if profile == "intermittent" and span < HEURISTIC_MIN_SALES_SPAN_DAYS:
        return True
    return False


def _recent_history_supports_higher_buffer(item, pack_qty):
    """Return True if order history suggests the item regularly needs >= 2 packs."""
    if not pack_qty or pack_qty <= 0:
        return False
    hist = item.get("historical_order_qty")
    if isinstance(hist, (int, float)) and hist >= pack_qty * 2:
        return True
    local_qty = item.get("recent_local_order_qty") or 0
    local_count = item.get("recent_local_order_count") or 0
    if local_count > 0 and (local_qty / local_count) >= pack_qty * 2:
        return True
    return False


def compute_heuristic_confidence(item):
    """
    Return a float in [0, 1] reflecting how much loaded evidence supports
    the inferred hardware buffer policy for this item.
    Independently of recency_confidence (which governs review gating).
    """
    score = 0.0
    span = item.get("sales_span_days") or 0
    if span >= HEURISTIC_MIN_SALES_SPAN_DAYS:
        score += 0.25
    if item.get("recency_confidence") == "high":
        score += 0.25
    if item.get("performance_profile") in ("top_performer", "steady"):
        score += 0.20
    if item.get("sales_health_signal") == "active":
        score += 0.15
    if item.get("detailed_sales_shape") in ("steady_repeat", "routine_mixed"):
        score += 0.10
    days_since = item.get("days_since_last_sale")
    if isinstance(days_since, (int, float)) and days_since < 30:
        score += 0.05
    score = min(score, 1.0)
    # Hard-cap at 0.3 when sales window is too short to be meaningful
    if span < HEURISTIC_SHORT_SPAN_DAYS:
        score = min(score, 0.3)
    return score


def infer_minimum_packs_on_hand(item, inv, pack_qty):
    """Infer a conservative hardware pack floor for active hardware with extreme pack/max mismatch."""
    mx = inv.get("max") if inv else None
    if not (mx and mx > 0 and pack_qty and pack_qty >= LARGE_PACK_REVIEW_MIN_PACK_QTY):
        return None
    if not looks_like_hardware_pack_item(item, inv or {}):
        return None
    if should_large_pack_review(item, inv or {}, pack_qty):
        return None
    if pack_qty <= mx * PACK_MAX_RATIO_FOR_LARGE_PACK:
        return None

    sales_health = item.get("sales_health_signal", "")
    performance = item.get("performance_profile", "")
    days_since_last_sale = item.get("days_since_last_sale")

    if sales_health not in ("active", "stable", ""):
        return None
    if performance not in ("steady", "top_performer", "intermittent", ""):
        return None
    if isinstance(days_since_last_sale, (int, float)) and days_since_last_sale > HEURISTIC_MAX_DAYS_SINCE_SALE:
        return None

    if _demand_is_volatile(item):
        return 1

    sales_span_days = item.get("sales_span_days")
    weekly_demand = item.get("avg_weekly_sales_loaded")
    annualized_demand = item.get("annualized_sales_loaded")
    detailed_shape = str(item.get("detailed_sales_shape", "") or "").strip().lower()
    if not isinstance(weekly_demand, (int, float)) or weekly_demand <= 0:
        weekly_demand = item.get("demand_signal")

    if (
        isinstance(sales_span_days, (int, float))
        and sales_span_days >= HEURISTIC_MIN_SALES_SPAN_DAYS
        and isinstance(weekly_demand, (int, float))
        and weekly_demand >= max(float(pack_qty) * HEURISTIC_WEEKLY_PACK_RATIO, float(mx) * HEURISTIC_WEEKLY_MAX_RATIO)
        and isinstance(annualized_demand, (int, float))
        and annualized_demand >= max(float(pack_qty) * HEURISTIC_ANNUAL_PACK_RATIO, float(mx) * HEURISTIC_ANNUAL_MAX_RATIO)
        and performance in ("steady", "top_performer")
        and detailed_shape in ("", "steady_repeat", "routine_mixed")
    ):
        return 3
    # Elevated buffer path: high heuristic confidence + history support
    if (
        item.get("heuristic_confidence", 0) >= HEURISTIC_HIGH_CONFIDENCE_THRESHOLD
        and _recent_history_supports_higher_buffer(item, pack_qty)
    ):
        item.setdefault("reason_codes", [])
        if "heuristic_confidence_elevated_buffer" not in item.get("reason_codes", []):
            item["reason_codes"] = item.get("reason_codes", []) + ["heuristic_confidence_elevated_buffer"]
        return 3
    # A very short loaded window does not provide enough history to confidently
    # assert a two-pack floor.  Use a single-pack conservative buffer.
    if isinstance(sales_span_days, (int, float)) and sales_span_days < HEURISTIC_SHORT_SPAN_DAYS:
        return 1
    return 2


def infer_minimum_cover_cycles(item, inv, pack_qty):
    """Infer a conservative hardware cover floor for active weekly-order hardware items."""
    reorder_cycle_weeks = item.get("reorder_cycle_weeks")
    mx = inv.get("max") if inv else None
    if not (
        isinstance(reorder_cycle_weeks, (int, float))
        and reorder_cycle_weeks > 0
        and reorder_cycle_weeks <= 1
        and isinstance(pack_qty, (int, float))
        and pack_qty > 0
        and isinstance(mx, (int, float))
        and mx > 0
    ):
        return None
    if pack_qty > mx * PACK_MAX_RATIO_FOR_LARGE_PACK:
        return None
    if not looks_like_hardware_pack_item(item, inv or {}):
        return None
    if should_large_pack_review(item, inv or {}, pack_qty):
        return None

    sales_health = item.get("sales_health_signal", "")
    performance = item.get("performance_profile", "")
    days_since_last_sale = item.get("days_since_last_sale")
    if sales_health not in ("active", "stable", ""):
        return None
    if performance not in ("steady", "top_performer", "intermittent", ""):
        return None
    if isinstance(days_since_last_sale, (int, float)) and days_since_last_sale > HEURISTIC_MAX_DAYS_SINCE_SALE:
        return None

    sales_span_days = item.get("sales_span_days")
    if isinstance(sales_span_days, (int, float)) and sales_span_days < HEURISTIC_SHORT_SPAN_DAYS:
        return 1
    if _demand_is_volatile(item):
        return 1

    weekly_demand = item.get("avg_weekly_sales_loaded")
    if not isinstance(weekly_demand, (int, float)) or weekly_demand <= 0:
        weekly_demand = item.get("demand_signal")
    if not isinstance(weekly_demand, (int, float)) or weekly_demand <= 0:
        return None
    if weekly_demand < max(1.0, mx * 0.75):
        return None
    if weekly_demand < max(1.0, pack_qty * 0.5):
        return None

    annualized_demand = item.get("annualized_sales_loaded")
    detailed_shape = str(item.get("detailed_sales_shape", "") or "").strip().lower()
    if (
        isinstance(sales_span_days, (int, float))
        and sales_span_days >= HEURISTIC_MIN_SALES_SPAN_DAYS
        and weekly_demand >= max(float(pack_qty) * HEURISTIC_COVER_WEEKLY_PACK_RATIO, float(mx) * HEURISTIC_COVER_WEEKLY_MAX_RATIO)
        and isinstance(annualized_demand, (int, float))
        and annualized_demand >= max(float(pack_qty) * HEURISTIC_COVER_ANNUAL_PACK_RATIO, float(mx) * HEURISTIC_COVER_ANNUAL_MAX_RATIO)
        and performance in ("steady", "top_performer")
        and detailed_shape in ("", "steady_repeat", "routine_mixed")
    ):
        return 3
    return 2
