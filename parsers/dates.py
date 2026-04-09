"""X4 date parsing with LRU-style cache."""

from datetime import datetime

_PARSE_X4_DATE_CACHE: dict = {}
_PARSE_X4_DATE_CACHE_MAX = 50_000


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
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(txt, fmt)
            break
        except ValueError:
            continue
    if parsed is not None and len(_PARSE_X4_DATE_CACHE) < _PARSE_X4_DATE_CACHE_MAX:
        _PARSE_X4_DATE_CACHE[txt] = parsed
    return parsed
