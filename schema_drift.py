"""CSV schema drift detection for source reports.

The operator runs PO Builder against the same set of X4 reports each week.
When ERP configuration changes or a new report template is deployed, the
column layout of the exported CSV changes silently — the file still parses,
but individual columns may now mean something different.  The v0.8.13
"tksheet binding name change broke all grid edits" saga is the cousin of
this class of bug: a schema change you only notice by stumbling over bad
output.

This module hashes the first non-empty row of each source CSV and stores
the result in ``po_builder_settings.json``.  At the next load, any file
whose header hash differs from the stored value surfaces a startup warning
so the operator can verify the columns before trusting the numbers.

Design notes:
- Hash is SHA1 over the lowercased, whitespace-normalized join of the
  header cells.  SHA1 is fine here (not a security boundary — we are
  comparing equality, not defending against a hostile collision).
- We strip trailing empty cells so Excel's habit of adding a few empty
  trailing commas doesn't trip a false positive.
- If a file is new (no stored hash), we record the hash silently — first
  runs are not drift.
- The check runs only on files that exist; missing files are handled by
  the existing "file not found" path in load_flow.
"""

from __future__ import annotations

import csv
import hashlib
from typing import Iterable, Optional


SCHEMA_HASHES_KEY = "csv_schema_hashes"


def _first_header_row(filepath: str) -> Optional[list[str]]:
    """Return the first non-empty row of ``filepath`` as a list of strings.

    Returns None if the file can't be read or contains no data rows.
    """
    try:
        with open(filepath, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if any(str(cell).strip() for cell in row):
                    return list(row)
    except (OSError, UnicodeDecodeError, csv.Error):
        return None
    return None


def normalize_header(row: Iterable[str]) -> list[str]:
    """Return a comparable representation of a header row.

    Trailing empty cells are dropped (Excel adds them inconsistently), and
    each cell is lowercased with inner whitespace collapsed.
    """
    cells = [" ".join(str(cell).strip().lower().split()) for cell in row]
    while cells and not cells[-1]:
        cells.pop()
    return cells


def hash_header_row(row: Iterable[str]) -> str:
    normalized = normalize_header(row)
    payload = "||".join(normalized).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def hash_csv_header(filepath: str) -> Optional[str]:
    row = _first_header_row(filepath)
    if row is None:
        return None
    return hash_header_row(row)


def compute_schema_hashes(file_paths: dict) -> dict:
    """Hash the header row of each file in ``file_paths``.

    Parameters
    ----------
    file_paths : dict mapping a stable key (e.g. "onhand", "sales") to the
        absolute CSV path.  Missing or unreadable files are skipped.

    Returns a dict of the same keys mapped to hex hashes.
    """
    out = {}
    for key, path in (file_paths or {}).items():
        if not path:
            continue
        digest = hash_csv_header(path)
        if digest is not None:
            out[key] = digest
    return out


def detect_drift(current_hashes: dict, stored_hashes: dict) -> list[str]:
    """Return a list of keys whose header hash changed since last load.

    Keys that are new (present in ``current_hashes`` but not ``stored_hashes``)
    are NOT reported as drift — they would fire on every first run.
    """
    drifted = []
    for key, current in (current_hashes or {}).items():
        prior = (stored_hashes or {}).get(key)
        if prior and prior != current:
            drifted.append(key)
    return sorted(drifted)


def friendly_label(key: str) -> str:
    """Translate a file-paths key into the label used in warnings."""
    return {
        "sales": "Detailed Part Sales",
        "rec": "Received Parts Detail",
        "po": "PO Part Listing by Product Group",
        "susp": "Suspended Items",
        "onhand": "On Hand Min Max Sales",
        "onhand_report": "On Hand Report",
        "packs": "Order Multiples / Pack Sizes",
    }.get(key, key)
