# Release Notes — v0.4.2

**Date:** 2026-04-02

---

## Summary

v0.4.2 fixes a bug that prevented the auto-update download path from ever
activating. When a newer release is available on GitHub and the release
includes a `POBuilder.exe` asset, the app now offers to download and install
the update directly — no browser required.

857 tests pass.

---

## What changed since v0.4.1

### Bug fix — auto-update download path was never reached (`po_builder.py`)

`fetch_latest_github_release` built its return dict by hand and omitted the
`assets` field from the GitHub API response. `update_flow.find_exe_asset` then
always received an empty list and returned `None`, making the condition
`can_self_update() and exe_url` permanently False. The self-update prompt was
never shown; users only ever saw the fallback "Open release page?" dialog.

**Fix:** `assets` is now forwarded from the API payload:

```python
"assets": payload.get("assets") or [],
```

The full auto-update flow on a packaged `.exe` is now active:

1. 1.5 s after launch a background thread checks the GitHub releases API.
2. If a newer tag is found **and** the release has a `.exe` asset, the dialog
   reads: *"Download and install now? (The app will restart.)"*
3. **Yes** — the exe downloads in the background. When complete, a *"Ready to
   Install"* prompt appears. Confirming launches a detached batch script that
   waits for the app to exit, swaps the file in place, and relaunches.
4. **No** — opens the release page in the browser.
5. **Cancel** — dismissed until next launch.
6. If no `.exe` asset is attached to the release (or the app is running from
   source), behaviour is unchanged: browser fallback only.

**Requirement:** each GitHub release must have `POBuilder.exe` uploaded as a
release asset for the download path to activate.

---

## Test count

| Release | Tests |
|---------|-------|
| v0.3.0  |   756 |
| v0.4.0  |   830 |
| v0.4.1  |   854 |
| v0.4.2  |   857 |

3 new tests: `test_fetch_latest_github_release_parses_expected_fields` updated
to assert assets are forwarded; `test_fetch_latest_github_release_passes_assets_to_find_exe_asset`
confirms `find_exe_asset` resolves the download URL from a real fetch result;
two new `test_app_runtime_flow` cases verify that `prompt_for_update` takes the
self-update path when an exe asset is present and falls back to the browser
dialog when it is not.
