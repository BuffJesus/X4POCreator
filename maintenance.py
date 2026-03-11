from typing import Iterable, List, Optional

from models import MaintenanceCandidate, MaintenanceIssue


def _fmt_int(value: Optional[int]) -> str:
    return "" if value is None else str(value)


def _fmt_qoh(value: Optional[float]) -> str:
    return "" if value is None else f"{value:g}"


def _fmt_mm_pair(min_qty: Optional[int], max_qty: Optional[int]) -> str:
    left = _fmt_int(min_qty)
    right = _fmt_int(max_qty)
    return f"{left}/{right}"


def build_maintenance_issue(candidate: MaintenanceCandidate) -> Optional[MaintenanceIssue]:
    source = candidate.source
    session = candidate.session
    suggested = candidate.suggested
    flags = []

    if session.vendor:
        if not source.supplier:
            flags.append(f"Set supplier to {session.vendor} (X4 blank)")
        elif source.supplier.upper() != session.vendor.upper():
            flags.append(f"Supplier {source.supplier} -> {session.vendor}")

    if session.pack_size:
        if not source.order_multiple:
            flags.append(f"Set order multiple to {session.pack_size}")
        elif int(source.order_multiple) != int(session.pack_size):
            flags.append(f"Order multiple {source.order_multiple} -> {session.pack_size}")

    if session.target_min != source.min_qty or session.target_max != source.max_qty:
        flags.append(
            f"App min/max {_fmt_mm_pair(source.min_qty, source.max_qty)} -> "
            f"{_fmt_mm_pair(session.target_min, session.target_max)}"
        )
    elif suggested.min_qty is not None and (
        source.min_qty != suggested.min_qty or source.max_qty != suggested.max_qty
    ):
        flags.append(
            f"Suggested min/max {_fmt_mm_pair(suggested.min_qty, suggested.max_qty)} "
            f"differs from X4 {_fmt_mm_pair(source.min_qty, source.max_qty)}"
        )

    if session.qoh_old is not None and session.qoh_new is not None:
        flags.append(f"QOH adjusted: {session.qoh_old:g} -> {session.qoh_new:g}")

    if session.duplicate_line_codes:
        flags.append(f"Also under: {', '.join(session.duplicate_line_codes)}")

    if "missing_pack" in session.data_flags:
        flags.append("Missing pack/order multiple data")

    if session.order_policy == "reel_review":
        flags.append(f"Reel/pack review needed (pack={session.pack_size})")

    if not flags:
        return None

    return MaintenanceIssue(
        line_code=candidate.key.line_code,
        item_code=candidate.key.item_code,
        description=session.description,
        issue="; ".join(flags),
        assigned_vendor=session.vendor,
        x4_supplier=source.supplier or "(empty)",
        pack_size=_fmt_int(session.pack_size),
        x4_order_multiple=_fmt_int(source.order_multiple),
        x4_min=_fmt_int(source.min_qty),
        x4_max=_fmt_int(source.max_qty),
        target_min=_fmt_int(session.target_min),
        target_max=_fmt_int(session.target_max),
        sug_min=_fmt_int(suggested.min_qty),
        sug_max=_fmt_int(suggested.max_qty),
        qoh_old=_fmt_qoh(session.qoh_old),
        qoh_new=_fmt_qoh(session.qoh_new),
    )


def build_maintenance_report(candidates: Iterable[MaintenanceCandidate]) -> List[MaintenanceIssue]:
    issues = []
    for candidate in candidates:
        issue = build_maintenance_issue(candidate)
        if issue is not None:
            issues.append(issue)
    issues.sort(key=lambda issue: (issue.line_code, issue.item_code))
    return issues
