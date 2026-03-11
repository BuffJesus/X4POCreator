from dataclasses import asdict, is_dataclass
import json
import os
from collections import defaultdict
from datetime import datetime


def load_json_file(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def save_json_file(path, payload):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        pass


def _to_jsonable(value):
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, set):
        return sorted(_to_jsonable(v) for v in value)
    return value


def load_order_rules(path):
    """Load per-item buy rules from disk."""
    return load_json_file(path, {})


def save_order_rules(path, rules):
    """Save per-item buy rules to disk."""
    save_json_file(path, rules)


def load_order_history(path):
    """
    Load order history from disk.
    Returns list of dicts: {date, items: [{line_code, item_code, qty, vendor}]}
    """
    return load_json_file(path, [])


def save_order_history(path, history):
    """Save order history to disk."""
    save_json_file(path, history)


def get_recent_orders(path, lookback_days=14, now=None):
    """
    Get a lookup of recently ordered items within the lookback window.
    Returns dict of (line_code, item_code) -> list of {qty, vendor, date}
    """
    history = load_order_history(path)
    current = now or datetime.now()
    cutoff = current.timestamp() - (lookback_days * 86400)
    recent = defaultdict(list)
    for session in history:
        try:
            session_date = datetime.fromisoformat(session["date"])
            if session_date.timestamp() < cutoff:
                continue
            for item in session.get("items", []):
                key = (item["line_code"], item["item_code"])
                recent[key].append({
                    "qty": item["qty"],
                    "vendor": item["vendor"],
                    "date": session["date"][:10],
                })
        except Exception:
            continue
    return recent


def append_order_history(path, assigned_items, now=None):
    """Append a new session's orders to the history file."""
    history = load_order_history(path)
    current = now or datetime.now()
    session = {
        "date": current.isoformat(),
        "items": [
            {
                "line_code": item["line_code"],
                "item_code": item["item_code"],
                "qty": item["order_qty"],
                "vendor": item["vendor"],
            }
            for item in assigned_items
        ],
    }
    history.append(session)
    save_order_history(path, history)


def load_duplicate_whitelist(path):
    """Load the set of item codes whitelisted as intentional duplicates."""
    whitelist = set()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    ic = line.strip()
                    if ic:
                        whitelist.add(ic)
        except Exception:
            pass
    return whitelist


def save_duplicate_whitelist(path, whitelist):
    """Save the whitelist set to disk."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            for ic in sorted(whitelist):
                f.write(ic + "\n")
    except Exception:
        pass


def load_suspense_carry(path, now=None, max_age_days=14):
    """Load persisted suspense carry keyed by (line_code, item_code)."""
    payload = load_json_file(path, {})
    current = now or datetime.now()
    lookup = {}
    for raw_key, entry in payload.items():
        try:
            line_code, item_code = raw_key.split(":", 1)
            qty = max(0, int(float(entry.get("qty", 0))))
            updated_at = entry.get("updated_at", "")
            if updated_at:
                age_days = (current - datetime.fromisoformat(updated_at)).total_seconds() / 86400
                if age_days > max_age_days:
                    continue
            if qty > 0:
                lookup[(line_code, item_code)] = {"qty": qty, "updated_at": updated_at}
        except Exception:
            continue
    return lookup


def save_suspense_carry(path, carry, now=None):
    """Persist suspense carry keyed by (line_code, item_code)."""
    current = now or datetime.now()
    payload = {}
    for (line_code, item_code), entry in carry.items():
        try:
            qty = max(0, int(float(entry.get("qty", 0))))
        except Exception:
            continue
        if qty <= 0:
            continue
        payload[f"{line_code}:{item_code}"] = {
            "qty": qty,
            "updated_at": entry.get("updated_at") or current.isoformat(),
        }
    save_json_file(path, payload)


def save_session_snapshot(directory, snapshot, now=None):
    """Persist a session snapshot JSON artifact and return its path."""
    current = now or datetime.now()
    os.makedirs(directory, exist_ok=True)
    filename = f"Session_{current.strftime('%Y%m%d_%H%M%S')}.json"
    path = os.path.join(directory, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_to_jsonable(snapshot), f, indent=2)
    return path
