## PO Builder `v0.1.21`

Release date: 2026-03-28

This release focuses on ordering correctness hardening and large-load performance.

### Highlights

- Reorder-worthy candidates are less likely to be missed when demand evidence is weak or upstream joins are incomplete.
- Removal and review flows are safer for protected candidates and weak-coverage items.
- Large CSV loads are more efficient and more transparent, with streamed parsing, parse-result caching, and live load-stage progress.

### Correctness

- Added candidate-preservation so below-floor or trigger-protected items can still enter the assignment session even without strong loaded sales evidence.
- Hardened “Remove Not Needed” so protected reorder candidates are skipped instead of being silently dropped.
- Added dynamic hardware buffering based on available sales-window and demand-shape evidence instead of a mostly fixed two-pack bias.
- Added min/max sanity normalization and explicit review signals when X4 and detailed-sales suggestions disagree materially.
- Added churn damping so small fallback-target changes do not flip reorder outcomes needlessly.
- Clarified pack semantics by separating true pack sizes from explicit exact-quantity overrides.
- Promoted unresolved source-mapping and inventory-coverage-gap cases into explicit review state instead of leaving them only as startup warnings.

### Performance

- Reworked the detailed sales + received parts load path to use streamed aggregation instead of fully materializing the biggest CSVs before reprocessing them.
- Removed remaining full-file `list(reader)` parser hot spots in suspended and pack-size parsing.
- Added a local parse-result cache keyed by report path, size, modified time, and parse settings so unchanged report sets can reload without reparsing.
- Removed the default forced 5-second loading delay.
- Added live loading-overlay stage text for parse/cache/load phases so large loads show what they are doing.

### Validation

- `python -m unittest discover -s tests -q`
- `python -m unittest tests.test_rules tests.test_assignment_flow tests.test_bulk_remove_flow tests.test_ui_bulk_dialogs tests.test_bulk_sheet_actions_flow tests.test_load_flow tests.test_item_workflow tests.test_data_folder_flow tests.test_parsers tests.test_loading_flow -q`
- Built release executable with PyInstaller spec and confirmed `dist\POBuilder.exe` was produced.
