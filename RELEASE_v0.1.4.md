# Release v0.1.4

Tag: `v0.1.4`

Release title: `PO Builder v0.1.4`

## Summary

This patch release tightens the desktop UI so maximized windows behave more predictably, with consistent scroll handling across the main setup and review flows.

## Highlights

- fixed the `Load Files` tab so scrollable content stays pinned to the top instead of leaving a large empty gap when the app is maximized
- stopped mouse-wheel scrolling on scrollable pages and dialogs when the content already fits in view, removing the odd "scrolls even though nothing is off-screen" behavior
- standardized canvas resize and scroll-region syncing across the load screen, line-code filter, customer filter, and bulk-review dialogs
- removed the old ad hoc global mouse-wheel bindings from those screens in favor of shared scroll handling
- added regression coverage for canvas sync behavior and scroll gating

## Notes

- `VERSION` is now `0.1.4`
- recommended git tag: `v0.1.4`
- recommended release target: the commit that contains the shared scroll helper changes plus the UI load, filter, and bulk-dialog scroll fixes

## Suggested Git Commands

```powershell
git add VERSION RELEASE_v0.1.4.md ui_scroll.py ui_load.py ui_filters.py ui_bulk_dialogs.py tests\test_ui_scroll.py
git commit -m "Prepare v0.1.4 release"
git tag -a v0.1.4 -m "PO Builder v0.1.4"
git push origin master
git push origin v0.1.4
```
