from dataclasses import asdict, is_dataclass
import json
import os
import tempfile
import time
from collections import defaultdict
from datetime import datetime

import shipping_flow


LOCK_TIMEOUT_SECONDS = 10
LOCK_STALE_SECONDS = 120


def _ensure_parent_dir(path):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)


def _get_meta(path):
    try:
        stat = os.stat(path)
    except FileNotFoundError:
        return None
    return {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size}


def _atomic_write_text(path, content, encoding="utf-8"):
    _ensure_parent_dir(path)
    directory = os.path.dirname(path) or "."
    fd, temp_path = tempfile.mkstemp(prefix=".tmp_", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(content)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _acquire_lock(path, timeout_seconds=LOCK_TIMEOUT_SECONDS, stale_seconds=LOCK_STALE_SECONDS):
    lock_path = path + ".lock"
    deadline = time.time() + timeout_seconds
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(str(time.time()))
            return lock_path
        except FileExistsError:
            try:
                age_seconds = time.time() - os.path.getmtime(lock_path)
                if age_seconds > stale_seconds:
                    os.remove(lock_path)
                    continue
            except OSError:
                pass
            if time.time() >= deadline:
                raise TimeoutError(f"Timed out waiting for lock: {os.path.basename(path)}")
            time.sleep(0.1)


def _release_lock(lock_path):
    try:
        os.remove(lock_path)
    except OSError:
        pass


def validate_storage_directory(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_test.tmp")
        _atomic_write_text(probe, "ok")
        os.remove(probe)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def load_json_file(path, default, with_meta=False):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
                if isinstance(default, dict) and not isinstance(payload, dict):
                    payload = default
                elif isinstance(default, list) and not isinstance(payload, list):
                    payload = default
                if with_meta:
                    return payload, _get_meta(path)
                return payload
        except Exception:
            pass
    if with_meta:
        return default, _get_meta(path)
    return default


def save_json_file(path, payload):
    _atomic_write_text(path, json.dumps(payload, indent=2), encoding="utf-8")


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


def load_order_rules_with_meta(path):
    """Load per-item buy rules from disk with file metadata."""
    return load_json_file(path, {}, with_meta=True)


def load_vendor_policies(path):
    """Load per-vendor shipping/release policies from disk."""
    payload = load_json_file(path, {})
    return _normalize_vendor_policies_payload(payload)


def load_vendor_policies_with_meta(path):
    """Load per-vendor shipping/release policies from disk with file metadata."""
    payload, meta = load_json_file(path, {}, with_meta=True)
    return _normalize_vendor_policies_payload(payload), meta


def _normalize_vendor_policies_payload(payload):
    normalized = {}
    for vendor, policy in (payload or {}).items():
        vendor_code = str(vendor or "").strip().upper()
        if not vendor_code:
            continue
        normalized[vendor_code] = shipping_flow.normalize_vendor_policy(policy)
    return normalized


def _merge_dict_by_key(base, current_on_disk, desired):
    merged = dict(current_on_disk)
    conflict = False
    all_keys = set(base) | set(current_on_disk) | set(desired)
    for key in all_keys:
        base_value = base.get(key)
        disk_value = current_on_disk.get(key)
        desired_value = desired.get(key)
        if desired_value == base_value:
            continue
        if disk_value == base_value or desired_value == disk_value:
            if key in desired:
                merged[key] = desired_value
            else:
                merged.pop(key, None)
            continue
        conflict = True
        if key in desired:
            merged[key] = desired_value
        else:
            merged.pop(key, None)
    return merged, conflict


def save_order_rules(path, rules, base_rules=None):
    """Save per-item buy rules to disk."""
    lock_path = _acquire_lock(path)
    try:
        current_on_disk, _ = load_order_rules_with_meta(path)
        merged, conflict = _merge_dict_by_key(base_rules or {}, current_on_disk, rules)
        save_json_file(path, merged)
        return {"payload": merged, "meta": _get_meta(path), "conflict": conflict}
    finally:
        _release_lock(lock_path)


def save_vendor_policies(path, policies, base_policies=None):
    """Save per-vendor shipping/release policies to disk."""
    lock_path = _acquire_lock(path)
    try:
        current_on_disk, _ = load_vendor_policies_with_meta(path)
        normalized_base = _normalize_vendor_policies_payload(base_policies or {})
        normalized_desired = _normalize_vendor_policies_payload(policies or {})
        merged, conflict = _merge_dict_by_key(normalized_base, current_on_disk, normalized_desired)
        merged = _normalize_vendor_policies_payload(merged)
        save_json_file(path, merged)
        return {"payload": merged, "meta": _get_meta(path), "conflict": conflict}
    finally:
        _release_lock(lock_path)


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
                line_code = str(item.get("line_code", "")).strip()
                item_code = str(item.get("item_code", "")).strip()
                try:
                    qty = max(0, int(float(item.get("qty", 0) or 0)))
                except Exception:
                    continue
                vendor = str(item.get("vendor", "")).strip().upper()
                if not line_code or not item_code or qty <= 0:
                    continue
                key = (line_code, item_code)
                recent[key].append({
                    "qty": qty,
                    "vendor": vendor,
                    "date": session["date"][:10],
                })
        except Exception:
            continue
    return recent


def append_order_history(path, assigned_items, now=None):
    """Append a new session's orders to the history file."""
    lock_path = _acquire_lock(path)
    try:
        history = load_order_history(path)
        current = now or datetime.now()
        exported_items = []
        for item in assigned_items:
            line_code = str(item.get("line_code", "")).strip()
            item_code = str(item.get("item_code", "")).strip()
            try:
                qty = max(0, int(float(item.get("order_qty", 0) or 0)))
            except Exception:
                continue
            vendor = str(item.get("vendor", "")).strip().upper()
            if not line_code or not item_code or qty <= 0:
                continue
            exported_items.append({
                "line_code": line_code,
                "item_code": item_code,
                "qty": qty,
                "vendor": vendor,
                "export_batch_type": str(item.get("export_batch_type", "") or "").strip(),
                "export_scope_label": str(item.get("export_scope_label", "") or "").strip(),
                "release_decision": str(item.get("release_decision", "") or "").strip(),
                "target_order_date": str(item.get("target_order_date", "") or "").strip(),
                "target_release_date": str(item.get("target_release_date", "") or "").strip(),
                "exported_for_order_date": str(item.get("exported_for_order_date", "") or "").strip(),
                "exported_for_release_date": str(item.get("exported_for_release_date", "") or "").strip(),
            })
        if not exported_items:
            return {"payload": history, "meta": _get_meta(path), "conflict": False}
        session = {
            "date": current.isoformat(),
            "items": exported_items,
        }
        history.append(session)
        save_order_history(path, history)
        return {"payload": history, "meta": _get_meta(path), "conflict": False}
    finally:
        _release_lock(lock_path)


def load_duplicate_whitelist(path, with_meta=False):
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
    if with_meta:
        return whitelist, _get_meta(path)
    return whitelist


def save_duplicate_whitelist(path, whitelist, base_whitelist=None):
    """Save the whitelist set to disk."""
    lock_path = _acquire_lock(path)
    try:
        disk_whitelist = load_duplicate_whitelist(path)
        base = set(base_whitelist or set())
        desired = set(whitelist)
        merged = (set(disk_whitelist) | (desired - base)) - (base - desired)
        content = "".join(f"{ic}\n" for ic in sorted(merged))
        _atomic_write_text(path, content, encoding="utf-8")
        return {"payload": merged, "meta": _get_meta(path), "conflict": False}
    finally:
        _release_lock(lock_path)


def load_ignored_items(path, with_meta=False):
    """Load the set of ignored item keys."""
    return load_duplicate_whitelist(path, with_meta=with_meta)


def save_ignored_items(path, ignored_items, base_ignored_items=None):
    """Save the ignored item key set to disk."""
    return save_duplicate_whitelist(path, ignored_items, base_whitelist=base_ignored_items)


def load_vendor_codes(path, default=None, with_meta=False):
    """Load persisted vendor codes from disk, one code per line."""
    codes = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    code = line.strip().upper()
                    if code and code not in codes:
                        codes.append(code)
        except Exception:
            pass
    if codes:
        payload = codes
    else:
        payload = list(default or [])
    if with_meta:
        return payload, _get_meta(path)
    return payload


def save_vendor_codes(path, vendor_codes, base_vendor_codes=None):
    """Persist vendor codes to disk, one code per line."""
    lock_path = _acquire_lock(path)
    try:
        disk_codes = load_vendor_codes(path, default=[])
        base = {str(code).strip().upper() for code in (base_vendor_codes or []) if str(code).strip()}
        desired = {str(code).strip().upper() for code in vendor_codes if str(code).strip()}
        disk = {str(code).strip().upper() for code in disk_codes if str(code).strip()}
        merged = sorted((disk | (desired - base)) - (base - desired))
        content = "".join(f"{code}\n" for code in merged)
        _atomic_write_text(path, content, encoding="utf-8")
        return {"payload": merged, "meta": _get_meta(path), "conflict": False}
    finally:
        _release_lock(lock_path)


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


def load_suspense_carry_with_meta(path, now=None, max_age_days=14):
    """Load persisted suspense carry with file metadata."""
    return load_suspense_carry(path, now=now, max_age_days=max_age_days), _get_meta(path)


def _prune_suspense_payload(payload, now=None, max_age_days=14):
    current = now or datetime.now()
    pruned = {}
    for raw_key, entry in payload.items():
        try:
            qty = max(0, int(float(entry.get("qty", 0))))
            if qty <= 0:
                continue
            updated_at = entry.get("updated_at", "")
            if updated_at:
                age_days = (current - datetime.fromisoformat(updated_at)).total_seconds() / 86400
                if age_days > max_age_days:
                    continue
            pruned[raw_key] = {"qty": qty, "updated_at": updated_at}
        except Exception:
            continue
    return pruned


def save_suspense_carry(path, carry, now=None, base_carry=None):
    """Persist suspense carry keyed by (line_code, item_code)."""
    current = now or datetime.now()
    max_age_days = 14
    desired_payload = {}
    for (line_code, item_code), entry in carry.items():
        try:
            qty = max(0, int(float(entry.get("qty", 0))))
        except Exception:
            continue
        if qty <= 0:
            continue
        desired_payload[f"{line_code}:{item_code}"] = {
            "qty": qty,
            "updated_at": entry.get("updated_at") or current.isoformat(),
        }
    normalized_base = {}
    for (line_code, item_code), entry in (base_carry or {}).items():
        normalized_base[f"{line_code}:{item_code}"] = {
            "qty": entry.get("qty"),
            "updated_at": entry.get("updated_at", ""),
        }
    lock_path = _acquire_lock(path)
    try:
        disk_payload = _prune_suspense_payload(
            load_json_file(path, {}),
            now=current,
            max_age_days=max_age_days,
        )
        merged_payload, conflict = _merge_dict_by_key(normalized_base, disk_payload, desired_payload)
        save_json_file(path, merged_payload)
        merged_lookup = load_suspense_carry(path, now=current, max_age_days=max_age_days)
        return {"payload": merged_lookup, "meta": _get_meta(path), "conflict": conflict}
    finally:
        _release_lock(lock_path)


def save_session_snapshot(directory, snapshot, now=None):
    """Persist a session snapshot JSON artifact and return its path."""
    current = now or datetime.now()
    os.makedirs(directory, exist_ok=True)
    filename = f"Session_{current.strftime('%Y%m%d_%H%M%S_%f')}_{os.getpid()}.json"
    path = os.path.join(directory, filename)
    _atomic_write_text(path, json.dumps(_to_jsonable(snapshot), indent=2), encoding="utf-8")
    return path


def load_session_snapshots(directory, max_count=3):
    """
    Load the most recent `max_count` session snapshot JSON files from `directory`.
    Returns a list of dicts (raw JSON), most-recent first.  Files that cannot be
    parsed are silently skipped.
    """
    if not os.path.isdir(directory):
        return []
    try:
        entries = [
            e for e in os.scandir(directory)
            if e.is_file() and e.name.startswith("Session_") and e.name.endswith(".json")
        ]
    except OSError:
        return []
    entries.sort(key=lambda e: e.stat().st_mtime, reverse=True)
    snapshots = []
    for entry in entries[:max_count]:
        try:
            with open(entry.path, "r", encoding="utf-8") as f:
                snapshots.append(json.load(f))
        except Exception:
            continue
    return snapshots


def extract_order_history(snapshots):
    """
    Derive per-item order-quantity history from a list of raw session snapshot dicts.

    Returns a dict keyed by (line_code, item_code) → sorted list of final_qty values
    (one per snapshot that contains that item).  Only positive final_qty values are
    included.
    """
    history = defaultdict(list)
    for snap in snapshots:
        assigned = snap.get("assigned_items") or []
        for item in assigned:
            line_code = item.get("line_code") or ""
            item_code = item.get("item_code") or ""
            if not line_code or not item_code:
                continue
            qty = item.get("final_qty")
            if isinstance(qty, (int, float)) and qty > 0:
                history[(line_code, item_code)].append(int(qty))
    return dict(history)
