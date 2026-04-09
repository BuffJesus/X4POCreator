"""Performance instrumentation harness.

Opt-in, low-overhead timing + event log used to measure where time
actually goes inside the app.  Designed to be enabled on the
operator's real machine so we have ground-truth numbers from real
workflows instead of guessing from dev-box profiler runs.

Typical usage:

    from perf_trace import enable, disable, span, stamp

    enable("perf_trace.jsonl", session_label="weekly")
    with span("parsers.parse_all_files", file_count=7):
        result = parse_all_files(...)
    stamp("notebook.tab_switch", old="Load", new="Bulk")
    disable()  # writes perf_summary.txt next to the jsonl

The harness stores each completed span / stamp in an in-memory ring
buffer *and* appends it to a JSONL file (one JSON object per line).
When the operator hits Help → Enable Performance Trace, the toggle
flips this module on for the rest of the session; an `atexit` hook
writes the aggregate summary on clean shutdown.

Overhead: `time.perf_counter()` is ~50 ns on Windows; a span's JSONL
write is ~10-50 µs.  At hundreds of spans per session the total
overhead is well under 1% and invisible to the operator.  Per-item
(60K-call) hot loops should use `aggregate_span` instead, which only
emits one summary row per outer span.
"""

from __future__ import annotations

import atexit
import json
import os
import sys
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Deque, Dict, Iterable, List, Optional


# ── Module state ─────────────────────────────────────────────────────────────

_LOCK = threading.RLock()
_ENABLED = False
_LOG_PATH: Optional[str] = None
_SUMMARY_PATH: Optional[str] = None
_SESSION_LABEL: str = ""
_SESSION_START_WALL: Optional[datetime] = None
_SESSION_START_MONO: Optional[float] = None

# Ring buffer keeps the last N events in memory so `write_summary` can
# compute aggregates without re-reading the JSONL.  Capped to avoid OOM
# on long sessions.
_RING_CAPACITY = 50_000
_RING: Deque[dict] = deque(maxlen=_RING_CAPACITY)

# Aggregate counters for `aggregate_span` — one counter per event name,
# used by the 60K-call hot loops so we don't flood the log.
_AGGREGATE_TOTALS: Dict[str, Dict[str, float]] = defaultdict(
    lambda: {"count": 0, "total_ms": 0.0, "max_ms": 0.0}
)

# ── Public API ───────────────────────────────────────────────────────────────


def is_enabled() -> bool:
    """Return True when the harness is currently recording."""
    return _ENABLED


def enable(
    log_path: Optional[str] = None,
    *,
    session_label: str = "",
    summary_path: Optional[str] = None,
) -> None:
    """Start recording.  Safe to call multiple times — subsequent calls
    rotate the log file but keep the existing ring buffer intact.
    """
    global _ENABLED, _LOG_PATH, _SUMMARY_PATH, _SESSION_LABEL
    global _SESSION_START_WALL, _SESSION_START_MONO
    with _LOCK:
        _ENABLED = True
        _LOG_PATH = log_path or _default_log_path()
        _SUMMARY_PATH = summary_path or _default_summary_path(_LOG_PATH)
        _SESSION_LABEL = str(session_label or "")
        _SESSION_START_WALL = datetime.now()
        _SESSION_START_MONO = time.perf_counter()
        # Write a session-start marker so multiple sessions in one
        # JSONL file are easy to separate.
        _write_jsonl({
            "event": "perf_trace.enabled",
            "session_label": _SESSION_LABEL,
            "ts": _SESSION_START_WALL.isoformat(timespec="milliseconds"),
        })


def disable(*, write_summary: bool = True) -> Optional[str]:
    """Stop recording.  Returns the summary path if one was written."""
    global _ENABLED
    summary_path = None
    with _LOCK:
        if not _ENABLED:
            return None
        if write_summary and _SUMMARY_PATH is not None:
            try:
                summary_path = write_summary_report(_SUMMARY_PATH)
            except Exception:
                summary_path = None
        _write_jsonl({
            "event": "perf_trace.disabled",
            "ts": datetime.now().isoformat(timespec="milliseconds"),
        })
        _ENABLED = False
    return summary_path


def log_path() -> Optional[str]:
    return _LOG_PATH


def summary_path() -> Optional[str]:
    return _SUMMARY_PATH


def clear_ring_buffer() -> None:
    """Drop every recorded event.  Used by tests between runs."""
    with _LOCK:
        _RING.clear()
        _AGGREGATE_TOTALS.clear()


@contextmanager
def span(event: str, **fields: Any):
    """Time the enclosed block and record one row on completion.

    Writes two events to the log: a `span_start` marker on entry and a
    `span` row with duration on clean exit.  The `span_start` is the
    breadcrumb trail we need for crash diagnosis — if a process dies
    inside the block, the completion row is never written, but the
    start marker survives so we can still see where it was.

    Always safe to call — does nothing when the harness is disabled.
    """
    if not _ENABLED:
        yield
        return
    # Emit a start marker BEFORE the work begins so crashes inside the
    # block leave a trail in the JSONL.  Flushed to disk immediately.
    start_row = {
        "event": event,
        "ts": _iso_now(),
        "session_label": _SESSION_LABEL,
        "kind": "span_start",
    }
    start_row.update(_clean_fields(fields))
    _record_event(start_row)
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000.0
        _record_span(event, duration_ms, fields)


def stamp(event: str, **fields: Any) -> None:
    """Record an instantaneous event (no duration)."""
    if not _ENABLED:
        return
    _record_event({
        "event": event,
        "ts": _iso_now(),
        "session_label": _SESSION_LABEL,
        "kind": "stamp",
        **_clean_fields(fields),
    })


def timed(event: str):
    """Decorator form of `span` for functions whose whole body is the
    measurement target.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            with span(event):
                return func(*args, **kwargs)
        wrapper.__name__ = getattr(func, "__name__", "timed")
        wrapper.__doc__ = getattr(func, "__doc__", "")
        return wrapper
    return decorator


@contextmanager
def aggregate_span(event: str):
    """Accumulate timing into a per-event counter without writing a
    per-call row.  Use this for hot loops that run 60K+ times — the
    summary row is written by `flush_aggregate`.
    """
    if not _ENABLED:
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000.0
        with _LOCK:
            bucket = _AGGREGATE_TOTALS[event]
            bucket["count"] += 1
            bucket["total_ms"] += duration_ms
            if duration_ms > bucket["max_ms"]:
                bucket["max_ms"] = duration_ms


def flush_aggregate(event: str) -> None:
    """Emit a summary row for an aggregate counter and reset it."""
    if not _ENABLED:
        return
    with _LOCK:
        bucket = _AGGREGATE_TOTALS.pop(event, None)
        if not bucket or bucket["count"] == 0:
            return
        avg_ms = bucket["total_ms"] / bucket["count"]
        _record_event({
            "event": event,
            "ts": _iso_now(),
            "session_label": _SESSION_LABEL,
            "kind": "aggregate",
            "count": bucket["count"],
            "total_ms": round(bucket["total_ms"], 3),
            "avg_ms": round(avg_ms, 4),
            "max_ms": round(bucket["max_ms"], 3),
        })


# ── Aggregation / summary ────────────────────────────────────────────────────


def recorded_events() -> List[dict]:
    """Return a shallow copy of the ring buffer for inspection."""
    with _LOCK:
        return list(_RING)


def summarize_events(events: Iterable[dict]) -> List[dict]:
    """Group events by name and compute count / total / percentile stats.

    Pure function — does not touch module state.  Used by
    `write_summary_report` and by tests.
    """
    by_event: Dict[str, List[float]] = defaultdict(list)
    aggregates: Dict[str, dict] = {}
    for row in events:
        if not isinstance(row, dict):
            continue
        name = row.get("event")
        if not name:
            continue
        kind = row.get("kind")
        if kind == "span_start":
            # Breadcrumb-only; the matching `span` event carries the
            # duration.  Skip so we don't double-count.
            continue
        if kind == "span":
            duration = row.get("duration_ms")
            if isinstance(duration, (int, float)):
                by_event[name].append(float(duration))
        elif kind == "aggregate":
            aggregates.setdefault(name, {
                "count": 0, "total_ms": 0.0, "max_ms": 0.0,
            })
            entry = aggregates[name]
            entry["count"] += int(row.get("count", 0) or 0)
            entry["total_ms"] += float(row.get("total_ms", 0.0) or 0.0)
            entry["max_ms"] = max(entry["max_ms"], float(row.get("max_ms", 0.0) or 0.0))
    summary: List[dict] = []
    for name, values in by_event.items():
        values.sort()
        n = len(values)
        total = sum(values)
        summary.append({
            "event": name,
            "kind": "span",
            "count": n,
            "total_ms": round(total, 3),
            "avg_ms": round(total / n, 4) if n else 0.0,
            "min_ms": round(values[0], 3),
            "max_ms": round(values[-1], 3),
            "p50_ms": round(_percentile(values, 0.5), 3),
            "p95_ms": round(_percentile(values, 0.95), 3),
            "p99_ms": round(_percentile(values, 0.99), 3),
        })
    for name, entry in aggregates.items():
        count = entry["count"]
        avg = entry["total_ms"] / count if count else 0.0
        summary.append({
            "event": name,
            "kind": "aggregate",
            "count": count,
            "total_ms": round(entry["total_ms"], 3),
            "avg_ms": round(avg, 4),
            "min_ms": 0.0,
            "max_ms": round(entry["max_ms"], 3),
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
        })
    summary.sort(key=lambda r: r["total_ms"], reverse=True)
    return summary


def top_slowest(events: Iterable[dict], *, limit: int = 10) -> List[dict]:
    """Return the `limit` individual spans with the highest duration."""
    candidates = [
        row for row in events
        if isinstance(row, dict) and row.get("kind") == "span"
    ]
    candidates.sort(key=lambda r: float(r.get("duration_ms", 0.0) or 0.0), reverse=True)
    return candidates[:limit]


def format_summary_report(events: Iterable[dict]) -> str:
    """Build a human-readable plain-text summary."""
    summary = summarize_events(events)
    slowest = top_slowest(events, limit=10)
    lines: List[str] = []
    wall_start = _SESSION_START_WALL.isoformat(timespec="seconds") if _SESSION_START_WALL else "(unknown)"
    lines.append(f"=== PO Builder Perf Summary — session {wall_start} ===")
    if _SESSION_LABEL:
        lines.append(f"Session label: {_SESSION_LABEL}")
    if _SESSION_START_MONO is not None:
        elapsed = time.perf_counter() - _SESSION_START_MONO
        lines.append(f"Total session duration: {_format_duration(elapsed)}")
    lines.append("")
    header = (
        f"{'event':<50}"
        f"{'count':>8}"
        f"{'total_ms':>12}"
        f"{'avg':>10}"
        f"{'min':>10}"
        f"{'max':>10}"
        f"{'p50':>10}"
        f"{'p95':>10}"
        f"{'p99':>10}"
    )
    lines.append(header)
    lines.append("─" * len(header))
    for row in summary:
        suffix = " [agg]" if row.get("kind") == "aggregate" else ""
        name = (row["event"] + suffix)[:50]
        lines.append(
            f"{name:<50}"
            f"{row['count']:>8}"
            f"{row['total_ms']:>12.1f}"
            f"{row['avg_ms']:>10.2f}"
            f"{row['min_ms']:>10.2f}"
            f"{row['max_ms']:>10.2f}"
            f"{row['p50_ms']:>10.2f}"
            f"{row['p95_ms']:>10.2f}"
            f"{row['p99_ms']:>10.2f}"
        )
    lines.append("")
    lines.append("=== Top 10 slowest individual events ===")
    for idx, row in enumerate(slowest, start=1):
        ts = row.get("ts", "")
        ts_short = ts.split("T", 1)[-1][:12] if "T" in ts else ts
        duration = float(row.get("duration_ms", 0.0))
        name = row.get("event", "")
        lines.append(f"  {idx:>2}. {name:<50}  {duration:>10.1f} ms  at {ts_short}")
    return "\n".join(lines) + "\n"


def write_summary_report(path: Optional[str] = None) -> Optional[str]:
    """Write the aggregate summary to *path* (or the default) and return
    the path.  Returns None when the harness has never been enabled.
    """
    with _LOCK:
        events = list(_RING)
    if not events:
        return None
    target = path or _SUMMARY_PATH or _default_summary_path(_LOG_PATH or _default_log_path())
    text = format_summary_report(events)
    try:
        directory = os.path.dirname(target)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(text)
    except OSError:
        return None
    return target


# ── Internals ────────────────────────────────────────────────────────────────


def _record_span(event: str, duration_ms: float, fields: Dict[str, Any]) -> None:
    row = {
        "event": event,
        "ts": _iso_now(),
        "session_label": _SESSION_LABEL,
        "kind": "span",
        "duration_ms": round(duration_ms, 3),
    }
    row.update(_clean_fields(fields))
    _record_event(row)


def _record_event(row: dict) -> None:
    with _LOCK:
        _RING.append(row)
    _write_jsonl(row)


def _write_jsonl(row: dict) -> None:
    path = _LOG_PATH
    if not path:
        return
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
            # Flush + fsync so a subsequent process crash still leaves
            # the row on disk.  Slightly slower but essential for the
            # "app died mid-parse" diagnosis case — without it we lose
            # the breadcrumb that would tell us where the crash was.
            try:
                handle.flush()
                os.fsync(handle.fileno())
            except OSError:
                pass
    except OSError:
        return


def _clean_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    """Strip non-JSON-safe values from a field dict."""
    cleaned: Dict[str, Any] = {}
    for key, value in (fields or {}).items():
        if value is None or isinstance(value, (bool, int, float, str)):
            cleaned[key] = value
        else:
            cleaned[key] = repr(value)
    return cleaned


def _percentile(sorted_values: List[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    # Nearest-rank percentile — simple, stable, matches what operators
    # expect from "p95" without argument about linear interpolation.
    rank = max(0, min(len(sorted_values) - 1, int(round(fraction * (len(sorted_values) - 1)))))
    return sorted_values[rank]


def _iso_now() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def _format_duration(seconds: float) -> str:
    if seconds < 1.0:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes = int(seconds // 60)
    rem = seconds - minutes * 60
    return f"{minutes}m {rem:.1f}s"


def _default_data_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _default_log_path() -> str:
    return os.path.join(_default_data_dir(), "perf_trace.jsonl")


def _default_summary_path(log_path: str) -> str:
    directory = os.path.dirname(log_path) or _default_data_dir()
    return os.path.join(directory, "perf_summary.txt")


# ── Auto-enable hook ─────────────────────────────────────────────────────────


def maybe_auto_enable() -> None:
    """Enable the harness automatically when the environment asks for it.

    Triggered conditions:
        - DEBUG_PERF=1 in the environment
        - A file named `perf_trace.enabled` exists in the data folder
    Callers invoke this at app startup so the trace covers the whole
    session from parse through export.
    """
    if _ENABLED:
        return
    want_env = str(os.environ.get("DEBUG_PERF", "") or "").strip().lower() in ("1", "true", "yes", "on")
    flag_path = os.path.join(_default_data_dir(), "perf_trace.enabled")
    want_flag = os.path.isfile(flag_path)
    if want_env or want_flag:
        enable(session_label="auto")


def _atexit_summary() -> None:
    """Flush aggregate counters and write the summary on clean shutdown."""
    try:
        if _ENABLED:
            for name in list(_AGGREGATE_TOTALS.keys()):
                flush_aggregate(name)
            disable(write_summary=True)
    except Exception:
        pass


atexit.register(_atexit_summary)
