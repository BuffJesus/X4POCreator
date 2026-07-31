"""X4 date parsing with LRU-style cache."""

from datetime import datetime

_PARSE_X4_DATE_CACHE: dict = {}
_PARSE_X4_DATE_CACHE_MAX = 50_000

# Locale-independent month map. strptime("%b") resolves month abbreviations
# through the C runtime's LC_TIME; on a non-English Windows locale "20-Nov-2019"
# would fail and silently return None, disabling every recency/sales-window
# calculation. Parse the month ourselves so behaviour is locale-agnostic.
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_x4_date(value):
    if not value:
        return None
    txt = str(value).strip()
    if not txt:
        return None
    cached = _PARSE_X4_DATE_CACHE.get(txt)
    if cached is not None:
        return cached
    parsed = None
    # Format 1: DD-Mon-YYYY (locale-independent month map)
    parts = txt.split("-")
    if len(parts) == 3 and parts[1][:3].lower() in _MONTHS:
        try:
            parsed = datetime(int(parts[2]), _MONTHS[parts[1][:3].lower()], int(parts[0]))
        except (ValueError, KeyError):
            parsed = None
    # Format 2: ISO YYYY-MM-DD (already locale-independent)
    if parsed is None:
        try:
            parsed = datetime.strptime(txt, "%Y-%m-%d")
        except ValueError:
            parsed = None
    if parsed is not None and len(_PARSE_X4_DATE_CACHE) < _PARSE_X4_DATE_CACHE_MAX:
        _PARSE_X4_DATE_CACHE[txt] = parsed
    return parsed
