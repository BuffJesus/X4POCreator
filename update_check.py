"""GitHub release check and version comparison for PO Builder.

Provides the plumbing to fetch the latest release from GitHub,
compare version strings, and decide whether an update is available.
The download-and-replace mechanics live in ``update_flow.py``.
"""

from __future__ import annotations

import json
import re
import urllib.request
import urllib.error

from app_version import APP_VERSION

GITHUB_REPO = "BuffJesus/X4POCreator"
GITHUB_RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_PAGE_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"


def _parse_version_parts(value: str) -> tuple[int, ...] | None:
    normalized = str(value or "").strip().lstrip("vV")
    # Accept "1.2.3" and "1.2.3-beta1" (strip pre-release suffix)
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", normalized)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def is_release_version(value: str) -> bool:
    return _parse_version_parts(value) is not None


def is_newer_version(candidate: str, current: str) -> bool:
    candidate_parts = _parse_version_parts(candidate)
    current_parts = _parse_version_parts(current)
    if candidate_parts is None or current_parts is None:
        return False
    return candidate_parts > current_parts


def fetch_latest_release(url: str = GITHUB_RELEASES_API_URL, timeout: int = 5) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"PO-Builder/{APP_VERSION}",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {
        "tag_name": str(payload.get("tag_name", "")).strip(),
        "html_url": str(payload.get("html_url", "")).strip() or GITHUB_RELEASES_PAGE_URL,
        "name": str(payload.get("name", "")).strip(),
        "published_at": str(payload.get("published_at", "")).strip(),
        "assets": payload.get("assets") or [],
    }


def check_for_update() -> dict | None:
    """Return release dict if a newer version is available, else None.

    Returns None on network errors or when already up to date.
    """
    try:
        release = fetch_latest_release()
    except (urllib.error.URLError, OSError, ValueError):
        return None
    tag = release.get("tag_name", "")
    if is_newer_version(tag, APP_VERSION):
        return release
    return None
