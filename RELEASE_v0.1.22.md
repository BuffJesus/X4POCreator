## PO Builder `v0.1.22`

Release date: 2026-03-28

This release is a performance-focused follow-up that reduces load time and improves load visibility on large report sets.

### Highlights

- Large report parsing is more memory-efficient and less repetitive.
- Reloading the same unchanged report set can now skip reparsing entirely.
- The load overlay now reports meaningful stages instead of appearing stalled on one generic message.
- Detailed-sales/inventory reconciliation was optimized to avoid repeated full lookup scans.

### Performance details

- Streamed the high-volume detailed sales and received-parts load path so the app no longer materializes the largest CSVs before reprocessing them.
- Removed the remaining full-file parser hot spots in suspended and pack-size parsing.
- Added a local parse-result cache keyed by file path, size, modified time, and parse settings.
- Removed the default forced 5-second loading delay.
- Added live loading-stage text updates for:
  - cached result reuse
  - detailed sales / received parts parsing
  - open PO, suspended, on hand, min/max, and pack-size parsing
  - detailed-sales/inventory reconciliation
  - warning/summary build
  - cache save
- Optimized detailed-sales line-code reconciliation by precomputing item-code-to-line-code candidates once and reusing them across normalization, unresolved detection, and conflict detection.

### Operational impact

- Repeated loads of the same report set should be much faster because cached parse results can be reused.
- First-time loads of very large detailed-sales datasets should use less memory and spend less time in the reconciliation stage.
- Operators should now see which load stage is active instead of a static "Loading files..." message.

### Validation

- `C:\Users\Cornelio\Desktop\POCreator\.venv\Scripts\python.exe -m unittest discover -s tests -q`
- `C:\Users\Cornelio\Desktop\POCreator\.venv\Scripts\python.exe -m PyInstaller -y PO_Builder.spec`
- Confirmed `dist\POBuilder.exe` was rebuilt successfully.
