# Release Notes — v0.5.1

**Date:** 2026-04-02

---

## Summary

v0.5.1 adds a "Check Now" button for manual update checks with diagnostic
output, making it straightforward to identify exactly why the auto-install path
is or isn't available.

922 tests pass.

---

## What changed since v0.5.0

### Improvement — Manual update check with diagnostics (`app_runtime_flow.py`, `ui_load.py`)

The auto-update dialog previously fell back silently to "Open release page?"
with no explanation, giving no signal as to whether the problem was a missing
asset, a wrong filename, or running from source.

**"Check Now" button** added to the Load tab (next to the startup check
checkbox). Clicking it runs a synchronous update check and shows one of:

| Situation | Message |
|-----------|---------|
| Already up to date | "You are up to date. Current: v0.5.1 / Latest: v0.5.1" |
| Update + exe asset + packaged exe | Triggers the "Download & install" dialog directly |
| Update + **no release assets at all** | "No release assets found. Attach POBuilder.exe as a release asset to enable auto-install." |
| Update + assets present but **none end in .exe** | "N asset(s) found, but none end in .exe. Ensure the file is named POBuilder.exe." |
| Update + running **from source** (not packaged exe) | "Auto-install is only available in the packaged .exe. Running from source — manual download required." |
| Network error | "Could not reach GitHub: [error detail]" |

All paths end with "Open the release page to download manually?" so the user
always has a fallback.

---

## How to verify auto-update is working end-to-end

1. Click **Check Now** on the Load tab.
2. If a newer version is available, the dialog will tell you exactly what it
   found (or what is missing).
3. The most common issue is no `.exe` asset on the GitHub release — attach
   `POBuilder.exe` from `dist\` to the release and try again.

---

## Test count

| Release | Tests |
|---------|-------|
| v0.5.0  |   916 |
| v0.5.1  |   922 |

6 new tests in `test_app_runtime_flow.py` covering all diagnostic message
paths for `check_for_updates_now`.
