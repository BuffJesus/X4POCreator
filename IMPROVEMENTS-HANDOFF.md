# PO Builder — improvements from the X4 decompiled source

Branch: **`improvements/db-and-correctness`** (5 commits off `master`).
Full test suite: **913 unittest cases, all green** (`.venv/Scripts/python -m unittest discover -s tests`).

All work was done and tested on the desktop copy. Two features (DB read, native
PO transmission) can only be *fully* validated on a real X4 workstation — this
machine has no Informix client SDK, no `rinax4gl` DSN, and no LAN route to
`rinaxserver`. Those validation steps are flagged **[WORK PC]** below.

## Getting it onto the work computer
It's the same git repo (`github.com/BuffJesus/X4POCreator`). On the work PC:
```
git fetch && git checkout improvements/db-and-correctness
```
(or merge to `master` after review). Nothing else is needed for the correctness
fixes and refactors — they're pure Python and already pass.

---

## What changed

### 1. Correctness fixes (were producing wrong POs / wrong edits)
| Fix | File | Effect |
|---|---|---|
| Bulk vendor-apply hit the wrong item under a filter | `ui_qt/shell.py` | Used `item_at` (visible-space) on a source index → vendor landed on an unrelated item. Now `source_item_at`. |
| Review tab edited/removed the wrong item with >1 vendor | `ui_qt/review_tab.py` | `_visible_items` was encounter-order but the table paints vendor-sorted. Now built in painted order. |
| Command-palette jump selected the wrong row under a filter | `ui_qt/command_palette.py` | Removed a bad source-index remap. |
| A bad On Hand / Min-Max file silently made QOH=0 fleet-wide → catalogue-wide over-order | `load_flow.py` | Hard gate now aborts the load when a provided inventory file fails/empties. |
| Non-English Windows locale silently broke all `DD-Mon-YYYY` dates | `parsers/dates.py` | Locale-independent month map instead of `strptime("%b")`. |
| Export preview $ bypassed the vetted cost logic | `export_flow.py` | Preview now routes through `shipping_flow.item_cost_data` (rejects suspicious costs, receipt-cost fallback). |

### 2. Dead-code removal (maintenance traps)
`rules/__init__.py` (−1144 lines) and `parsers/__init__.py` (−800 lines) carried
large top-of-file blocks that were shadowed by tail re-imports — and had silently
**diverged** from the live modules, so editing them was a no-op. Deletion is
provably behavior-neutral (every removed name was already rebound later). The 5
genuinely-live heuristics moved to `rules/_heuristics.py`.

### 3. Data-quality gate (`load_flow.py`, `ui_qt/`)
`compute_data_quality_summary` was computed by nothing. Now stored on the session
each load, broadened to count both unresolved AND conflicting items, and enforced
with a blocking-but-overridable dialog before assignment.

### 4. **DB-direct ingest** — `parsers/db_source.py` + `load_flow.parse_from_database`
Reads sales, receipts, inventory and pack sizes straight from Informix and feeds
the **identical** downstream pipeline as the CSV path (via a `source_bundle`).
Eliminates the hand-export/browse step and the wrong-file/stale-export error
class. Validated end-to-end through the real pipeline with a **fake** DB
connection; SQL is the validated X4 14.10 schema.

**[WORK PC] to finish/verify:**
1. `pip install pyodbc` into the app's environment (the only new dependency, and
   only for the DB path).
2. Smoke test against the real DB:
   ```python
   from parsers import db_source
   conn = db_source.connect(dsn="rinax4gl")          # sets SET ROLE Rinax_Select_Only
   bundle = db_source.build_source_bundle(conn)       # ~seconds on the real DB
   print(len(bundle["sales_items"]), len(bundle["inventory_lookup"]))
   ```
   Then `load_flow.parse_from_database(conn, old_po_warning_days=90, short_sales_window_days=30)`.
3. Confirm two SQL details flagged as needing a real-schema check:
   - the per-line cost column on `po_detail` (`extended_cost` assumed — used for
     `receipt_cost_lookup`), and
   - whether a true per-receipt journal/cardex table exists. `po_detail.total_qty_received`
     is *cumulative*, so receipt-count/pack histograms are approximate until pointed
     at per-event rows. Adjust `SQL_RECEIPTS` in `db_source.py` if so.
4. **UI button** is not wired yet — `parse_from_database` is the backend entry
   point; add a "Load from X4 database" action in the load tab that calls it and
   passes the result to `apply_load_result`. Keep CSV load as the fallback.

### 5. **X4-native electronic-PO exporter** — `x4_po_export.py`
Reproduces X4's own Rinax fixed-width PO **record body** verbatim from the
decompiled `PO_Header.Rinax_EFile` (byte-exact tests), so a PO can be handed to
X4's transmission path instead of re-keyed from the `.xlsx`.

**[WORK PC] before sending to a live vendor:**
- The **filename + destination folder + FTP** are environment-specific (built from
  the vendor's `remote_orders_setup` row: `transport`, `distribution_center`,
  `file_type` → names like `<transport>_<dc>_<wd>_<file_type>_<wd><po>=_<MMddhhmm>.INTR`
  in `<PO_Remote_Orders_Folder>\Sent\`). These are deliberately **not** hardcoded.
  Confirm your target vendor's `Transmission_Code` and setup row, then pick the
  filename scheme (`rinax_x12_850_filename` is provided for the X12-850 type).
- **Generate one PO and diff it byte-for-byte against a real X4-produced file for
  the same PO before transmitting.** The record layout is faithful to the source,
  but validate the PO-type code and any product-group substitution behaviour.

---

## Notes / caveats
- One earlier review finding — *"demand ÷ full 8-year span dilutes recent demand"*
  (assignment sizing) — was **not** addressed here; it was UNVERIFIED in the prior
  review (rate-limited) and needs its own confirmation before acting.
- The first commit also carries a pre-existing uncommitted `app_version.py` change
  that was already in the working tree when the branch was created.
