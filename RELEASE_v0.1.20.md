## PO Builder `v0.1.20`

Release date: 2026-03-17

This is a hotfix release for a load-screen regression in the packaged app.

### Highlights

- Fixed a load-tab regression that could block file selection and folder scan/populate when legacy inputs were hidden.
- File-path selections now survive load-section refreshes instead of being silently dropped.
- Rebuilt the packaged executable with the fix.

### Hotfix details

- Load-file path variables are now created up front for all supported file types, including hidden legacy compatibility inputs.
- The `Browse...`, `Scan & Populate`, and `Load Files & Continue` paths now tolerate hidden optional inputs instead of assuming every field is currently visible.
- Refreshing the load sections no longer recreates those path variables and wipe previously selected files.

### Validation

- `python -m unittest tests.test_ui_load tests.test_po_builder -q`
- `python -m unittest tests.test_ui_load tests.test_po_builder tests.test_load_flow tests.test_parsers -q`
- `cmd /c "build.bat < nul"`
