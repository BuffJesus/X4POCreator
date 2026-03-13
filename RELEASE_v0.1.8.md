# PO Builder v0.1.8

Release date: 2026-03-12

## Summary

This release is the strongest `0.1.x` stepping stone toward `v0.2.0` so far. It continues the shared-data hardening work, significantly reduces maintenance risk in `po_builder.py`, and expands regression coverage around the refactors that support the main workflow.

## Highlights

- Continued decomposing `po_builder.py` into focused helper modules without changing user-facing workflow behavior.
- Normalized demand to the effective report span so long sales windows do not inflate reorder suggestions unrealistically.
- Improved bulk right-click and removal behavior so context-menu actions better respect the intended row selection.
- Added a clearer release/debug build path in `build.bat` and aligned packaging specs around the current asset set.
- Added direct regression coverage for shared-data refresh, persistence helpers, runtime/update behavior, loading helpers, reorder calculations, UI state helpers, review editing, and bulk-sheet actions.
- Kept the full automated suite green while increasing coverage from `175` passing tests at the start of this work to `205`.

## Main-Controller Decomposition

This release extracts more high-churn controller logic into focused modules:

- `data_folder_flow.py`
- `persistent_state_flow.py`
- `session_state_flow.py`
- `app_runtime_flow.py`
- `loading_flow.py`
- `reorder_flow.py`
- `ui_state_flow.py`
- `review_flow.py`
- `bulk_sheet_actions_flow.py`

These extractions keep `POBuilderApp` method names stable while moving logic behind testable module-level helpers.

## Shared-Data And Persistence

- Shared/local folder switching and active-data refresh remain hardened and regression-tested.
- Persistent save/merge paths for vendor codes, order rules, duplicate whitelist, ignored items, and suspense carry are now isolated from the main controller.
- Shared-data conflict handling for `suspense_carry.json` remains in place from the earlier `0.1.7` work and is now surrounded by stronger refactor coverage.

## Workflow Reliability

- Reorder-cycle and recent-order refresh behavior now live in dedicated helpers with direct tests.
- Demand signals are now normalized against the detected sales report span before suggestion logic is applied, reducing over-ordering risk from long export windows.
- Review edit application for vendor, quantity, and pack-size paths is extracted and covered directly.
- Bulk-sheet selection, shortcut fill, navigation, and begin-edit helper paths continue to behave the same while living outside the main controller.
- Bulk right-click selection handling now preserves in-selection context more reliably before the menu command fires.

## Build And Packaging

- `build.bat` now supports a `debug` mode for console-visible troubleshooting and a clearer release build path.
- Packaging specs were adjusted to match the current bundled assets and openpyxl build flow.

## Verification

- `python -m unittest discover -s tests -q`

## Notes

`v0.1.8` is still not the `v0.2.0` milestone release. The main remaining gaps for `v0.2.0` are workflow-level integration confidence and packaged-app smoke testing, not controller-structure momentum.
