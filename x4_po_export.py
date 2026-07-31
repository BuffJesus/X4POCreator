"""Emit X4-native electronic purchase-order files.

PO Builder normally writes a styled .xlsx per vendor that the operator hand-keys
/ imports back into X4. This module instead reproduces X4's own native
electronic-PO record layout so a PO can be handed straight to X4's transmission
path (or a vendor), removing the re-keying step.

The record layout below is reproduced verbatim from the decompiled X4 source:
``PO_Header.Rinax_EFile`` in B2.decompiled.cs (RxPad semantics from
A6.decompiled.cs ``RxPad``). This is X4 Transmission_Code 1 ("Rinax" format) —
fixed-width, record-type-prefixed, LF-terminated:

    "1 " header : WD code(8,L) + 10sp + PO#(8,R) + 2sp + vendor(6,L) + type(2) + 1sp
    "2 " detail : product_group+item_code(20,L) + qty(10,R) + 7sp     [one per line]
    "3 " comment: comment text(37,L)                                  [wrapped, optional]
    "*END" + 35sp                                                     [terminator]

(L = left-justified/right-padded, R = right-justified/left-padded; over-long
fields are truncated to the left/right slice exactly as RxPad does.)

IMPORTANT — transmission is environment-specific and is NOT reproduced here:
the real filename and destination come from X4's ``remote_orders_setup`` row for
the vendor's WD customer code (X4 builds names like
``<transport>_<dc>_<wd>_<file_type>_<wd><po>=_<MMddhhmm>.INTR`` and drops them in
``<PO_Remote_Orders_Folder>\\Sent\\``, then FTPs them). A different transmission
code (ASC X12 850) uses ``Rinax<wd>PO<po:09>.txt``. Pick the scheme that matches
your vendor's setup at deploy time — see ``rinax_x12_850_filename`` /
``write_po_file`` and the work-PC handoff notes. Validate a generated file
against a real X4-produced PO before transmitting to a live vendor.
"""

import os

# X4 remote PO type codes (frmRemotePOType radio-group mapping in B2).
PO_TYPE_CODES = {
    "confirming": "C ",
    "standard": "S ",
    "cancel": "X ",
    "return": "R ",
}


def rxpad(value, width, pad_left, pad_char=" "):
    """Port of X4's objGlobalFunctions.RxPad (A6.decompiled.cs).

    Over-long input is truncated: keep the right ``width`` chars when
    ``pad_left`` else the left ``width``. Otherwise pad on the left (right-
    justify) when ``pad_left`` else on the right (left-justify).
    """
    s = "" if value is None else str(value)
    if len(s) > width:
        return s[-width:] if pad_left else s[:width]
    fill = pad_char * (width - len(s))
    return (fill + s) if pad_left else (s + fill)


def _qty_str(qty):
    """Render a quantity the way VB Conversions.ToString(Double) would: an
    integral value has no decimal point (5.0 -> "5"), otherwise keep it."""
    try:
        f = float(qty)
    except (TypeError, ValueError):
        return "0"
    if f == int(f):
        return str(int(f))
    return repr(f)


def _po_type_code(po_type):
    if po_type is None:
        return "  "
    key = str(po_type).strip().lower()
    if key in PO_TYPE_CODES:
        return PO_TYPE_CODES[key]
    # Already a raw 2-char code like "S "? normalize to width 2.
    raw = str(po_type)
    return (raw + "  ")[:2] if raw.strip() else "  "


def build_rinax_po_body(*, wd_customer_code, po_number, vendor_code, lines,
                        po_type="standard"):
    """Build the X4-native Rinax electronic-PO file body (str, LF-terminated).

    ``lines`` is an iterable of dicts with keys ``line_code`` (X4 product_group,
    typically with its trailing dash), ``item_code``, ``qty`` and optional
    ``comments``. Lines with qty == 0 are skipped, exactly as X4 does.
    """
    type_code = _po_type_code(po_type)

    out = []
    header = (
        "1 "
        + rxpad(wd_customer_code, 8, pad_left=False)
        + " " * 10
        + rxpad(str(po_number), 8, pad_left=True)
        + " " * 2
        + rxpad(vendor_code, 6, pad_left=False)
        + type_code
        + " "
    )
    out.append(header + "\n")

    for line in lines:
        qty = line.get("qty", line.get("final_qty", line.get("order_qty", 0)))
        try:
            qty_num = float(qty)
        except (TypeError, ValueError):
            qty_num = 0.0
        if qty_num == 0.0:
            continue
        product_group = str(line.get("line_code", "") or "")
        item_code = str(line.get("item_code", "") or "")
        detail = (
            "2 "
            + rxpad(product_group + item_code, 20, pad_left=False)
            + rxpad(_qty_str(qty_num), 10, pad_left=True)
            + " " * 7
        )
        out.append(detail + "\n")

        comments = line.get("comments")
        if comments:
            # Faithful port of the B2 comment-wrapping loop.
            text = str(comments).replace("\r\n", "\n3 ")
            while len(text) > 0:
                out.append("3 " + rxpad(text[:37], 37, pad_left=False) + "\n")
                text = text[37:] if len(text) > 38 else ""

    out.append("*END" + " " * 35 + "\n")
    return "".join(out)


def rinax_x12_850_filename(wd_customer_code, po_number, *, pad=9):
    """Filename for the ASC X12 850 transmission type: Rinax<wd>PO<po:0pad>.txt.

    (X4's native Rinax type-1 uses an environment-specific name built from the
    remote_orders_setup row and is not reproduced; supply it explicitly.)
    """
    return f"Rinax{wd_customer_code}PO{str(po_number).zfill(pad)}.txt"


def write_po_file(directory, filename, body, *, subfolder="Sent"):
    """Write ``body`` to ``directory/subfolder/filename`` (X4 uses a Sent\\ dir).

    Returns the full path written. Newlines are written verbatim (LF) as X4
    emits them; open in binary to avoid the platform translating them.
    """
    target_dir = os.path.join(directory, subfolder) if subfolder else directory
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, filename)
    with open(path, "wb") as fh:
        fh.write(body.encode("ascii", errors="replace"))
    return path
