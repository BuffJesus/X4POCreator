import os
import sys
from datetime import datetime


if getattr(sys, "frozen", False):
    _DATA_DIR = os.path.dirname(sys.executable)
else:
    _DATA_DIR = os.path.dirname(os.path.abspath(__file__))

DEBUG_LOG_FILE = os.path.join(_DATA_DIR, "debug_trace.log")


def write_debug(event, **fields):
    """Append a compact debug line to the local trace log."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    parts = [timestamp, event]
    for key in sorted(fields):
        value = fields[key]
        if isinstance(value, str):
            safe = value.replace("\r", "\\r").replace("\n", "\\n")
        else:
            safe = repr(value)
        parts.append(f"{key}={safe}")
    line = " | ".join(parts)
    try:
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass
