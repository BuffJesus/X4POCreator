#!/usr/bin/env python3
"""
PO Builder - Purchase Order generation tool for X4 Import from Excel.

Reads Part Sales & Receipts CSVs (and optionally suspended items / open PO listings),
lets the user exclude line codes, assign vendor codes item-by-item, review/edit
quantities, and exports one .xlsx file per vendor in the X4 import format.
"""

import csv
import math
import os
import sys
import threading
import re
import copy
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from collections import defaultdict
from datetime import datetime
import json
import export_flow
import parsers
import storage
from bulk_sheet import BulkSheetView
import ui_assignment_actions
import ui_bulk
import ui_bulk_dialogs
import ui_filters
import ui_help
import ui_individual
import ui_load
import ui_review
import ui_vendor_manager
from maintenance import build_maintenance_report
from models import ItemKey, MaintenanceCandidate, SessionItemState, SourceItemState, SuggestedItemState
from rules import (
    enrich_item,
    evaluate_item_status,
    get_rule_pack_size,
)

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Persistent files stored next to the script
# Path setup — works both as a script and as a PyInstaller .exe
# Bundled assets (loading.gif) go to the PyInstaller temp dir
# User data (whitelist, history) stays next to the executable so it persists
if getattr(sys, "frozen", False):
    # Running as PyInstaller bundle
    _BUNDLE_DIR = sys._MEIPASS           # temp dir with bundled assets
    _DATA_DIR = os.path.dirname(sys.executable)  # folder containing the .exe
else:
    _BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    _DATA_DIR = _BUNDLE_DIR

DUPLICATE_WHITELIST_FILE = os.path.join(_DATA_DIR, "duplicate_whitelist.txt")
ORDER_HISTORY_FILE = os.path.join(_DATA_DIR, "order_history.json")
ORDER_RULES_FILE = os.path.join(_DATA_DIR, "order_rules.json")
SUSPENSE_CARRY_FILE = os.path.join(_DATA_DIR, "suspense_carry.json")
SESSIONS_DIR = os.path.join(_DATA_DIR, "sessions")
VENDOR_CODES_FILE = os.path.join(_DATA_DIR, "vendor_codes.txt")
LOADING_GIF_FILE = os.path.join(_BUNDLE_DIR, "loading.gif")
LOADING_WAV_FILE = os.path.join(_BUNDLE_DIR, "loading.wav")
ICON_FILE = os.path.join(_BUNDLE_DIR, "icon.ico")
OLD_PO_WARNING_DAYS = 90
SHORT_SALES_WINDOW_DAYS = 7
MIN_ANNUAL_SALES_FOR_SUGGESTIONS = 3
MAX_EXCEED_MARGIN = 1.5
MAX_EXCEED_ABS_BUFFER = 5
MAX_LOADING_GIF_FRAMES = 90
BULK_EDITABLE_COLS = ("vendor", "final_qty", "qoh", "cur_min", "cur_max", "pack_size")
REVIEW_EDITABLE_COLS = ("vendor", "order_qty", "pack_size")


# ─── Order Rules (persistent per-item buy rules) ────────────────────────────

def get_rule_key(line_code, item_code):
    """Build a consistent key for the order rules dict."""
    return f"{line_code}:{item_code}"

try:
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
except ImportError:
    print("openpyxl is required. Install with: pip install openpyxl")
    sys.exit(1)


# ─── Known Vendor Codes ─────────────────────────────────────────────────────

KNOWN_VENDORS = [
    "18.80", "ABOVBEYO", "ABV&BEY", "ACKLANDS", "ACKLGRU", "ACKLGRUN",
    "ACT AIR", "ACTIVE", "ADVWARE", "ALBECHAI", "ALL-TEK", "ALLIDIBR",
    "ALLIDICA", "ALLIED", "AMAZON", "AMSOIL", "ANDEFRED", "APPIND", "APPLID",
    "APPLIED", "ARMALL", "ATLATRAI", "ATS ELEC", "B/B", "BAT DIR", "BATDIR",
    "BATT/DIR", "BATTDIRE", "BCBEAR", "BEARTRAN", "BEREFLUI", "BOB DALE",
    "BOBDALE", "BOLTSU", "BOLTSUP", "BOLTSUPP", "BOMAENTE", "BR/FARM",
    "BRICON", "BROOINDU", "BROOKS F",
    # Image 2
    "CA/PUMP", "CAL-SCAN", "CAMPBELL", "CANAPUMP", "CANYON", "CANYRIGG",
    "CASCADE", "CASLAN", "CELDIS", "CHRIPAGE", "COMMERCI", "COMMSOLU",
    "COSTCO", "CROSCANA", "CROSS", "CROSSCA", "CROSSCAN", "CTP",
    "DAYCCANA", "DAYCO", "DEFIOPTI", "DENDOFF", "DERKMANU", "DIX PERF",
    "DOCACORP", "DOLLAR", "DRIVE PR", "DRIVPROD", "DYL", "DYNAINDU",
    "DYNALINE", "EDMONTON", "EDMONUT", "ELEMETDE", "FISHSCIE", "FLUID",
    "FLUISEAL", "FORNEY", "FORNWELD", "FOXSAFE", "FREDANDE",
    # Image 3
    "FTGAINDU", "G2S", "G2SEQUIP", "GARAPAK", "GAZEOILF", "GEARCENT",
    "GHJULIMI", "GLOBAL", "GLOBAUT", "GOODRUBB", "GR/WEST", "GRANENTE",
    "GREDIST", "GREEN", "GREENLI", "GREGDIST", "GREGG", "GREGGS", "GRELIN",
    "GRGGS", "HARWOOD", "HITAKOKI", "HJU", "HOME DEP", "HOME HAR", "HOMEHA",
    "HPAULTUN", "HYDRSTEE", "HYDRX", "IDENT", "IFRWORK", "IND ENG",
    "INDENG", "J-DON", "JASOINDU", "JASON", "JBROS", "JET", "JETEQUI",
    "JOHNBROO", "JONELL",
    # Image 4
    "KDS", "KDSMUR", "KENCOVE", "KINEINCO", "KOYOCANA", "LEEVALL", "LJPETE",
    "MACMINDU", "MAGIAUTO", "MAINFILT", "MBL", "MCCOBROS", "MEDIBATT",
    "MIDFSUPP", "MILLER", "MILSUP", "MISC", "MOTION", "MRC", "NACHCANA",
    "NACHI", "NAPDIS", "NO SPILL", "NORDA-TE", "NORDTECH", "NORFLU",
    "NORTMETT", "NORWINDU", "NOSPILL", "P.S.I", "PADDPLAS", "PANAMA",
    "PAPCO", "PARA", "PARAHYD", "PARAHYDR", "PARAMECH", "PARAMNT", "PARHYDR",
    "PATS", "PATSDRIV",
    # Image 5
    "PECOFACE", "PETROCAN", "PIPETECH", "POWEIGNI", "POWER", "PREMIUM",
    "PREMTOOL", "PROLINE", "PTA", "PTMIND", "PWR IGN", "R&M", "RAYNAUTO",
    "RBW", "RBWIL", "RBWILL", "RE XSTRM", "REDLDIST", "RELIINDU",
    "REMA TIP", "RENOINDU", "ROBETHIB", "ROLG", "SEALWELD", "SHELMACH",
    "SHIPSUPP", "SHURSEAL", "SKEANS", "SOURCE", "SPAENAUR", "SPALHARD",
    "SPARTAN", "STAPEWAY", "STAPLES", "STEERACI", "SUMMIT", "SWAGELOK",
    "SYSTPLUS", "THERTECH", "TITASUPP", "TRANEXPR",
    # Image 6
    "TRANSUPP", "TSL", "UKPROD", "UNI", "UNI/DYL", "UNI/WIX", "UNIFIED",
    "UNISE", "UNISEL", "UNISEL;", "UNISELE", "UNIVALV", "UNSIELE", "WAJIND",
    "WAJIND01", "WAL/COST", "WALLMACH", "WALMART", "WATSGLOV", "WATSON",
    "WCSC", "WESTERN", "WESTGAUG", "WESTINDU", "WESTPART", "WESTWARD", "WIL",
    "WILSAUTO", "WURTCANA", "WURTH",
]


# ─── Excel Export ─────────────────────────────────────────────────────────────

def export_vendor_po(vendor_code, items, output_dir):
    """
    Export a single vendor PO as an .xlsx file in X4 import format.
    Headers: product group, item code, order qty
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "PO Import"

    # Header row styling
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font_white = Font(bold=True, size=11, color="FFFFFF")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    headers = ["product group", "item code", "order quantity"]
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin_border

    # Data rows
    for row_idx, item in enumerate(items, 2):
        pg_cell = ws.cell(row=row_idx, column=1, value=item["line_code"])
        ic_cell = ws.cell(row=row_idx, column=2, value=item["item_code"])
        qty_cell = ws.cell(row=row_idx, column=3, value=item["order_qty"])
        for cell in (pg_cell, ic_cell, qty_cell):
            cell.border = thin_border
        # Force item code as text to preserve leading zeros
        ic_cell.number_format = "@"
        qty_cell.alignment = Alignment(horizontal="center")

    # Column widths
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 20
    ws.column_dimensions["C"].width = 16

    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in vendor_code)
    timestamp = datetime.now().strftime("%Y%m%d")
    filename = f"PO_{safe_name}_{timestamp}.xlsx"
    filepath = os.path.join(output_dir, filename)
    wb.save(filepath)
    return filepath


# ─── GUI Application ─────────────────────────────────────────────────────────

class POBuilderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PO Builder — X4 Import Tool")
        self.root.geometry("1100x720")
        self.root.minsize(900, 600)

        # State
        self.sales_items = []           # parsed part sales data
        self.po_items = []              # parsed open PO data
        self.suspended_items = []       # parsed suspended item details
        self.suspended_set = set()      # (line_code, item_code)
        self.suspended_lookup = {}      # (line_code, item_code) -> list of susp info
        self.open_po_lookup = {}        # (line_code, item_code) -> list of PO info
        self.all_line_codes = set()
        self.excluded_line_codes = set()
        self.all_customers = []         # (code, name, count) from suspended items
        self.excluded_customers = set() # customer codes to exclude
        self.inventory_lookup = {}      # (line_code, item_code) -> {qoh, min, max, ...}
        self.inventory_source_lookup = {}  # immutable X4 baseline copy of inventory_lookup
        self.pack_size_lookup = {}      # (line_code, item_code) -> pack size (int)
        self.pack_size_source_lookup = {}  # immutable X4 baseline copy of pack_size_lookup
        self.pack_size_by_item = {}     # item_code -> pack size (unambiguous fallback)
        self.pack_size_conflicts = set()  # item_codes with conflicting pack sizes
        self.on_po_qty = {}             # (line_code, item_code) -> total qty on PO
        self.qoh_adjustments = {}       # (line_code, item_code) -> {old, new}
        self.duplicate_ic_lookup = {}   # item_code -> set of line_codes (only dupes)
        self.dup_whitelist = storage.load_duplicate_whitelist(DUPLICATE_WHITELIST_FILE)  # persistent whitelist
        self.recent_orders = {}         # (lc, ic) -> [{qty, vendor, date}]
        self.order_rules = storage.load_order_rules(ORDER_RULES_FILE)  # persistent per-item buy rules
        self.suspense_carry = storage.load_suspense_carry(SUSPENSE_CARRY_FILE)
        self.vendor_codes_used = storage.load_vendor_codes(VENDOR_CODES_FILE, KNOWN_VENDORS)
        self.assigned_items = []        # final list of {item data + vendor + order_qty}
        self.last_removed_bulk_items = []  # [(index, item_dict)] for one-step undo
        self.startup_warning_rows = []  # structured rows for startup warning CSV export
        self.bulk_sheet = None
        self.review_grid_editor = None

        # Build the notebook (tabbed interface) — styles set by apply_dark_theme()
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Loading overlay
        self._loading_overlay = None
        self._loading_frames = []
        self._loading_frame_idx = 0
        self._loading_after_id = None
        self._loading_frames_loaded = False

        self._build_tab_load()
        self._build_tab_exclude()
        self._build_tab_customers()
        self._build_tab_bulk_assign()
        self._build_tab_individual_assign()
        self._build_tab_review()
        self._build_tab_help()

        # Disable tabs 2-6 until data is loaded
        for i in (1, 2, 3, 4, 5):
            self.notebook.tab(i, state="disabled")

    # ── Loading Overlay ──────────────────────────────────────────────────

    def _load_gif_frames(self):
        """Load animated GIF frames for the loading overlay."""
        if self._loading_frames_loaded:
            return
        self._loading_frames_loaded = True
        gif_path = LOADING_GIF_FILE
        if not os.path.exists(gif_path):
            return

        # Preferred path: Pillow (supports resizing and smooth animation).
        if HAS_PIL:
            try:
                img = Image.open(gif_path)
                target_size = (200, 200)
                frame_count = max(1, int(getattr(img, "n_frames", 1)))
                step = max(1, math.ceil(frame_count / MAX_LOADING_GIF_FRAMES))
                for i in range(0, frame_count, step):
                    img.seek(i)
                    frame = img.copy().convert("RGBA").resize(target_size, Image.LANCZOS)
                    self._loading_frames.append(ImageTk.PhotoImage(frame))
                if self._loading_frames:
                    return
            except Exception:
                self._loading_frames = []

        # Fallback path: Tk PhotoImage frame extraction (helps in debug env issues).
        try:
            target_w, target_h = 200, 200
            i = 0
            while True:
                if i >= MAX_LOADING_GIF_FRAMES:
                    break
                frame = tk.PhotoImage(file=gif_path, format=f"gif -index {i}")
                fw = max(1, frame.width())
                fh = max(1, frame.height())
                # Resize fallback frames toward the same target size used by PIL path.
                sx = max(1, round(fw / target_w))
                sy = max(1, round(fh / target_h))
                if sx > 1 or sy > 1:
                    frame = frame.subsample(sx, sy)
                self._loading_frames.append(frame)
                i += 1
        except Exception:
            # Stop when no more frames; keep whatever loaded.
            pass

    def _show_loading(self, text="Loading..."):
        """Show the dancing cat loading overlay."""
        if self._loading_overlay is not None:
            return  # already showing
        if not self._loading_frames_loaded:
            self._load_gif_frames()
        self._start_loading_audio()
        if not self._loading_frames:
            # No gif available — just show text
            self._loading_overlay = tk.Frame(self.root, bg="#1e1e2e")
            self._loading_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
            tk.Label(self._loading_overlay, text=text, font=("Segoe UI", 14),
                     fg="#c9a0dc", bg="#1e1e2e").place(relx=0.5, rely=0.5, anchor="center")
            self.root.update()
            return

        self._loading_overlay = tk.Frame(self.root, bg="#1e1e2e")
        self._loading_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._loading_img_label = tk.Label(self._loading_overlay, bg="#1e1e2e")
        self._loading_img_label.place(relx=0.5, rely=0.40, anchor="center")

        self._loading_text_label = tk.Label(
            self._loading_overlay, text=text, font=("Segoe UI", 13, "bold"),
            fg="#c9a0dc", bg="#1e1e2e"
        )
        self._loading_text_label.place(relx=0.5, rely=0.70, anchor="center")

        self._loading_frame_idx = 0
        self._animate_loading()

    def _start_loading_audio(self):
        """Start looping Nyan Cat loading audio if available."""
        if not HAS_WINSOUND:
            return
        if not os.path.exists(LOADING_WAV_FILE):
            return
        try:
            winsound.PlaySound(
                LOADING_WAV_FILE,
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP,
            )
        except Exception:
            pass

    def _stop_loading_audio(self):
        """Stop loading audio playback."""
        if not HAS_WINSOUND:
            return
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass

    def _animate_loading(self):
        """Cycle through gif frames at native speed."""
        if not self._loading_overlay or not self._loading_frames:
            return
        frame = self._loading_frames[self._loading_frame_idx % len(self._loading_frames)]
        self._loading_img_label.configure(image=frame)
        self._loading_frame_idx += 1
        self._loading_after_id = self.root.after(50, self._animate_loading)

    def _autosize_dialog(self, dlg, min_w=420, min_h=280, max_w_ratio=0.9, max_h_ratio=0.9):
        """Size a popup to its content while keeping it inside the screen."""
        dlg.update_idletasks()
        screen_w = dlg.winfo_screenwidth()
        screen_h = dlg.winfo_screenheight()
        max_w = max(min_w, int(screen_w * max_w_ratio))
        max_h = max(min_h, int(screen_h * max_h_ratio))

        req_w = dlg.winfo_reqwidth() + 16
        req_h = dlg.winfo_reqheight() + 16
        width = max(min_w, min(req_w, max_w))
        height = max(min_h, min(req_h, max_h))

        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 3)
        dlg.geometry(f"{width}x{height}+{x}+{y}")
        dlg.minsize(min_w, min_h)

    def _hide_loading(self):
        """Remove the loading overlay."""
        if self._loading_after_id:
            self.root.after_cancel(self._loading_after_id)
            self._loading_after_id = None
        self._stop_loading_audio()
        if self._loading_overlay:
            self._loading_overlay.destroy()
            self._loading_overlay = None

    def _run_with_loading(self, text, func, *args, min_seconds=5):
        """Show loading overlay with animation, run func in a thread, then hide."""
        import time
        self._show_loading(text)
        self.root.update()
        result_holder = {"result": None, "error": None}
        start_time = time.time()

        def _worker():
            try:
                result_holder["result"] = func(*args)
            except Exception as e:
                result_holder["error"] = e

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        # Keep the UI responsive (animation runs) while thread works
        # or until minimum display time is reached
        while thread.is_alive() or (time.time() - start_time) < min_seconds:
            self.root.update()
            self.root.after(16)  # ~60fps

        self._hide_loading()

        if result_holder["error"]:
            raise result_holder["error"]
        return result_holder["result"]

    # ── Tab 1: Load Files ────────────────────────────────────────────────

    def _build_tab_load(self):
        ui_load.build_load_tab(self)

    def _browse_folder(self):
        path = filedialog.askdirectory(title="Select Folder Containing X4 Report CSVs")
        if path:
            self.var_scan_dir.set(path)

    def _scan_folder(self):
        folder = self.var_scan_dir.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showinfo("No Folder", "Please select a valid folder first.")
            return

        found = parsers.scan_directory_for_reports(folder)

        var_map = {
            "sales": self.var_sales_path,
            "minmax": self.var_minmax_path,
            "onhand": self.var_onhand_path,
            "po": self.var_po_path,
            "susp": self.var_susp_path,
            "packsize": self.var_packsize_path,
        }

        report_names = {
            "sales": "Part Sales & Receipts",
            "minmax": "On Hand Min/Max Sales",
            "onhand": "On Hand Report",
            "po": "POs by PG",
            "susp": "Suspended Items",
            "packsize": "Order Multiples",
        }

        populated = []
        for rtype, filepath in found.items():
            if rtype in var_map:
                var_map[rtype].set(filepath)
                populated.append(report_names.get(rtype, rtype))

        if populated:
            self.lbl_scan_status.config(
                text=f"✓  Found {len(populated)} report(s): {', '.join(populated)}"
            )
        else:
            self.lbl_scan_status.config(text="No X4 report CSVs detected in that folder.")

    def _browse(self, which):
        path = filedialog.askopenfilename(
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        if path:
            var_map = {
                "sales": self.var_sales_path,
                "po": self.var_po_path,
                "susp": self.var_susp_path,
                "minmax": self.var_minmax_path,
                "onhand": self.var_onhand_path,
                "packsize": self.var_packsize_path,
            }
            if which in var_map:
                var_map[which].set(path)

    def _do_load(self):
        sales_path = self.var_sales_path.get().strip()
        if not sales_path:
            messagebox.showerror("Missing File", "The Part Sales & Receipts CSV is required.")
            return

        # Gather paths before showing loading screen
        paths = {
            "sales": sales_path,
            "po": self.var_po_path.get().strip(),
            "susp": self.var_susp_path.get().strip(),
            "onhand": self.var_onhand_path.get().strip(),
            "minmax": self.var_minmax_path.get().strip(),
            "packsize": self.var_packsize_path.get().strip(),
        }

        try:
            result = self._run_with_loading("Loading files...", self._parse_all_files, paths)
        except Exception as e:
            messagebox.showerror("Parse Error", f"Failed to parse Part Sales CSV:\n{e}")
            return

        if result is None:
            return

        # Apply parsed results to state
        self.sales_items = result["sales_items"]
        self.all_line_codes = result["all_line_codes"]
        self.po_items = result.get("po_items", [])
        self.open_po_lookup = result.get("open_po_lookup", {})
        self.suspended_items = result.get("suspended_items", [])
        self.suspended_set = result.get("suspended_set", set())
        self.suspended_lookup = result.get("suspended_lookup", {})
        self.inventory_lookup = result.get("inventory_lookup", {})
        self.inventory_source_lookup = copy.deepcopy(self.inventory_lookup)
        self.pack_size_lookup = result.get("pack_size_lookup", {})
        self.pack_size_source_lookup = copy.deepcopy(self.pack_size_lookup)
        self.startup_warning_rows = result.get("startup_warning_rows", [])
        self.pack_size_by_item, self.pack_size_conflicts = parsers.build_pack_size_fallbacks(self.pack_size_lookup)

        if not self.sales_items:
            messagebox.showwarning("No Data", "No items found in the Part Sales CSV. Check the file format.")
            return

        # Show warnings from parsing
        for warning in result.get("warnings", []):
            messagebox.showwarning(warning[0], warning[1])
        if self.pack_size_conflicts:
            sample = ", ".join(sorted(self.pack_size_conflicts)[:12])
            extra = "..." if len(self.pack_size_conflicts) > 12 else ""
            messagebox.showwarning(
                "Pack Fallback Conflict",
                (
                    f"{len(self.pack_size_conflicts)} item code(s) have conflicting order multiples across line codes.\n"
                    "Item-code-level pack fallback was skipped for these items.\n\n"
                    f"Examples: {sample}{extra}"
                ),
            )
            # Add summary row for export.
            self.startup_warning_rows.append({
                "warning_type": "Pack Fallback Conflict",
                "severity": "warning",
                "line_code": "",
                "item_code": "",
                "description": "",
                "reference_date": "",
                "qty": "",
                "po_reference": "",
                "details": (
                    f"{len(self.pack_size_conflicts)} conflicting item code(s). "
                    f"Examples: {sample}{extra}"
                ),
            })

        if hasattr(self, "btn_export_startup_warnings"):
            if self.startup_warning_rows:
                self.btn_export_startup_warnings.config(state="normal")
            else:
                self.btn_export_startup_warnings.config(state="disabled")

        # Prompt immediately after startup warnings so export is not missed.
        if self.startup_warning_rows:
            do_export = messagebox.askyesno(
                "Export Startup Warnings?",
                (
                    f"{len(self.startup_warning_rows)} startup warning row(s) are available.\n\n"
                    "These warnings do not block the run, but they may weaken suggestions or deserve a quick X4 check.\n\n"
                    "Do you want to export the Startup Warnings CSV now?"
                ),
            )
            if do_export:
                self._export_startup_warnings_csv()

        # Status summary
        status_parts = [f"{len(self.sales_items)} items loaded"]
        if self.po_items:
            status_parts.append(f"{len(self.po_items)} open PO lines")
        if self.suspended_set:
            status_parts.append(f"{len(self.suspended_set)} suspended items")
        if self.inventory_lookup:
            status_parts.append(f"{len(self.inventory_lookup)} inventory records")
        if self.pack_size_lookup:
            status_parts.append(f"{len(self.pack_size_lookup)} order multiples")
        if self.pack_size_by_item:
            status_parts.append(f"{len(self.pack_size_by_item)} item-level pack fallbacks")
        status_parts.append(f"{len(self.all_line_codes)} line codes found")
        self.lbl_load_status.config(text="✓  " + "  ·  ".join(status_parts))

        # Populate exclude tab and enable it
        self._populate_exclude_tab()
        self.notebook.tab(1, state="normal")
        self.notebook.select(1)

    def _export_startup_warnings_csv(self):
        """Export startup warning details (old POs and other load-time warnings) to CSV."""
        if not self.startup_warning_rows:
            messagebox.showinfo("No Warnings", "No startup warning details are available to export.")
            return

        default_name = f"Startup_Warnings_{datetime.now().strftime('%Y%m%d')}.csv"
        path = filedialog.asksaveasfilename(
            title="Save Startup Warnings CSV",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
        )
        if not path:
            return

        def _text_code(val):
            """Force Excel to treat codes as text for consistent alignment."""
            txt = str(val).strip() if val is not None else ""
            return f"'{txt}" if txt else ""

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Warning Type",
                    "Severity",
                    "Line Code",
                    "Item Code",
                    "Description",
                    "Reference Date",
                    "Qty",
                    "PO Reference",
                    "Details",
                ])
                for row in self.startup_warning_rows:
                    writer.writerow([
                        row.get("warning_type", ""),
                        row.get("severity", ""),
                        _text_code(row.get("line_code", "")),
                        _text_code(row.get("item_code", "")),
                        row.get("description", ""),
                        row.get("reference_date", ""),
                        row.get("qty", ""),
                        row.get("po_reference", ""),
                        row.get("details", ""),
                    ])
            messagebox.showinfo("Saved", f"Startup warnings exported to:\n{os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export startup warnings CSV:\n{e}")

    @staticmethod
    def _parse_all_files(paths):
        """Parse all CSV files (runs in background thread)."""
        warnings = []
        startup_warning_rows = []
        result = {"warnings": warnings, "startup_warning_rows": startup_warning_rows}

        # Required: Part Sales
        result["sales_items"] = parsers.parse_part_sales_csv(paths["sales"])
        if not result["sales_items"]:
            return result
        desc_lookup = {
            (s.get("line_code", ""), s.get("item_code", "")): s.get("description", "")
            for s in result["sales_items"]
        }
        sales_start, sales_end = parsers.parse_sales_date_range(paths["sales"])
        if sales_start and sales_end:
            span_days = (sales_end.date() - sales_start.date()).days + 1
            if span_days < SHORT_SALES_WINDOW_DAYS:
                warnings.append((
                    "Sales Window Warning",
                    (
                        f"Part Sales date range is only {span_days} day(s): "
                        f"{sales_start.strftime('%Y-%m-%d')} to {sales_end.strftime('%Y-%m-%d')}.\n\n"
                        "This can produce noisy reorder suggestions. You can continue, but a wider sales date range is recommended."
                    ),
                ))
                startup_warning_rows.append({
                    "warning_type": "Sales Window Warning",
                    "severity": "warning",
                    "line_code": "",
                    "item_code": "",
                    "description": "",
                    "reference_date": f"{sales_start.strftime('%Y-%m-%d')} to {sales_end.strftime('%Y-%m-%d')}",
                    "qty": "",
                    "po_reference": "",
                    "details": f"Sales window is {span_days} day(s), below recommended {SHORT_SALES_WINDOW_DAYS}+.",
                })

        all_line_codes = sorted(set(item["line_code"] for item in result["sales_items"]))

        # Optional: PO listing
        if paths["po"]:
            try:
                po_items = parsers.parse_po_listing_csv(paths["po"])
                open_po_lookup = defaultdict(list)
                for po in po_items:
                    open_po_lookup[(po["line_code"], po["item_code"])].append(po)
                for po in po_items:
                    if po["line_code"] not in all_line_codes:
                        all_line_codes.append(po["line_code"])
                all_line_codes = sorted(set(all_line_codes))
                result["po_items"] = po_items
                result["open_po_lookup"] = open_po_lookup

                # Warn on older open POs for manual verification in X4.
                by_key = defaultdict(list)
                for po in po_items:
                    po_dt = parsers.parse_x4_date(po.get("date_issued", ""))
                    if po_dt:
                        by_key[(po["line_code"], po["item_code"])].append(po)
                old_keys = []
                today = datetime.now()
                for key, rows in by_key.items():
                    dated = [(parsers.parse_x4_date(r.get("date_issued", "")), r) for r in rows]
                    dated = [(dt, r) for dt, r in dated if dt is not None]
                    if not dated:
                        continue
                    oldest = min(dt for dt, _ in dated)
                    age_days = (today - oldest).days
                    if age_days >= OLD_PO_WARNING_DAYS:
                        total_qty = sum(float(r.get("qty", 0) or 0) for _, r in dated)
                        old_keys.append((age_days, key, total_qty, [r for _, r in dated]))
                if old_keys:
                    old_keys.sort(reverse=True)
                    sample = "\n".join(
                        f"  {lc}/{ic}: oldest {age} days, qty {qty:g}"
                        for age, (lc, ic), qty, _ in old_keys[:8]
                    )
                    warnings.append((
                        "Old Open PO Warning",
                        (
                            f"{len(old_keys)} item(s) have open PO history older than "
                            f"{OLD_PO_WARNING_DAYS} days.\n"
                            "You can continue, but review these items to confirm receipt or PO closure status in X4 so you do not reorder something already received.\n\n"
                            f"Examples:\n{sample}"
                        ),
                    ))
                    for age, (lc, ic), qty, po_rows in old_keys:
                        refs = []
                        for po in sorted(po_rows, key=lambda x: x.get("date_issued", "")):
                            po_num = po.get("po_number", "")
                            po_type = po.get("po_type", "") or "PO"
                            po_date = po.get("date_issued", "")
                            po_qty = po.get("qty", 0)
                            if po_num:
                                refs.append(f"{po_num}/{po_type} {po_date} qty {po_qty:g}")
                            else:
                                refs.append(f"{po_type} {po_date} qty {po_qty:g}")
                        po_ref = "; ".join(refs[:8])
                        if len(refs) > 8:
                            po_ref += f"; ... +{len(refs) - 8} more"
                        startup_warning_rows.append({
                            "warning_type": "Old Open PO Warning",
                            "severity": "warning",
                            "line_code": lc,
                            "item_code": ic,
                            "description": desc_lookup.get((lc, ic), ""),
                            "reference_date": f"{age} days old",
                            "qty": f"{qty:g}",
                            "po_reference": po_ref,
                            "details": "Open PO age exceeds review threshold; verify receipt/closure in X4.",
                        })
            except Exception as e:
                warnings.append(("PO Parse Warning", f"Could not parse PO listing:\n{e}\nContinuing without it."))

        # Optional: Suspended items
        if paths["susp"]:
            try:
                susp_items, susp_set = parsers.parse_suspended_csv(paths["susp"])
                susp_lookup = defaultdict(list)
                for si in susp_items:
                    susp_lookup[(si["line_code"], si["item_code"])].append(si)
                    key = (si["line_code"], si["item_code"])
                    if not desc_lookup.get(key) and si.get("description"):
                        desc_lookup[key] = si.get("description")
                for si in susp_items:
                    if si["line_code"] not in all_line_codes:
                        all_line_codes.append(si["line_code"])
                all_line_codes = sorted(set(all_line_codes))
                result["suspended_items"] = susp_items
                result["suspended_set"] = susp_set
                result["suspended_lookup"] = susp_lookup
            except Exception as e:
                warnings.append(("Suspended Parse Warning", f"Could not parse suspended items:\n{e}\nContinuing without it."))

        # Optional: Inventory data
        inventory_lookup = {}
        if paths["onhand"]:
            try:
                oh_data = parsers.parse_on_hand_report(paths["onhand"])
                for key, info in oh_data.items():
                    inventory_lookup[key] = {
                        "qoh": info["qoh"], "repl_cost": info["repl_cost"],
                        "min": None, "max": None, "ytd_sales": 0, "mo12_sales": 0,
                        "supplier": "", "last_receipt": "", "last_sale": "",
                    }
            except Exception as e:
                warnings.append(("On Hand Parse Warning", f"Could not parse On Hand Report:\n{e}\nContinuing without it."))

        if paths["minmax"]:
            try:
                mm_data = parsers.parse_on_hand_min_max(paths["minmax"])
                for key, info in mm_data.items():
                    inventory_lookup[key] = info
            except Exception as e:
                warnings.append(("Min/Max Parse Warning", f"Could not parse Min/Max report:\n{e}\nContinuing without it."))

        result["inventory_lookup"] = inventory_lookup

        if inventory_lookup:
            negative_qoh = [
                ((line_code, item_code), info)
                for (line_code, item_code), info in inventory_lookup.items()
                if isinstance(info.get("qoh"), (int, float)) and info.get("qoh", 0) < 0
            ]
            if negative_qoh:
                negative_qoh.sort(key=lambda entry: (entry[0][0], entry[0][1]))
                sample = "\n".join(
                    f"  {line_code}/{item_code}: QOH {info.get('qoh', 0):g}"
                    for (line_code, item_code), info in negative_qoh[:8]
                )
                warnings.append((
                    "Negative QOH Warning",
                    (
                        f"{len(negative_qoh)} item(s) have negative QOH in the inventory source data.\n"
                        "You can continue, but these items should be checked in X4 because suggestions may be distorted until the quantity is corrected.\n\n"
                        f"Examples:\n{sample}"
                    ),
                ))
                for (line_code, item_code), info in negative_qoh:
                    startup_warning_rows.append({
                        "warning_type": "Negative QOH Warning",
                        "severity": "warning",
                        "line_code": line_code,
                        "item_code": item_code,
                        "description": desc_lookup.get((line_code, item_code), ""),
                        "reference_date": "",
                        "qty": f"{info.get('qoh', 0):g}",
                        "po_reference": "",
                        "details": "Inventory source data shows negative QOH; verify the on-hand balance in X4.",
                    })

            missing = [s for s in result["sales_items"] if (s["line_code"], s["item_code"]) not in inventory_lookup]
            if missing:
                missing_qty = sum(s.get("qty_sold", 0) for s in missing)
                sample = ", ".join(f"{s['line_code']}/{s['item_code']}" for s in missing[:12])
                extra = "..." if len(missing) > 12 else ""
                warnings.append((
                    "Inventory Coverage Warning",
                    (
                        f"{len(missing)} sales item(s) were not found in inventory/min-max data "
                        f"(total sold qty {missing_qty}).\n"
                        "Those items can still be reviewed, but their ordering guidance will be weaker until inventory/min-max data is available.\n\n"
                        f"Examples: {sample}{extra}"
                    ),
                ))
                for s in missing:
                    startup_warning_rows.append({
                        "warning_type": "Inventory Coverage Warning",
                        "severity": "warning",
                        "line_code": s.get("line_code", ""),
                        "item_code": s.get("item_code", ""),
                        "description": s.get("description", "") or desc_lookup.get(
                            (s.get("line_code", ""), s.get("item_code", "")), ""
                        ),
                        "reference_date": "",
                        "qty": s.get("qty_sold", 0),
                        "po_reference": "",
                        "details": "Sales item missing from inventory/min-max data.",
                    })

        # Optional: Pack sizes
        if paths["packsize"]:
            try:
                result["pack_size_lookup"] = parsers.parse_pack_sizes_csv(paths["packsize"])
            except Exception as e:
                warnings.append(("Pack Size Parse Warning", f"Could not parse pack sizes:\n{e}\nContinuing without it."))

        result["all_line_codes"] = all_line_codes
        return result

    # ── Tab 2: Exclude Line Codes ────────────────────────────────────────

    def _build_tab_exclude(self):
        ui_filters.build_exclude_tab(self)

    def _populate_exclude_tab(self):
        ui_filters.populate_exclude_tab(self)

    def _toggle_all_lc(self, state):
        for var in self.lc_vars.values():
            var.set(state)
        self._update_lc_count()

    def _update_lc_count(self):
        ui_filters.update_lc_count(self)

    def _do_exclude(self):
        self.excluded_line_codes = {lc for lc, var in self.lc_vars.items() if not var.get()}

        # If there are suspended items, populate and show the customer tab
        if self.suspended_items:
            self._populate_customer_tab()
            self.notebook.tab(2, state="normal")
            self.notebook.select(2)
        else:
            # No suspended items — skip customer filter, go straight to assign
            self._proceed_to_assign()

    def _resolve_pack_size(self, key):
        """Resolve pack size with exact-key and item-code fallback."""
        pack = self.pack_size_lookup.get(key)
        if pack:
            return pack
        generic = self.pack_size_lookup.get(("", key[1]))
        if generic:
            return generic
        return self.pack_size_by_item.get(key[1])

    def _get_x4_pack_size(self, key):
        """Return the original X4 order multiple from the loaded source files."""
        pack = self.pack_size_source_lookup.get(key)
        if pack:
            return pack
        generic = self.pack_size_source_lookup.get(("", key[1]))
        if generic:
            return generic
        return None

    def _default_vendor_for_key(self, key):
        """Use the X4 supplier as the initial vendor when available."""
        inv = self.inventory_lookup.get(key, {})
        supplier = (inv.get("supplier", "") or "").strip().upper()
        return supplier or ""

    def _get_suspense_carry_qty(self, key):
        entry = self.suspense_carry.get(key, {})
        try:
            return max(0, int(float(entry.get("qty", 0))))
        except Exception:
            return 0

    def _persist_suspense_carry(self):
        next_carry = {}
        current_stamp = datetime.now().isoformat()
        for item in self.filtered_items:
            key = (item["line_code"], item["item_code"])
            prior_qty = self._get_suspense_carry_qty(key)
            sales_qty = max(0, int(item.get("qty_sold", 0) or 0))
            current_suspense = max(0, int(item.get("qty_suspended", 0) or 0))
            remaining_prior = max(0, prior_qty - sales_qty)
            newly_covered = 0
            if item.get("vendor"):
                ordered_qty = max(0, int(item.get("final_qty", item.get("order_qty", 0)) or 0))
                newly_covered = min(ordered_qty, max(0, int(item.get("effective_qty_suspended", 0) or 0)))
            next_qty = remaining_prior + newly_covered
            if next_qty > 0:
                next_carry[key] = {"qty": next_qty, "updated_at": current_stamp}
        self.suspense_carry = next_carry
        storage.save_suspense_carry(SUSPENSE_CARRY_FILE, self.suspense_carry)

    def _proceed_to_assign(self):
        """Apply all filters, merge suspended items, and move to bulk vendor assignment."""
        self._show_loading("Crunching numbers...")
        self.root.update()

        # Rebuild suspended lookup excluding filtered-out customers
        self.suspended_lookup = defaultdict(list)
        self.suspended_set = set()
        for si in self.suspended_items:
            if si["line_code"] in self.excluded_line_codes:
                continue
            cust_code = si.get("customer_code", "")
            if cust_code in self.excluded_customers:
                continue
            key = (si["line_code"], si["item_code"])
            self.suspended_lookup[key].append(si)
            self.suspended_set.add(key)

        # Compute suspended qty per (line_code, item_code)
        suspended_qty = defaultdict(int)
        for si in self.suspended_items:
            if si["line_code"] in self.excluded_line_codes:
                continue
            cust_code = si.get("customer_code", "")
            if cust_code in self.excluded_customers:
                continue
            key = (si["line_code"], si["item_code"])
            suspended_qty[key] += si.get("qty_ordered", 0)

        # Build on-PO quantity lookup (needed for order qty calculation)
        self.on_po_qty = defaultdict(float)
        for po in self.po_items:
            key = (po["line_code"], po["item_code"])
            self.on_po_qty[key] += po["qty"]

        # Start with sales items, using inventory position and suspense carry to avoid double counting.
        self.filtered_items = []
        seen_keys = set()
        for item in self.sales_items:
            if item["line_code"] in self.excluded_line_codes:
                continue
            key = (item["line_code"], item["item_code"])
            sq = suspended_qty.get(key, 0)
            carry_qty = self._get_suspense_carry_qty(key)
            effective_sales = max(0, int(item.get("qty_sold", 0)) - carry_qty)
            effective_susp = max(0, sq - carry_qty)
            demand_signal = effective_sales + effective_susp
            inv = self.inventory_lookup.get(key, {})
            inventory_position = (inv.get("qoh", 0) or 0) + self.on_po_qty.get(key, 0)
            current_min = inv.get("min")
            if demand_signal <= 0 and not (
                isinstance(current_min, (int, float)) and inventory_position < current_min
            ):
                continue
            po_qty = self.on_po_qty.get(key, 0)
            self.filtered_items.append({
                **item,
                "qty_suspended": sq,
                "effective_qty_sold": effective_sales,
                "effective_qty_suspended": effective_susp,
                "suspense_carry_qty": carry_qty,
                "demand_signal": demand_signal,
                "qty_on_po": po_qty,
                "gross_need": demand_signal,
                "order_qty": 0,
                "vendor": self._default_vendor_for_key(key),
                "pack_size": self._resolve_pack_size(key),
            })
            seen_keys.add(key)

        # Add suspended-only items not in the sales report
        for key, susp_list in self.suspended_lookup.items():
            if key in seen_keys:
                continue
            if key[0] in self.excluded_line_codes:
                continue
            sq = suspended_qty.get(key, 0)
            if sq <= 0:
                continue
            carry_qty = self._get_suspense_carry_qty(key)
            effective_susp = max(0, sq - carry_qty)
            if effective_susp <= 0:
                continue
            po_qty = self.on_po_qty.get(key, 0)
            first = susp_list[0]
            self.filtered_items.append({
                "line_code": key[0],
                "item_code": key[1],
                "description": first.get("description", ""),
                "qty_sold": 0,
                "effective_qty_sold": 0,
                "qty_received": 0,
                "qty_suspended": sq,
                "effective_qty_suspended": effective_susp,
                "suspense_carry_qty": carry_qty,
                "demand_signal": effective_susp,
                "qty_on_po": po_qty,
                "gross_need": effective_susp,
                "order_qty": 0,
                "vendor": self._default_vendor_for_key(key),
                "pack_size": self._resolve_pack_size(key),
            })

        if not self.filtered_items:
            self._hide_loading()
            messagebox.showwarning(
                "No Items",
                "After applying filters, no items remain to order.",
            )
            return

        # Sort by line code then item code
        self.filtered_items.sort(key=lambda x: (x["line_code"], x["item_code"]))

        # ── Enrich items with ordering logic ──
        for item in self.filtered_items:
            key = (item["line_code"], item["item_code"])
            inv = self.inventory_lookup.get(key, {})
            sug_min, sug_max = self._suggest_min_max(key)
            item["suggested_min"] = sug_min
            item["suggested_max"] = sug_max
            rule_key = get_rule_key(item["line_code"], item["item_code"])
            rule = self.order_rules.get(rule_key)
            rule_pack = get_rule_pack_size(rule)
            if rule_pack is not None:
                item["pack_size"] = rule_pack
            pack_qty = item.get("pack_size")
            enrich_item(item, inv, pack_qty, rule)

        # Build duplicate item code lookup (item_code -> set of line_codes)
        self.duplicate_ic_lookup = defaultdict(set)
        for (lc, ic) in self.inventory_lookup:
            self.duplicate_ic_lookup[ic].add(lc)
        # Only keep entries with 2+ line codes, excluding whitelisted items
        self.duplicate_ic_lookup = {
            ic: lcs for ic, lcs in self.duplicate_ic_lookup.items()
            if len(lcs) > 1 and ic not in self.dup_whitelist
        }

        # Load recent order history
        try:
            days = self.var_lookback_days.get()
        except Exception:
            days = 14
        self.recent_orders = storage.get_recent_orders(ORDER_HISTORY_FILE, days)

        # Reset assignment state
        self.assigned_items = []
        self.qoh_adjustments = {}
        self.vendor_codes_used = storage.load_vendor_codes(VENDOR_CODES_FILE, KNOWN_VENDORS)
        for item in self.filtered_items:
            vendor = item.get("vendor", "").strip().upper()
            if vendor and vendor not in self.vendor_codes_used:
                self.vendor_codes_used.append(vendor)
        self.vendor_codes_used.sort()
        self.last_removed_bulk_items = []
        self._refresh_vendor_inputs()

        # Populate and go to bulk assign
        self._hide_loading()
        self._populate_bulk_tree()
        self.notebook.tab(3, state="normal")
        self.notebook.select(3)

    # ── Tab 3: Customer Exclusion ─────────────────────────────────────────

    def _build_tab_customers(self):
        ui_filters.build_customer_tab(self)

    def _populate_customer_tab(self):
        ui_filters.populate_customer_tab(self)

    def _toggle_all_cust(self, state):
        for var in self.cust_vars.values():
            var.set(state)
        self._update_cust_count()

    def _update_cust_count(self):
        ui_filters.update_cust_count(self)

    def _do_customer_exclude(self):
        self.excluded_customers = {code for code, var in self.cust_vars.items() if not var.get()}
        self._proceed_to_assign()

    # ── Tab 4: Bulk Vendor Assignment ────────────────────────────────────

    def _build_tab_bulk_assign(self):
        ui_bulk.build_bulk_tab(self, BULK_EDITABLE_COLS)

    def _populate_bulk_tree(self):
        ui_bulk.populate_bulk_tree(self)

    def _get_cycle_weeks(self):
        """Return the number of weeks for the selected reorder cycle."""
        cycle = self.var_reorder_cycle.get()
        return {"Weekly": 1, "Biweekly": 2, "Monthly": 4}.get(cycle, 2)

    def _suggest_min_max(self, key):
        """
        Calculate suggested min/max based on 12-month sales and reorder cycle.
        Min = usage during 1 cycle (reorder point)
        Max = usage during 2 cycles (stock-up target)
        Returns (sug_min, sug_max) or (None, None) if history is too sparse.
        """
        inv = self.inventory_lookup.get(key, {})
        mo12 = inv.get("mo12_sales", 0)
        if not mo12 or mo12 <= 0:
            return None, None
        if mo12 < MIN_ANNUAL_SALES_FOR_SUGGESTIONS:
            return None, None
        weekly = mo12 / 52
        weeks = self._get_cycle_weeks()
        sug_min = max(1, math.ceil(weekly * weeks))
        sug_max = max(sug_min + 1, math.ceil(weekly * weeks * 2))
        return sug_min, sug_max

    def _find_filtered_item(self, key):
        """Return the live filtered item matching the given (line_code, item_code)."""
        for item in self.filtered_items:
            if (item["line_code"], item["item_code"]) == key:
                return item
        return None

    @staticmethod
    def _normalize_vendor_code(value):
        return str(value or "").strip().upper()

    def _save_vendor_codes(self):
        storage.save_vendor_codes(VENDOR_CODES_FILE, self.vendor_codes_used)

    def _refresh_vendor_inputs(self):
        if hasattr(self, "combo_bulk_vendor"):
            self.combo_bulk_vendor["values"] = self.vendor_codes_used
        if hasattr(self, "combo_vendor"):
            self.combo_vendor["values"] = self.vendor_codes_used
        if hasattr(self, "combo_vendor_filter"):
            vendors = sorted(set(item["vendor"] for item in self.assigned_items if item.get("vendor")))
            self.combo_vendor_filter["values"] = ["ALL"] + vendors

    def _remember_vendor_code(self, vendor):
        normalized = self._normalize_vendor_code(vendor)
        if not normalized:
            return ""
        if normalized not in self.vendor_codes_used:
            self.vendor_codes_used.append(normalized)
            self.vendor_codes_used.sort()
            self._save_vendor_codes()
            self._refresh_vendor_inputs()
        return normalized

    def _rename_vendor_code(self, old_vendor, new_vendor):
        old_normalized = self._normalize_vendor_code(old_vendor)
        new_normalized = self._normalize_vendor_code(new_vendor)
        if not old_normalized or not new_normalized:
            return ""

        for collection_name in ("filtered_items", "individual_items", "assigned_items"):
            collection = getattr(self, collection_name, [])
            for item in collection:
                if self._normalize_vendor_code(item.get("vendor", "")) == old_normalized:
                    item["vendor"] = new_normalized

        self.vendor_codes_used = [code for code in self.vendor_codes_used if code != old_normalized]
        if new_normalized not in self.vendor_codes_used:
            self.vendor_codes_used.append(new_normalized)
        self.vendor_codes_used.sort()
        self._save_vendor_codes()
        self._refresh_vendor_inputs()
        self._update_bulk_summary()
        self._update_review_summary()
        return new_normalized

    def _remove_vendor_code(self, vendor):
        normalized = self._normalize_vendor_code(vendor)
        if not normalized:
            return
        self.vendor_codes_used = [code for code in self.vendor_codes_used if code != normalized]
        self._save_vendor_codes()
        self._refresh_vendor_inputs()

    def _open_vendor_manager(self):
        ui_vendor_manager.open_vendor_manager(self)

    def _get_effective_order_qty(self, item):
        """Return the current working quantity regardless of storage field."""
        return item.get("final_qty", item.get("order_qty", 0))

    def _set_effective_order_qty(self, item, qty, *, manual_override=False):
        """Keep quantity fields aligned while optionally marking a user override."""
        qty = max(0, int(qty))
        item["final_qty"] = qty
        item["order_qty"] = qty
        if manual_override:
            item["manual_override"] = True

    def _recalculate_item(self, item):
        """Refresh derived ordering fields for a single item after edits."""
        key = (item["line_code"], item["item_code"])
        rule_key = get_rule_key(item["line_code"], item["item_code"])
        rule = self.order_rules.get(rule_key)
        sug_min, sug_max = self._suggest_min_max(key)
        item["suggested_min"] = sug_min
        item["suggested_max"] = sug_max
        enrich_item(item, self.inventory_lookup.get(key, {}), item.get("pack_size"), rule)
        return item

    def _sync_review_item_to_filtered(self, item):
        """Mirror review edits back to the filtered item so both views stay consistent."""
        key = (item["line_code"], item["item_code"])
        filtered = self._find_filtered_item(key)
        if filtered is None:
            return None
        filtered["vendor"] = item.get("vendor", filtered.get("vendor", ""))
        filtered["pack_size"] = item.get("pack_size")
        self._set_effective_order_qty(
            filtered,
            item.get("order_qty", self._get_effective_order_qty(filtered)),
            manual_override=True,
        )
        self._recalculate_item(filtered)
        item["status"] = filtered.get("status", item.get("status", "ok"))
        item["why"] = filtered.get("why", item.get("why", ""))
        item["data_flags"] = list(filtered.get("data_flags", item.get("data_flags", [])))
        item["order_policy"] = filtered.get("order_policy", item.get("order_policy", ""))
        item["suggested_min"] = filtered.get("suggested_min")
        item["suggested_max"] = filtered.get("suggested_max")
        item["suggested_qty"] = filtered.get("suggested_qty")
        item["raw_need"] = filtered.get("raw_need")
        item["final_qty"] = self._get_effective_order_qty(filtered)
        return filtered

    def _bulk_row_values(self, item):
        return ui_bulk.bulk_row_values(self, item)

    def _refresh_suggestions(self):
        """Recalculate suggestions when the reorder cycle changes."""
        self._apply_bulk_filter()

    def _refresh_recent_orders(self):
        """Reload recent orders when lookback days changes."""
        try:
            days = self.var_lookback_days.get()
        except Exception:
            days = 14
        self.recent_orders = storage.get_recent_orders(ORDER_HISTORY_FILE, days)
        self._apply_bulk_filter()

    def _update_bulk_summary(self):
        ui_bulk.update_bulk_summary(self)

    def _apply_bulk_filter(self):
        ui_bulk.apply_bulk_filter(self)

    def _sort_bulk_tree(self, col):
        ui_bulk.sort_bulk_tree(self, col)

    def _bulk_vendor_autocomplete(self, event):
        ui_assignment_actions.bulk_vendor_autocomplete(self, event)

    def _bulk_apply_selected(self):
        ui_assignment_actions.bulk_apply_selected(self)

    def _bulk_apply_visible(self):
        ui_assignment_actions.bulk_apply_visible(self)

    def _not_needed_reason(self, item):
        return ui_bulk_dialogs.not_needed_reason(self, item, MAX_EXCEED_ABS_BUFFER)

    def _bulk_remove_not_needed_visible(self):
        self._bulk_remove_not_needed(scope="screen")

    def _bulk_remove_not_needed_filtered(self):
        """Review and remove currently filtered rows that appear unnecessary to order."""
        self._bulk_remove_not_needed(scope="filtered")

    def _bulk_remove_not_needed(self, scope="screen"):
        ui_bulk_dialogs.bulk_remove_not_needed(self, scope, MAX_EXCEED_ABS_BUFFER)

    def _undo_last_bulk_removal(self):
        ui_assignment_actions.undo_last_bulk_removal(self)

    def _update_bulk_cell_status(self):
        if not hasattr(self, "lbl_bulk_cell_status"):
            return
        bulk_sheet = getattr(self, "bulk_sheet", None)
        sheet_selected_cells = bulk_sheet.selected_cells() if bulk_sheet else []
        active_col = (
            bulk_sheet.selected_editable_column_name() if bulk_sheet else ""
        ) or (bulk_sheet.current_column_name() if bulk_sheet else "")
        if active_col:
            label_map = {
                "vendor": "Vendor",
                "final_qty": "Order Qty",
                "qoh": "QOH",
                "cur_min": "Min",
                "cur_max": "Max",
                "pack_size": "Pack",
            }
            col_label = label_map.get(active_col, active_col)
            count = len(sheet_selected_cells)
            if count:
                self.lbl_bulk_cell_status.config(text=f"Active edit column: {col_label} | Selected cells: {count}")
                return
            selected_rows = len(self.bulk_sheet.selected_row_ids()) if getattr(self, "bulk_sheet", None) else (
                len(self.bulk_tree.selection()) if hasattr(self, "bulk_tree") else 0
            )
            self.lbl_bulk_cell_status.config(text=f"Active edit column: {col_label} | Selected rows: {selected_rows}")
        else:
            selected_rows = len(self.bulk_sheet.selected_row_ids()) if getattr(self, "bulk_sheet", None) else (
                len(self.bulk_tree.selection()) if hasattr(self, "bulk_tree") else 0
            )
            self.lbl_bulk_cell_status.config(text=f"Active edit column: none | Selected rows: {selected_rows}")

    def _update_bulk_sheet_status(self):
        self._update_bulk_cell_status()

    def _bulk_copy_selection(self, event=None):
        if self.bulk_sheet and self.bulk_sheet.copy_selection_to_clipboard():
            return "break"
        return None

    def _bulk_paste_selection(self, event=None):
        if self.bulk_sheet and self.bulk_sheet.paste_from_clipboard():
            return "break"
        return None

    def _bulk_select_current_row(self, event=None):
        if self.bulk_sheet and self.bulk_sheet.select_current_row():
            return "break"
        return None

    def _bulk_select_current_column(self, event=None):
        if self.bulk_sheet and self.bulk_sheet.select_current_column():
            return "break"
        return None

    def _bulk_begin_edit(self, event=None):
        if not self.bulk_sheet:
            return None
        col_name = (
            self.bulk_sheet.selected_editable_column_name()
            or self.bulk_sheet.current_editable_column_name()
        )
        row_ids = list(self.bulk_sheet.selected_target_row_ids(col_name)) if col_name else []
        if col_name in BULK_EDITABLE_COLS and len(row_ids) > 1:
            prompt = f"Enter a value for {col_name} across {len(row_ids)} selected row(s):"
            initial = self.bulk_sheet.current_cell_value()
            value = simpledialog.askstring("Bulk Edit Selection", prompt, parent=self.root, initialvalue=initial)
            if value is None:
                return "break"
            for row_id in row_ids:
                self._bulk_apply_editor_value(row_id, col_name, value.strip())
            self._apply_bulk_filter()
            self._update_bulk_summary()
            self._update_bulk_cell_status()
            return "break"
        self.bulk_sheet.sheet.open_cell()
        return "break"

    def _bulk_fit_columns(self):
        if self.bulk_sheet:
            self.bulk_sheet.fit_columns_to_window()

    def _bulk_remove_selected_rows(self, event=None):
        selected = []
        if self.bulk_sheet:
            selected = list(self.bulk_sheet.explicit_selected_row_ids())
            if not selected:
                current_row_id = self.bulk_sheet.current_row_id()
                if current_row_id is not None:
                    selected = [current_row_id]
        else:
            selected = list(self.bulk_tree.selection())
        if not selected:
            return "break" if event is not None else None
        if not messagebox.askyesno("Confirm Remove", f"Remove {len(selected)} item(s) from this session?"):
            return "break" if event is not None else None
        removed_payload = []
        for idx in sorted((int(row_id) for row_id in selected), reverse=True):
            if 0 <= idx < len(self.filtered_items):
                removed_payload.append((idx, copy.deepcopy(self.filtered_items[idx])))
                self.filtered_items.pop(idx)
        self.last_removed_bulk_items = removed_payload
        if self.bulk_sheet:
            self.bulk_sheet.clear_selection()
        self._apply_bulk_filter()
        self._update_bulk_summary()
        return "break" if event is not None else None

    def _bulk_fill_selected_cells(self):
        col_name = (
            (self.bulk_sheet.selected_editable_column_name() if self.bulk_sheet else "")
            or (self.bulk_sheet.current_editable_column_name() if self.bulk_sheet else "")
        )
        if self.bulk_sheet:
            row_ids = list(self.bulk_sheet.selected_target_row_ids(col_name))
        else:
            row_ids = list(self.bulk_tree.selection())
        if col_name not in BULK_EDITABLE_COLS or not row_ids:
            messagebox.showinfo("No Cell Selection", "Select one or more rows or cells in a single editable column first.")
            return
        value = simpledialog.askstring("Fill Selected Cells", f"Enter a value for {col_name}:", parent=self.root)
        if value is None:
            return
        if self.bulk_sheet:
            for row_id in row_ids:
                self._bulk_apply_editor_value(row_id, col_name, value.strip())
            self._apply_bulk_filter()
        else:
            for row_id in row_ids:
                self._bulk_apply_editor_value(row_id, col_name, value.strip())
            self._apply_bulk_filter()
        self._update_bulk_summary()
        self._update_bulk_cell_status()

    def _bulk_clear_selected_cells(self):
        col_name = (
            (self.bulk_sheet.selected_editable_column_name() if self.bulk_sheet else "")
            or (self.bulk_sheet.current_editable_column_name() if self.bulk_sheet else "")
        )
        if self.bulk_sheet:
            row_ids = list(self.bulk_sheet.selected_target_row_ids(col_name))
        else:
            row_ids = list(self.bulk_tree.selection())
        if col_name not in BULK_EDITABLE_COLS or not row_ids:
            messagebox.showinfo("No Cell Selection", "Select one or more rows or cells in a single editable column first.")
            return
        if self.bulk_sheet:
            for row_id in row_ids:
                self._bulk_apply_editor_value(row_id, col_name, "")
            self._apply_bulk_filter()
        else:
            for row_id in row_ids:
                self._bulk_apply_editor_value(row_id, col_name, "")
            self._apply_bulk_filter()
        self._update_bulk_summary()
        self._update_bulk_cell_status()

    def _bulk_delete_selected(self, event=None):
        if self.bulk_sheet and self.bulk_sheet.explicit_selected_row_ids():
            return self._bulk_remove_selected_rows(event)
        elif self.bulk_sheet and self.bulk_sheet.selected_cells():
            self._bulk_clear_selected_cells()
            return "break"
        else:
            return self._bulk_remove_selected_rows(event)

    def _bulk_apply_editor_value(self, row_id, col_name, raw):
        idx = int(row_id)
        if col_name == "buy_rule":
            self._open_buy_rule_editor(idx)
            return
        if col_name not in BULK_EDITABLE_COLS:
            return
        item = self.filtered_items[idx]
        key = (item["line_code"], item["item_code"])
        inv = self.inventory_lookup.get(key, {})
        rule_key = get_rule_key(item["line_code"], item["item_code"])
        rule = self.order_rules.get(rule_key)
        if col_name == "vendor":
            new_val = raw.upper()
            if new_val:
                item["vendor"] = new_val
                self._remember_vendor_code(new_val)
                self._update_bulk_summary()
        elif col_name == "final_qty":
            try:
                qty = int(float(raw))
                self._set_effective_order_qty(item, qty, manual_override=True)
                self._recalculate_item(item)
            except ValueError:
                pass
        elif col_name == "qoh":
            try:
                new_qoh = float(raw)
                old_qoh = inv.get("qoh", 0)
                if new_qoh != old_qoh:
                    self.qoh_adjustments[key] = {"old": old_qoh, "new": new_qoh}
                    if key in self.inventory_lookup:
                        self.inventory_lookup[key]["qoh"] = new_qoh
                    self._recalculate_item(item)
            except ValueError:
                pass
        elif col_name in ("cur_min", "cur_max"):
            if key not in self.inventory_lookup:
                self.inventory_lookup[key] = {
                    "qoh": 0, "repl_cost": 0, "min": None, "max": None,
                    "ytd_sales": 0, "mo12_sales": 0, "supplier": "",
                    "last_receipt": "", "last_sale": "",
                }
            try:
                parsed = None if raw == "" else int(float(raw))
                if col_name == "cur_min":
                    self.inventory_lookup[key]["min"] = parsed
                else:
                    self.inventory_lookup[key]["max"] = parsed
                self._recalculate_item(item)
            except ValueError:
                pass
        elif col_name == "pack_size":
            try:
                item["pack_size"] = None if raw == "" else int(float(raw))
                rule = dict(rule or {})
                if item["pack_size"] is None:
                    rule.pop("pack_size", None)
                else:
                    rule["pack_size"] = item["pack_size"]
                self.order_rules[rule_key] = rule
                storage.save_order_rules(ORDER_RULES_FILE, self.order_rules)
                self._recalculate_item(item)
            except ValueError:
                pass

    def _open_buy_rule_editor(self, idx):
        ui_bulk_dialogs.open_buy_rule_editor(self, idx, ORDER_RULES_FILE)

    def _view_item_details(self):
        ui_bulk_dialogs.view_item_details(self)

    def _edit_buy_rule_from_bulk(self):
        ui_bulk_dialogs.edit_buy_rule_from_bulk(self)

    def _resolve_review_from_bulk(self):
        ui_bulk_dialogs.resolve_review_from_bulk(self)

    def _dismiss_duplicate_from_bulk(self):
        ui_bulk_dialogs.dismiss_duplicate_from_bulk(self)

    def _dismiss_duplicate(self, item_code):
        """Add an item code to the persistent duplicate whitelist."""
        self.dup_whitelist.add(item_code)
        storage.save_duplicate_whitelist(DUPLICATE_WHITELIST_FILE, self.dup_whitelist)
        # Remove from the active lookup
        self.duplicate_ic_lookup.pop(item_code, None)
        # Refresh the tree to clear the Also Under column
        self._apply_bulk_filter()

    def _go_to_individual(self):
        ui_assignment_actions.go_to_individual(self)

    def _finish_bulk(self):
        """Check stock warnings, then collect assigned items and go to review."""
        if not self._check_stock_warnings():
            return
        self._finish_bulk_final()

    def _check_stock_warnings(self):
        return ui_bulk_dialogs.check_stock_warnings(self)

    def _finish_bulk_final(self):
        ui_bulk_dialogs.finish_bulk_final(self)

    # Tab 5: Individual Vendor Assignment
    # ── Tab 5: Individual Vendor Assignment ───────────────────────────────

    def _build_tab_individual_assign(self):
        ui_individual.build_individual_tab(self)

    def _vendor_autocomplete(self, event):
        ui_assignment_actions.vendor_autocomplete(self, event)

    def _populate_assign_item(self):
        ui_individual.populate_assign_item(self)

    def _dismiss_dup_from_individual(self):
        ui_assignment_actions.dismiss_dup_from_individual(self)

    def _assign_current(self):
        ui_assignment_actions.assign_current(self)

    def _assign_skip(self):
        ui_assignment_actions.assign_skip(self)

    def _assign_back(self):
        ui_assignment_actions.assign_back(self)

    def _finish_assign(self):
        ui_assignment_actions.finish_assign(self)

    # ── Tab 6: Review & Export ───────────────────────────────────────────

    def _build_tab_review(self):
        ui_review.build_review_tab(self)

    def _build_tab_help(self):
        ui_help.build_help_tab(self)

    def _populate_review_tab(self):
        ui_review.populate_review_tab(self)

    def _review_row_values(self, item):
        return ui_review.review_row_values(item)

    def _update_review_summary(self):
        ui_review.update_review_summary(self)

    def _apply_review_filter(self):
        ui_review.apply_review_filter(self)

    def _sort_tree(self, col):
        ui_review.sort_tree(self, col)

    def _review_editor_widget(self, col_name):
        if col_name == "vendor":
            return ttk.Combobox(self.tree, values=self.vendor_codes_used, font=("Segoe UI", 10))
        return ttk.Entry(self.tree, font=("Segoe UI", 10))

    def _review_editor_value(self, row_id, col_name):
        return self.tree.set(row_id, col_name)

    def _review_refresh_editor_row(self, row_id):
        idx = int(row_id)
        self.tree.item(row_id, values=self._review_row_values(self.assigned_items[idx]))

    def _review_apply_editor_value(self, row_id, col_name, raw):
        idx = int(row_id)
        item = self.assigned_items[idx]
        if col_name == "order_qty":
            try:
                self._set_effective_order_qty(item, int(float(raw)), manual_override=True)
                self._sync_review_item_to_filtered(item)
            except ValueError:
                pass
        elif col_name == "vendor":
            new_val = raw.upper()
            if new_val:
                item["vendor"] = new_val
                self._remember_vendor_code(new_val)
                self._sync_review_item_to_filtered(item)
                self._update_review_summary()
        elif col_name == "pack_size":
            try:
                item["pack_size"] = None if raw == "" else int(float(raw))
                self._sync_review_item_to_filtered(item)
            except ValueError:
                pass

    def _on_review_tree_click(self, event):
        """Remember the clicked editable review column for keyboard editing."""
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        col = self.tree.identify_column(event.x)
        if not col:
            return
        col_names = ("vendor", "line_code", "item_code", "description", "order_qty", "status", "why", "pack_size")
        col_idx = int(col.replace("#", "")) - 1
        if 0 <= col_idx < len(col_names):
            self.review_grid_editor.remember_col(col_names[col_idx])

    def _on_review_tree_keyboard_edit(self, event=None):
        """Open the review-tree editor from the keyboard."""
        return self.review_grid_editor.keyboard_edit()

    def _on_review_tree_horizontal_nav(self, event):
        """Change the active editable review column with arrow keys."""
        return self.review_grid_editor.horizontal_nav(event.keysym)

    def _on_tree_double_click(self, event):
        """Edit order_qty or vendor on double-click."""
        region = self.tree.identify("region", event.x, event.y)
        if region == "separator":
            self._autosize_review_column_from_x(event.x)
            return "break"
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return

        col_idx = int(col.replace("#", "")) - 1
        col_names = ("vendor", "line_code", "item_code", "description", "order_qty", "status", "why", "pack_size")
        if col_idx >= len(col_names):
            return
        col_name = col_names[col_idx]

        self.review_grid_editor.open_editor(row_id, col_name)

    def _autosize_review_column_from_x(self, x):
        col = self.tree.identify_column(x)
        if not col:
            return
        col_idx = int(col.replace("#", "")) - 1
        columns = getattr(self, "review_tree_columns", ())
        labels = getattr(self, "review_tree_labels", {})
        if 0 <= col_idx < len(columns):
            col_name = columns[col_idx]
            max_width = 560 if col_name in ("description", "why") else 220
            self.review_grid_editor.autosize_column(col_name, labels.get(col_name, col_name), max_width=max_width)

    def _delete_selected(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return
        if not messagebox.askyesno("Confirm Delete", f"Remove {len(selected)} item(s) from the PO?"):
            return
        # Remove from assigned_items (highest index first to avoid shifting)
        indices = sorted([int(s) for s in selected], reverse=True)
        for idx in indices:
            if idx < len(self.assigned_items):
                self.assigned_items.pop(idx)
        self._populate_review_tab()

    def _back_to_assign(self):
        self.notebook.select(3)

    def _do_export(self):
        export_flow.do_export(self, export_vendor_po, ORDER_HISTORY_FILE, SESSIONS_DIR)

    def _build_maintenance_report(self):
        """
        Build a list of X4 data maintenance items from source/session/suggested state.
        """
        seen_keys = set()
        items_by_key = {}
        for item in self.filtered_items:
            items_by_key[(item["line_code"], item["item_code"])] = dict(item)
        for item in self.assigned_items:
            key = (item["line_code"], item["item_code"])
            merged = dict(items_by_key.get(key, {}))
            merged.update(item)
            items_by_key[key] = merged
        items = list(items_by_key.values()) if items_by_key else list(self.assigned_items)
        candidates = []

        for item in items:
            key = (item["line_code"], item["item_code"])
            seen_keys.add(key)
            x4_inv = self.inventory_source_lookup.get(key, {})
            live_inv = self.inventory_lookup.get(key, {})
            other_lcs = self.duplicate_ic_lookup.get(item["item_code"], set())
            others = tuple(sorted(lc for lc in other_lcs if lc != item["line_code"]))
            sug_min, sug_max = self._suggest_min_max(key)
            qoh_adj = self.qoh_adjustments.get(key)
            candidates.append(
                MaintenanceCandidate(
                    key=ItemKey(item["line_code"], item["item_code"]),
                    source=SourceItemState(
                        supplier=x4_inv.get("supplier", ""),
                        order_multiple=self._get_x4_pack_size(key),
                        min_qty=x4_inv.get("min"),
                        max_qty=x4_inv.get("max"),
                    ),
                    session=SessionItemState(
                        description=item.get("description", ""),
                        vendor=item.get("vendor", ""),
                        pack_size=item.get("pack_size"),
                        target_min=live_inv.get("min"),
                        target_max=live_inv.get("max"),
                        qoh_old=qoh_adj["old"] if qoh_adj else None,
                        qoh_new=qoh_adj["new"] if qoh_adj else None,
                        data_flags=tuple(item.get("data_flags", [])),
                        order_policy=item.get("order_policy", ""),
                        duplicate_line_codes=others,
                    ),
                    suggested=SuggestedItemState(
                        min_qty=sug_min,
                        max_qty=sug_max,
                    ),
                )
            )

        for key, adj in self.qoh_adjustments.items():
            if key in seen_keys:
                continue
            x4_inv = self.inventory_source_lookup.get(key, {})
            live_inv = self.inventory_lookup.get(key, {})
            candidates.append(
                MaintenanceCandidate(
                    key=ItemKey(key[0], key[1]),
                    source=SourceItemState(
                        supplier=x4_inv.get("supplier", ""),
                        order_multiple=self._get_x4_pack_size(key),
                        min_qty=x4_inv.get("min"),
                        max_qty=x4_inv.get("max"),
                    ),
                    session=SessionItemState(
                        description="",
                        target_min=live_inv.get("min"),
                        target_max=live_inv.get("max"),
                        qoh_old=adj["old"],
                        qoh_new=adj["new"],
                    ),
                    suggested=SuggestedItemState(),
                )
            )

        return build_maintenance_report(candidates)

    def _build_session_snapshot(self, output_dir, created_files, maintenance_issues):
        return export_flow.build_session_snapshot(self, output_dir, created_files, maintenance_issues)

    def _export_maintenance_csv(self, issues, output_dir):
        return export_flow.export_maintenance_csv(issues, output_dir)

    def _show_maintenance_report(self, output_dir, issues=None):
        if issues is None:
            issues = self._build_maintenance_report()
        ui_review.show_maintenance_report(self, output_dir, issues)


# ─── Entry Point ─────────────────────────────────────────────────────────────

def apply_dark_theme(root):
    """Apply a dark mode theme with purple accents."""
    # Color palette
    BG = "#1e1e2e"           # main background
    BG_LIGHT = "#2a2a3d"     # slightly lighter panels
    BG_WIDGET = "#333348"    # entry/combo backgrounds
    FG = "#e0e0e8"           # main text
    FG_DIM = "#9090a8"       # secondary text
    PURPLE = "#b48ead"       # primary accent
    PURPLE_BRIGHT = "#c9a0dc" # hover / highlight
    PURPLE_DARK = "#7c5e8a"  # pressed / selection
    BORDER = "#444460"       # subtle borders
    RED = "#f07070"          # warnings
    TREE_BG = "#252538"      # treeview background
    TREE_ALT = "#2c2c42"     # alternate row
    TREE_SEL = "#5b4670"     # selected row

    root.configure(bg=BG)
    root.option_add("*TCombobox*Listbox.background", BG_WIDGET)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", PURPLE_DARK)
    root.option_add("*TCombobox*Listbox.selectForeground", FG)

    style = ttk.Style()
    style.theme_use("clam")

    # ── Global defaults ──
    style.configure(".", background=BG, foreground=FG, fieldbackground=BG_WIDGET,
                     bordercolor=BORDER, troughcolor=BG_LIGHT, font=("Segoe UI", 10),
                     insertcolor=FG, selectbackground=PURPLE_DARK, selectforeground=FG)

    # ── Frames & Labels ──
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("TLabelframe", background=BG, foreground=PURPLE, bordercolor=BORDER)
    style.configure("TLabelframe.Label", background=BG, foreground=PURPLE, font=("Segoe UI", 10, "bold"))

    # ── Notebook ──
    style.configure("TNotebook", background=BG, bordercolor=BORDER)
    style.configure("TNotebook.Tab", background=BG_LIGHT, foreground=FG_DIM,
                     padding=[14, 7], font=("Segoe UI", 10))
    style.map("TNotebook.Tab",
              background=[("selected", BG), ("active", BG_WIDGET)],
              foreground=[("selected", PURPLE_BRIGHT), ("active", FG)])

    # ── Buttons ──
    style.configure("TButton", background=BG_WIDGET, foreground=FG,
                     bordercolor=BORDER, padding=[10, 5], font=("Segoe UI", 10))
    style.map("TButton",
              background=[("active", PURPLE_DARK), ("pressed", PURPLE)],
              foreground=[("active", FG), ("pressed", FG)])

    style.configure("Big.TButton", background=PURPLE_DARK, foreground=FG,
                     font=("Segoe UI", 10, "bold"), padding=[16, 7], bordercolor=PURPLE)
    style.map("Big.TButton",
              background=[("active", PURPLE), ("pressed", PURPLE_BRIGHT)])

    # ── Entries & Combos ──
    style.configure("TEntry", fieldbackground=BG_WIDGET, foreground=FG,
                     insertcolor=FG, bordercolor=BORDER)
    style.map("TEntry", fieldbackground=[("focus", "#3a3a52")])

    style.configure("TCombobox", fieldbackground=BG_WIDGET, foreground=FG,
                     background=BG_WIDGET, arrowcolor=PURPLE, bordercolor=BORDER)
    style.map("TCombobox", fieldbackground=[("focus", "#3a3a52")],
              background=[("active", BG_LIGHT)])

    # ── Checkbuttons ──
    style.configure("TCheckbutton", background=BG, foreground=FG, indicatorcolor=BG_WIDGET)
    style.map("TCheckbutton",
              background=[("active", BG_LIGHT)],
              indicatorcolor=[("selected", PURPLE), ("active", PURPLE_DARK)])

    # ── Progressbar ──
    style.configure("TProgressbar", background=PURPLE, troughcolor=BG_LIGHT, bordercolor=BORDER)

    # ── Scrollbar ──
    style.configure("TScrollbar", background=BG_LIGHT, troughcolor=BG,
                     bordercolor=BORDER, arrowcolor=PURPLE)
    style.map("TScrollbar", background=[("active", PURPLE_DARK)])

    # ── Treeview ──
    style.configure("Treeview", background=TREE_BG, foreground=FG,
                     fieldbackground=TREE_BG, bordercolor=BORDER, font=("Segoe UI", 9))
    style.configure("Treeview.Heading", background=BG_WIDGET, foreground=PURPLE_BRIGHT,
                     bordercolor=BORDER, font=("Segoe UI", 9, "bold"))
    style.map("Treeview",
              background=[("selected", TREE_SEL)],
              foreground=[("selected", FG)])
    style.map("Treeview.Heading",
              background=[("active", PURPLE_DARK)])

    # ── Custom label styles ──
    style.configure("Header.TLabel", font=("Segoe UI", 13, "bold"), foreground=PURPLE_BRIGHT, background=BG)
    style.configure("SubHeader.TLabel", font=("Segoe UI", 10), foreground=FG_DIM, background=BG)
    style.configure("Info.TLabel", font=("Segoe UI", 9), foreground=FG_DIM, background=BG)
    style.configure("Warning.TLabel", font=("Segoe UI", 9, "bold"), foreground=RED, background=BG)
    style.configure("Path.TLabel", font=("Segoe UI", 8, "italic"), foreground="#7a7a95", background=BG)

    return style


def main():
    root = tk.Tk()
    apply_dark_theme(root)

    # Set custom window icon if available
    if os.path.exists(ICON_FILE):
        try:
            root.iconbitmap(ICON_FILE)
        except Exception:
            pass

    app = POBuilderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
