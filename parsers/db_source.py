"""Direct X4 (IBM Informix) data source for PO Builder.

This is the DB-direct alternative to hand-exporting CSV reports. It reads the
same data the four/seven reports carry — detailed part sales, received-parts
detail, on-hand min/max, and order multiples — straight from the Informix
tables, and returns a ``source_bundle`` whose structures are byte-for-byte the
same shape ``load_flow`` already consumes. It reuses ``parsers.aggregators``
for all derived fields (vendor confidence, receipt_cost_lookup, sales stats),
so the DB path and the CSV path produce identical contracts by construction.

Wiring: ``load_flow.parse_from_database(conn, ...)`` calls
``build_source_bundle`` and feeds it to ``parse_all_files(source_bundle=...)``.

Schema is the validated X4 14.10 layout (server ``rinaxids`` @ ``rinaxserver``,
database ``prx``, DSN ``rinax4gl``). Column names were confirmed against the
decompiled X4 data-access SQL. IMPORTANT: every connection MUST issue
``SET ROLE Rinax_Select_Only`` first or a valid login reads nothing.

None of the SQL executes on import; this module is safe to import without the
Informix client SDK present. ``connect()`` is the only place a driver is needed
and it imports lazily.
"""

from parsers.dates import parse_x4_date

# ── SQL (product_group carries its trailing dash in X4; warehouse 1 = stock) ──

# Inventory: On Hand + Min/Max in one read. mo12_sales has no whse column and is
# left 0 (derive from invoice_detail over the trailing year if needed).
SQL_INVENTORY = """
SELECT w.product_group        AS line_code,
       w.item_code            AS item_code,
       i.description          AS description,
       w.qty_on_hand_stk      AS qoh,
       w.replacement_cost     AS repl_cost,
       w.minimum_stk_point    AS min_stk,
       w.maximum_stk_point    AS max_stk,
       w.num_sales_ytd        AS ytd_sales,
       w.primary_supplier     AS supplier,
       w.date_last_receipt    AS last_receipt,
       w.date_of_last_sale    AS last_sale
FROM whse w
JOIN item i
  ON i.product_group = w.product_group
 AND i.item_code     = w.item_code
WHERE w.warehouse_num = ?
"""

# Order multiple / pack size.
SQL_PACK_SIZES = """
SELECT product_group AS line_code,
       item_code     AS item_code,
       order_multiple AS pack_size
FROM item
WHERE order_multiple > 0
"""

# One row per finalized, sales-affecting invoice line (feeds the sales aggregator).
SQL_DETAILED_SALES = """
SELECT d.product_group AS line_code,
       d.item_code     AS item_code,
       d.description   AS description,
       d.quantity_ship AS qty_sold,
       h.document_date AS sale_date
FROM invoice_detail d
JOIN invoice_header h ON h.invheaderid = d.invheaderid
WHERE h.inv_state = 'F'
  AND d.affect_sales = 'T'
  AND d.quantity_ship <> 0
"""

# Receipt history (feeds the receipt aggregator + receipt_cost_lookup).
# NOTE: po_detail.total_qty_received is CUMULATIVE per PO line, so this yields
# one synthetic receipt row per PO line — receipt_count / pack-size histograms
# are therefore approximate. If a true per-receipt journal/cardex table is
# available, point SQL_RECEIPTS at it for exact per-event granularity.
SQL_RECEIPTS = """
SELECT d.product_group      AS line_code,
       d.item_code          AS item_code,
       d.description        AS description,
       d.total_qty_received AS qty_received,
       d.extended_cost      AS ext_cost,
       d.first_received_date AS receipt_date,
       h.vendor             AS vendor
FROM po_detail d
JOIN po_header h ON h.po_header_id = d.po_header_id
WHERE d.detail_type = 'PA'
  AND d.total_qty_received > 0
"""

_FETCH_BATCH = 5000


# ── connection helpers ────────────────────────────────────────────────────

def connect(dsn="rinax4gl", uid=None, pwd=None, *, autocommit=True):
    """Open a pyodbc connection to X4 and set the read-only role.

    Requires the Informix ODBC driver + the ``rinax4gl`` System DSN (present on
    real X4 workstations, absent on a dev copy). Imports pyodbc lazily so this
    module stays importable everywhere.
    """
    import pyodbc  # lazy: only needed when actually hitting the DB

    parts = [f"DSN={dsn}"]
    if uid:
        parts.append(f"UID={uid}")
    if pwd:
        parts.append(f"PWD={pwd}")
    conn = pyodbc.connect(";".join(parts), autocommit=autocommit)
    set_select_role(conn)
    return conn


def set_select_role(connection):
    """Issue the mandatory ``SET ROLE Rinax_Select_Only``.

    Without this, a valid X4 login reads zero rows (looks like a permission
    error but isn't).
    """
    cur = connection.cursor()
    try:
        cur.execute("SET ROLE Rinax_Select_Only")
    finally:
        cur.close()


# ── row plumbing ──────────────────────────────────────────────────────────

def _dict_rows(cursor):
    """Yield each result row as a dict keyed by lowercased column alias."""
    columns = [col[0].lower() for col in cursor.description]
    while True:
        batch = cursor.fetchmany(_FETCH_BATCH)
        if not batch:
            break
        for row in batch:
            yield dict(zip(columns, row))


def _query(connection, sql, params=()):
    cur = connection.cursor()
    cur.execute(sql, params)
    try:
        yield from _dict_rows(cur)
    finally:
        cur.close()


def _line_code(product_group):
    """Normalize a product group to the app's line-code convention.

    Uppercased, whitespace-stripped, with exactly one trailing dash (X4 already
    stores the dash; this just guarantees it so DB and CSV keys match).
    """
    lc = str(product_group or "").strip().upper()
    if lc and not lc.endswith("-"):
        lc += "-"
    return lc


def _item_code(value):
    return str(value or "").strip()


def _date_str(value):
    """Render a DB date/datetime/str as a string parse_x4_date accepts (ISO)."""
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    return str(value).strip()


def _to_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _to_float_or_none(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ── row iterators (identical dict shape to the CSV iterators) ─────────────

def iter_sales_rows(connection):
    for r in _query(connection, SQL_DETAILED_SALES):
        yield {
            "line_code": _line_code(r.get("line_code")),
            "item_code": _item_code(r.get("item_code")),
            "description": str(r.get("description") or "").strip(),
            "qty_sold": _to_int(r.get("qty_sold")),
            "sale_date": _date_str(r.get("sale_date")),
        }


def iter_receipt_rows(connection):
    for r in _query(connection, SQL_RECEIPTS):
        yield {
            "line_code": _line_code(r.get("line_code")),
            "item_code": _item_code(r.get("item_code")),
            "description": str(r.get("description") or "").strip(),
            "qty_received": _to_int(r.get("qty_received")),
            "ext_cost": _to_float_or_none(r.get("ext_cost")),
            "receipt_date": _date_str(r.get("receipt_date")),
            "vendor": str(r.get("vendor") or "").strip(),
        }


def load_inventory_lookup(connection, *, warehouse_num=1):
    """Return {(line_code, item_code) -> InventoryEntry-shaped dict}."""
    lookup = {}
    for r in _query(connection, SQL_INVENTORY, (warehouse_num,)):
        key = (_line_code(r.get("line_code")), _item_code(r.get("item_code")))
        if not key[1]:
            continue
        lookup[key] = {
            "description": str(r.get("description") or "").strip(),
            "qoh": _to_float_or_none(r.get("qoh")),
            "repl_cost": _to_float_or_none(r.get("repl_cost")),
            "min": _int_or_none(r.get("min_stk")),
            "max": _int_or_none(r.get("max_stk")),
            "ytd_sales": _to_int(r.get("ytd_sales")),
            "mo12_sales": 0,
            "supplier": str(r.get("supplier") or "").strip().upper(),
            "last_receipt": _date_str(r.get("last_receipt")),
            "last_sale": _date_str(r.get("last_sale")),
        }
    return lookup


def load_pack_size_lookup(connection):
    """Return {(line_code, item_code) -> int pack size} for order_multiple > 0."""
    lookup = {}
    for r in _query(connection, SQL_PACK_SIZES):
        key = (_line_code(r.get("line_code")), _item_code(r.get("item_code")))
        if not key[1]:
            continue
        ps = _to_int(r.get("pack_size"))
        if ps > 0:
            lookup[key] = ps
    return lookup


def _int_or_none(value):
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


# ── top-level bundle ──────────────────────────────────────────────────────

def build_source_bundle(connection, *, warehouse_num=1, parse_date=None):
    """Build the full source_bundle load_flow.parse_all_files consumes.

    Returns a dict with: sales_items, sales_window, detailed_sales_rows,
    receipt_history_lookup, receipt_cost_lookup, detailed_sales_stats_lookup,
    inventory_lookup, pack_size_lookup.
    """
    import parsers  # lazy to avoid an import cycle at module load

    parse_date = parse_date or parse_x4_date
    aggregates = parsers.parse_detailed_pair_aggregates(
        None, None,
        sales_rows=iter_sales_rows(connection),
        receipt_rows=iter_receipt_rows(connection),
        parse_date=parse_date,
    )
    bundle = dict(aggregates)
    bundle["inventory_lookup"] = load_inventory_lookup(connection, warehouse_num=warehouse_num)
    bundle["pack_size_lookup"] = load_pack_size_lookup(connection)
    return bundle
