"""Byte-exact tests for x4_po_export — the X4-native Rinax electronic-PO body.

Layout reproduced from PO_Header.Rinax_EFile (B2.decompiled.cs) + RxPad
(A6.decompiled.cs). Field widths are asserted exactly because the file is
fixed-width and consumed positionally by X4 / the vendor.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import x4_po_export as x4


class RxPadTests(unittest.TestCase):
    def test_pad_right_default(self):
        self.assertEqual(x4.rxpad("AB", 5, pad_left=False), "AB   ")

    def test_pad_left(self):
        self.assertEqual(x4.rxpad("7", 4, pad_left=True), "   7")

    def test_truncate_keeps_left_when_not_pad_left(self):
        self.assertEqual(x4.rxpad("ABCDEFG", 4, pad_left=False), "ABCD")

    def test_truncate_keeps_right_when_pad_left(self):
        self.assertEqual(x4.rxpad("1234567", 4, pad_left=True), "4567")

    def test_zero_pad(self):
        self.assertEqual(x4.rxpad("12", 5, pad_left=True, pad_char="0"), "00012")


class RinaxBodyTests(unittest.TestCase):
    def test_header_field_positions(self):
        body = x4.build_rinax_po_body(
            wd_customer_code="ABCDE",
            po_number=1234,
            vendor_code="MOT",
            po_type="standard",
            lines=[],
        )
        header = body.splitlines()[0]
        # "1 " + wd(8,L) + 10sp + po#(8,R) + 2sp + vendor(6,L) + type(2) + 1sp
        self.assertEqual(header[:2], "1 ")
        self.assertEqual(header[2:10], "ABCDE   ")          # wd, left-justified
        self.assertEqual(header[10:20], " " * 10)
        self.assertEqual(header[20:28], "    1234")          # po#, right-justified
        self.assertEqual(header[28:30], "  ")
        self.assertEqual(header[30:36], "MOT   ")            # vendor, left-justified
        self.assertEqual(header[36:38], "S ")                # type code
        self.assertEqual(header[38:39], " ")
        self.assertEqual(len(header), 39)

    def test_detail_line_positions_and_qty_skip(self):
        body = x4.build_rinax_po_body(
            wd_customer_code="WD",
            po_number=7,
            vendor_code="V1",
            lines=[
                {"line_code": "AER-", "item_code": "GH781-4", "qty": 5},
                {"line_code": "ZZ-", "item_code": "SKIP", "qty": 0},   # dropped
            ],
        )
        lines = body.splitlines()
        detail = [l for l in lines if l.startswith("2 ")]
        self.assertEqual(len(detail), 1)                     # qty=0 line skipped
        d = detail[0]
        self.assertEqual(d[:2], "2 ")
        self.assertEqual(d[2:22], "AER-GH781-4         ")    # pg+item, 20, L
        self.assertEqual(d[22:32], "         5")            # qty, 10, R
        self.assertEqual(d[32:39], " " * 7)
        self.assertEqual(len(d), 39)

    def test_terminator(self):
        body = x4.build_rinax_po_body(
            wd_customer_code="WD", po_number=1, vendor_code="V", lines=[],
        )
        self.assertTrue(body.endswith("*END" + " " * 35 + "\n"))

    def test_comment_wrapping(self):
        body = x4.build_rinax_po_body(
            wd_customer_code="WD", po_number=1, vendor_code="V",
            lines=[{"line_code": "A-", "item_code": "1", "qty": 1,
                    "comments": "X" * 40}],
        )
        comment_lines = [l for l in body.splitlines() if l.startswith("3 ")]
        self.assertEqual(len(comment_lines), 2)              # 40 chars -> 37 + 3
        self.assertEqual(comment_lines[0], "3 " + "X" * 37)
        self.assertEqual(comment_lines[1], "3 " + "XXX" + " " * 34)

    def test_qty_integral_has_no_decimal(self):
        body = x4.build_rinax_po_body(
            wd_customer_code="WD", po_number=1, vendor_code="V",
            lines=[{"line_code": "A-", "item_code": "1", "qty": 12.0}],
        )
        d = [l for l in body.splitlines() if l.startswith("2 ")][0]
        self.assertEqual(d[22:32], "        12")

    def test_x12_850_filename(self):
        self.assertEqual(x4.rinax_x12_850_filename("ABCDE", 1234),
                         "RinaxABCDEPO000001234.txt")

    def test_uses_final_qty_when_qty_absent(self):
        body = x4.build_rinax_po_body(
            wd_customer_code="WD", po_number=1, vendor_code="V",
            lines=[{"line_code": "A-", "item_code": "1", "final_qty": 3}],
        )
        self.assertIn("2 ", body)
        d = [l for l in body.splitlines() if l.startswith("2 ")][0]
        self.assertEqual(d[22:32], "         3")


class WriteFileTests(unittest.TestCase):
    def test_write_po_file_lf_preserved(self):
        import tempfile
        body = x4.build_rinax_po_body(
            wd_customer_code="WD", po_number=1, vendor_code="V",
            lines=[{"line_code": "A-", "item_code": "1", "qty": 1}],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = x4.write_po_file(tmp, "test.txt", body)
            self.assertTrue(path.endswith(os.path.join("Sent", "test.txt")))
            with open(path, "rb") as fh:
                raw = fh.read()
            # LF preserved, no CRLF translation
            self.assertNotIn(b"\r\n", raw)
            self.assertTrue(raw.endswith(b"*END" + b" " * 35 + b"\n"))


if __name__ == "__main__":
    unittest.main()
