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
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from collections import defaultdict
from datetime import datetime
import json
import webbrowser
import export_flow
import item_workflow
import load_flow
import parsers
import storage
from debug_log import DEBUG_LOG_FILE, write_debug
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
from models import AppSessionState, ItemKey, MaintenanceCandidate, SessionItemState, SourceItemState, SuggestedItemState
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

LOCAL_DATA_DIR = _DATA_DIR
APP_SETTINGS_FILE = os.path.join(_DATA_DIR, "po_builder_settings.json")
VERSION_FILE = os.path.join(_DATA_DIR, "VERSION")
DUPLICATE_WHITELIST_FILE = os.path.join(LOCAL_DATA_DIR, "duplicate_whitelist.txt")
ORDER_HISTORY_FILE = os.path.join(LOCAL_DATA_DIR, "order_history.json")
ORDER_RULES_FILE = os.path.join(LOCAL_DATA_DIR, "order_rules.json")
SUSPENSE_CARRY_FILE = os.path.join(LOCAL_DATA_DIR, "suspense_carry.json")
SESSIONS_DIR = os.path.join(LOCAL_DATA_DIR, "sessions")
VENDOR_CODES_FILE = os.path.join(LOCAL_DATA_DIR, "vendor_codes.txt")
GITHUB_REPO = "BuffJesus/X4POCreator"
GITHUB_RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_PAGE_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"
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
BULK_SHORTCUTS_TEXT = """Current bulk-sheet shortcuts

Supported now
- Ctrl+C: copy selected cells or rows
- Ctrl+V: paste into the active editable area
- Ctrl+A: select all visible rows
- Ctrl+Z: undo the last bulk edit or row removal
- Ctrl+Y: redo the last undone bulk edit or row removal
- Ctrl+D: fill down using the current cell value
- Ctrl+R: same as Ctrl+D for the current one-column bulk edit model
- Ctrl+Enter: apply the current cell value across the selected rows in the active editable column
- Delete / Backspace: clear selected cells, or remove selected rows
- F2 or Enter: edit the current editable selection
- Tab / Shift+Tab: move the active cell across editable bulk columns
- Shift+Arrow: extend the current cell selection range
- Home / End: jump to first or last editable column on the current row
- Ctrl+Arrow: jump to row or editable-column edges in the current direction
- Esc: clear the current selection
- Shift+Space: select current row
- Ctrl+Space: select current column

Planned next
- commit-and-move behavior while actively editing cells
- Page Up / Page Down: stronger spreadsheet navigation
"""
MAX_BULK_HISTORY = 25


def _session_field(name):
    def _get(self):
        return getattr(self.session, name)

    def _set(self, value):
        setattr(self.session, name, value)

    return property(_get, _set)


# ─── Order Rules (persistent per-item buy rules) ────────────────────────────

def get_rule_key(line_code, item_code):
    """Build a consistent key for the order rules dict."""
    return f"{line_code}:{item_code}"


def load_app_version(path=VERSION_FILE):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = handle.read().strip()
            return value or "dev"
    except Exception:
        return "dev"


APP_VERSION = load_app_version()


def _parse_version_parts(value):
    normalized = str(value or "").strip().lstrip("vV")
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", normalized)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def is_release_version(value):
    return _parse_version_parts(value) is not None


def is_newer_version(candidate, current):
    candidate_parts = _parse_version_parts(candidate)
    current_parts = _parse_version_parts(current)
    if candidate_parts is None or current_parts is None:
        return False
    return candidate_parts > current_parts


def fetch_latest_github_release(url=GITHUB_RELEASES_API_URL, timeout=3):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"PO-Builder/{APP_VERSION}",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {
        "tag_name": str(payload.get("tag_name", "")).strip(),
        "html_url": str(payload.get("html_url", "")).strip() or GITHUB_RELEASES_PAGE_URL,
        "name": str(payload.get("name", "")).strip(),
        "published_at": str(payload.get("published_at", "")).strip(),
    }

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
    sales_items = _session_field("sales_items")
    po_items = _session_field("po_items")
    suspended_items = _session_field("suspended_items")
    suspended_set = _session_field("suspended_set")
    suspended_lookup = _session_field("suspended_lookup")
    open_po_lookup = _session_field("open_po_lookup")
    all_line_codes = _session_field("all_line_codes")
    inventory_lookup = _session_field("inventory_lookup")
    inventory_source_lookup = _session_field("inventory_source_lookup")
    pack_size_lookup = _session_field("pack_size_lookup")
    pack_size_source_lookup = _session_field("pack_size_source_lookup")
    pack_size_by_item = _session_field("pack_size_by_item")
    pack_size_conflicts = _session_field("pack_size_conflicts")
    qoh_adjustments = _session_field("qoh_adjustments")
    recent_orders = _session_field("recent_orders")
    order_rules = _session_field("order_rules")
    vendor_codes_used = _session_field("vendor_codes_used")
    filtered_items = _session_field("filtered_items")
    assigned_items = _session_field("assigned_items")
    startup_warning_rows = _session_field("startup_warning_rows")
    def __init__(self, root):
        self.root = root
        self.app_settings = self._load_app_settings()
        self._startup_data_dir_warning = ""
        self.shared_data_dir = ""
        self.data_dir = LOCAL_DATA_DIR
        self.data_paths = {}
        self.update_check_enabled = False
        self.session = AppSessionState()
        self._configure_initial_data_dir()
        self.root.title("PO Builder — X4 Import Tool")
        self.root.geometry("1100x720")
        self.root.minsize(900, 600)

        # State
        self.excluded_line_codes = set()
        self.all_customers = []         # (code, name, count) from suspended items
        self.excluded_customers = set() # customer codes to exclude
        self.on_po_qty = {}             # (line_code, item_code) -> total qty on PO
        self.duplicate_ic_lookup = {}   # item_code -> set of line_codes (only dupes)
        self.dup_whitelist = set()      # persistent whitelist
        self.suspense_carry = {}
        self.individual_items = []
        self.last_removed_bulk_items = []  # [(index, item_dict)] for one-step undo
        self.bulk_undo_stack = []
        self.bulk_redo_stack = []
        self.bulk_sheet = None
        self.review_grid_editor = None
        self._loaded_dup_whitelist = set()
        self._loaded_order_rules = {}
        self._loaded_suspense_carry = {}
        self._loaded_vendor_codes = []
        self._load_persistent_state()

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
        if self._startup_data_dir_warning:
            self.root.after(100, lambda: messagebox.showwarning("Shared Data Folder", self._startup_data_dir_warning))
        if self.update_check_enabled:
            self.root.after(1500, self._start_update_check)

    # ── Loading Overlay ──────────────────────────────────────────────────

    @staticmethod
    def _build_data_paths(data_dir):
        return {
            "duplicate_whitelist": os.path.join(data_dir, "duplicate_whitelist.txt"),
            "order_history": os.path.join(data_dir, "order_history.json"),
            "order_rules": os.path.join(data_dir, "order_rules.json"),
            "suspense_carry": os.path.join(data_dir, "suspense_carry.json"),
            "sessions": os.path.join(data_dir, "sessions"),
            "vendor_codes": os.path.join(data_dir, "vendor_codes.txt"),
        }

    def _data_path(self, key):
        return self.data_paths[key]

    def _load_app_settings(self):
        settings = storage.load_json_file(APP_SETTINGS_FILE, {})
        return settings if isinstance(settings, dict) else {}

    def _save_app_settings(self):
        storage.save_json_file(APP_SETTINGS_FILE, self.app_settings)

    def _configure_initial_data_dir(self):
        requested = str(self.app_settings.get("shared_data_dir", "") or "").strip()
        self.update_check_enabled = bool(self.app_settings.get("check_for_updates_on_startup", True))
        if requested:
            normalized = os.path.abspath(requested)
            ok, reason = storage.validate_storage_directory(normalized)
            if ok:
                self.shared_data_dir = normalized
                self.data_dir = normalized
            else:
                self._startup_data_dir_warning = (
                    "Shared data folder is unavailable, so the app fell back to local data.\n\n"
                    f"Requested folder:\n{normalized}\n\nReason:\n{reason}"
                )
                self.app_settings["shared_data_dir"] = ""
                self._save_app_settings()
        self.data_paths = self._build_data_paths(self.data_dir)

    def _load_persistent_state(self):
        dup_whitelist, _ = storage.load_duplicate_whitelist(self._data_path("duplicate_whitelist"), with_meta=True)
        order_rules, _ = storage.load_order_rules_with_meta(self._data_path("order_rules"))
        suspense_carry, _ = storage.load_suspense_carry_with_meta(self._data_path("suspense_carry"))
        vendor_codes, _ = storage.load_vendor_codes(self._data_path("vendor_codes"), KNOWN_VENDORS, with_meta=True)
        self.dup_whitelist = set(dup_whitelist)
        self.order_rules = dict(order_rules)
        self.suspense_carry = dict(suspense_carry)
        self.vendor_codes_used = list(vendor_codes)
        self._loaded_dup_whitelist = set(self.dup_whitelist)
        self._loaded_order_rules = copy.deepcopy(self.order_rules)
        self._loaded_suspense_carry = copy.deepcopy(self.suspense_carry)
        self._loaded_vendor_codes = list(self.vendor_codes_used)
        self._refresh_data_folder_labels()

    def _active_data_folder_label(self):
        if self.shared_data_dir:
            return f"Shared Folder: {self.data_dir}"
        return f"Local Data: {self.data_dir}"

    def _refresh_data_folder_labels(self):
        if hasattr(self, "lbl_data_source"):
            self.lbl_data_source.config(text=self._active_data_folder_label())

    def _set_shared_data_folder(self):
        selected = filedialog.askdirectory(
            title="Select Shared Data Folder",
            initialdir=self.data_dir,
            mustexist=False,
        )
        if not selected:
            return
        normalized = os.path.abspath(selected)
        ok, reason = storage.validate_storage_directory(normalized)
        if not ok:
            messagebox.showerror("Shared Data Folder", f"Cannot use that folder:\n{reason}")
            return
        self.shared_data_dir = normalized
        self.data_dir = normalized
        self.data_paths = self._build_data_paths(self.data_dir)
        self.app_settings["shared_data_dir"] = normalized
        self._save_app_settings()
        self._load_persistent_state()
        if self.filtered_items or self.assigned_items:
            messagebox.showinfo(
                "Shared Data Folder Updated",
                "Reload files to apply the shared rules, history, and vendor list to the current session.",
            )

    def _use_local_data_folder(self):
        self.shared_data_dir = ""
        self.data_dir = LOCAL_DATA_DIR
        self.data_paths = self._build_data_paths(self.data_dir)
        self.app_settings["shared_data_dir"] = ""
        self._save_app_settings()
        self._load_persistent_state()
        if self.filtered_items or self.assigned_items:
            messagebox.showinfo(
                "Local Data Enabled",
                "Reload files to apply the local rules, history, and vendor list to the current session.",
            )

    def _set_update_check_enabled(self):
        if hasattr(self, "var_check_updates"):
            self.update_check_enabled = bool(self.var_check_updates.get())
        else:
            self.update_check_enabled = True
        self.app_settings["check_for_updates_on_startup"] = self.update_check_enabled
        self._save_app_settings()

    def _start_update_check(self):
        if not self.update_check_enabled or not is_release_version(APP_VERSION):
            return
        worker = threading.Thread(target=self._check_for_updates_worker, daemon=True)
        worker.start()

    def _check_for_updates_worker(self):
        try:
            release = fetch_latest_github_release()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError):
            return
        latest_tag = release.get("tag_name", "")
        if not is_newer_version(latest_tag, APP_VERSION):
            return
        self.root.after(0, lambda: self._prompt_for_update(release))

    def _prompt_for_update(self, release):
        latest_tag = release.get("tag_name", "")
        release_name = release.get("name") or latest_tag
        published_at = release.get("published_at", "")
        details = f"Version {latest_tag}"
        if release_name and release_name != latest_tag:
            details = f"{release_name} ({latest_tag})"
        if published_at:
            details += f"\nPublished: {published_at[:10]}"
        answer = messagebox.askyesno(
            "Update Available",
            f"A newer release is available on GitHub.\n\nCurrent version: {APP_VERSION}\nLatest release: {details}\n\nOpen the release page now?",
        )
        if answer:
            try:
                webbrowser.open(release.get("html_url") or GITHUB_RELEASES_PAGE_URL)
            except Exception:
                messagebox.showinfo(
                    "Release Page",
                    f"Open this page in your browser:\n{release.get('html_url') or GITHUB_RELEASES_PAGE_URL}",
                )

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
        return load_flow.parse_all_files(
            paths,
            old_po_warning_days=OLD_PO_WARNING_DAYS,
            short_sales_window_days=SHORT_SALES_WINDOW_DAYS,
        )

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
        result = storage.save_suspense_carry(
            self._data_path("suspense_carry"),
            self.suspense_carry,
            base_carry=self._loaded_suspense_carry,
        )
        self.suspense_carry = dict(result["payload"])
        self._loaded_suspense_carry = copy.deepcopy(self.suspense_carry)

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
        self.recent_orders = storage.get_recent_orders(self._data_path("order_history"), days)

        # Reset assignment state
        self.assigned_items = []
        self.qoh_adjustments = {}
        self.vendor_codes_used = storage.load_vendor_codes(self._data_path("vendor_codes"), KNOWN_VENDORS)
        for item in self.filtered_items:
            vendor = item.get("vendor", "").strip().upper()
            if vendor and vendor not in self.vendor_codes_used:
                self.vendor_codes_used.append(vendor)
        self.vendor_codes_used.sort()
        self._loaded_vendor_codes = list(self.vendor_codes_used)
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
        return item_workflow.find_filtered_item(self.filtered_items, key)

    @staticmethod
    def _normalize_vendor_code(value):
        return str(value or "").strip().upper()

    def _save_vendor_codes(self):
        result = storage.save_vendor_codes(
            self._data_path("vendor_codes"),
            self.vendor_codes_used,
            base_vendor_codes=self._loaded_vendor_codes,
        )
        self.vendor_codes_used = list(result["payload"])
        self._loaded_vendor_codes = list(self.vendor_codes_used)

    def _save_order_rules(self):
        result = storage.save_order_rules(
            self._data_path("order_rules"),
            self.order_rules,
            base_rules=self._loaded_order_rules,
        )
        self.order_rules = dict(result["payload"])
        self._loaded_order_rules = copy.deepcopy(self.order_rules)

    def _save_duplicate_whitelist(self):
        result = storage.save_duplicate_whitelist(
            self._data_path("duplicate_whitelist"),
            self.dup_whitelist,
            base_whitelist=self._loaded_dup_whitelist,
        )
        self.dup_whitelist = set(result["payload"])
        self._loaded_dup_whitelist = set(self.dup_whitelist)

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
        return item_workflow.get_effective_order_qty(item)

    def _set_effective_order_qty(self, item, qty, *, manual_override=False):
        item_workflow.set_effective_order_qty(item, qty, manual_override=manual_override)

    @staticmethod
    def _clear_manual_override(item):
        item_workflow.clear_manual_override(item)

    def _recalculate_item(self, item):
        item_workflow.recalculate_item(
            item,
            self.inventory_lookup,
            self.order_rules,
            self._suggest_min_max,
            get_rule_key,
        )
        return item

    def _effective_order_rule(self, item, rule):
        return item_workflow.effective_order_rule(item, rule, self.inventory_lookup)

    def _sync_review_item_to_filtered(self, item):
        return item_workflow.sync_review_item_to_filtered(
            item,
            self.filtered_items,
            self.inventory_lookup,
            self.order_rules,
            self._suggest_min_max,
            get_rule_key,
        )

    def _bulk_row_values(self, item):
        return ui_bulk.bulk_row_values(self, item)

    def _refresh_suggestions(self):
        """Recalculate suggestions when the reorder cycle changes."""
        for item in self.filtered_items:
            self._recalculate_item(item)
        for item in self.assigned_items:
            self._sync_review_item_to_filtered(item)
        self._apply_bulk_filter()

    def _refresh_recent_orders(self):
        """Reload recent orders when lookback days changes."""
        try:
            days = self.var_lookback_days.get()
        except Exception:
            days = 14
        self.recent_orders = storage.get_recent_orders(self._data_path("order_history"), days)
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

    def _capture_bulk_history_state(self):
        return {
            "filtered_items": copy.deepcopy(self.filtered_items),
            "inventory_lookup": copy.deepcopy(self.inventory_lookup),
            "qoh_adjustments": copy.deepcopy(self.qoh_adjustments),
            "order_rules": copy.deepcopy(self.order_rules),
            "vendor_codes_used": list(self.vendor_codes_used),
            "_loaded_order_rules": copy.deepcopy(self._loaded_order_rules),
            "_loaded_vendor_codes": list(self._loaded_vendor_codes),
            "last_removed_bulk_items": copy.deepcopy(self.last_removed_bulk_items),
        }

    def _finalize_bulk_history_action(self, label, before_state):
        if before_state is None:
            return False
        after_state = self._capture_bulk_history_state()
        if after_state == before_state:
            return False
        self.bulk_undo_stack.append({
            "label": label,
            "before": before_state,
            "after": after_state,
        })
        if len(self.bulk_undo_stack) > MAX_BULK_HISTORY:
            self.bulk_undo_stack = self.bulk_undo_stack[-MAX_BULK_HISTORY:]
        self.bulk_redo_stack = []
        return True

    def _restore_bulk_history_state(self, state):
        self.filtered_items = copy.deepcopy(state.get("filtered_items", []))
        self.inventory_lookup = copy.deepcopy(state.get("inventory_lookup", {}))
        self.qoh_adjustments = copy.deepcopy(state.get("qoh_adjustments", {}))
        self.order_rules = copy.deepcopy(state.get("order_rules", {}))
        self.vendor_codes_used = list(state.get("vendor_codes_used", []))
        self._loaded_order_rules = copy.deepcopy(state.get("_loaded_order_rules", {}))
        self._loaded_vendor_codes = list(state.get("_loaded_vendor_codes", []))
        self.last_removed_bulk_items = copy.deepcopy(state.get("last_removed_bulk_items", []))
        self._refresh_vendor_inputs()
        if self.bulk_sheet:
            self.bulk_sheet.clear_selection()
        self._apply_bulk_filter()
        self._update_bulk_summary()
        self._update_bulk_cell_status()

    def _bulk_undo(self, event=None):
        if not self.bulk_undo_stack:
            return "break" if event is not None else None
        entry = self.bulk_undo_stack.pop()
        current_state = self._capture_bulk_history_state()
        self._restore_bulk_history_state(entry["before"])
        self.bulk_redo_stack.append({
            "label": entry.get("label", ""),
            "before": copy.deepcopy(entry["before"]),
            "after": current_state,
        })
        return "break" if event is not None else None

    def _bulk_redo(self, event=None):
        if not self.bulk_redo_stack:
            return "break" if event is not None else None
        entry = self.bulk_redo_stack.pop()
        current_state = self._capture_bulk_history_state()
        self._restore_bulk_history_state(entry["after"])
        self.bulk_undo_stack.append({
            "label": entry.get("label", ""),
            "before": current_state,
            "after": copy.deepcopy(entry["after"]),
        })
        return "break" if event is not None else None

    def _bulk_select_all(self, event=None):
        if self.bulk_sheet and self.bulk_sheet.select_all_visible():
            return "break"
        return None

    def _bulk_clear_selection(self, event=None):
        if self.bulk_sheet:
            self.bulk_sheet.clear_selection()
            self._right_click_bulk_context = None
            return "break"
        return None

    def _bulk_fill_selection_with_current_value(self, event=None, *, alias="fill"):
        if not self.bulk_sheet:
            return None
        col_name = (
            self.bulk_sheet.selected_editable_column_name()
            or self.bulk_sheet.current_editable_column_name()
        )
        row_ids = list(self.bulk_sheet.selected_target_row_ids(col_name)) if col_name else []
        if col_name not in BULK_EDITABLE_COLS or not row_ids:
            return "break"
        value = self.bulk_sheet.current_cell_value().strip()
        before_state = self._capture_bulk_history_state() if hasattr(self, "_capture_bulk_history_state") else None
        write_debug(
            "bulk_shortcut_fill",
            alias=alias,
            col_name=col_name,
            row_count=len(row_ids),
            value=value,
        )
        for row_id in row_ids:
            self._bulk_apply_editor_value(row_id, col_name, value)
        self._apply_bulk_filter()
        self.bulk_sheet.clear_selection()
        self._update_bulk_summary()
        self._update_bulk_cell_status()
        if hasattr(self, "_finalize_bulk_history_action"):
            self._finalize_bulk_history_action(f"{alias}:{col_name}", before_state)
        return "break"

    def _bulk_fill_down_selection(self, event=None):
        return self._bulk_fill_selection_with_current_value(event, alias="fill_down")

    def _bulk_fill_right_selection(self, event=None):
        return self._bulk_fill_selection_with_current_value(event, alias="fill_right")

    def _bulk_apply_current_value_to_selection(self, event=None):
        return self._bulk_fill_selection_with_current_value(event, alias="ctrl_enter")

    def _bulk_move_next_editable_cell(self, event=None):
        if self.bulk_sheet and self.bulk_sheet.move_current_editable_cell(1):
            return "break"
        return None

    def _bulk_move_prev_editable_cell(self, event=None):
        if self.bulk_sheet and self.bulk_sheet.move_current_editable_cell(-1):
            return "break"
        return None

    def _bulk_extend_selection_up(self, event=None):
        if self.bulk_sheet and self.bulk_sheet.extend_selection(-1, 0):
            return "break"
        return None

    def _bulk_extend_selection_down(self, event=None):
        if self.bulk_sheet and self.bulk_sheet.extend_selection(1, 0):
            return "break"
        return None

    def _bulk_extend_selection_left(self, event=None):
        if self.bulk_sheet and self.bulk_sheet.extend_selection(0, -1):
            return "break"
        return None

    def _bulk_extend_selection_right(self, event=None):
        if self.bulk_sheet and self.bulk_sheet.extend_selection(0, 1):
            return "break"
        return None

    def _bulk_jump_home(self, event=None):
        if self.bulk_sheet and self.bulk_sheet.jump_current_cell("home", ctrl=False):
            return "break"
        return None

    def _bulk_jump_end(self, event=None):
        if self.bulk_sheet and self.bulk_sheet.jump_current_cell("end", ctrl=False):
            return "break"
        return None

    def _bulk_jump_ctrl_left(self, event=None):
        if self.bulk_sheet and self.bulk_sheet.jump_current_cell("left", ctrl=True):
            return "break"
        return None

    def _bulk_jump_ctrl_right(self, event=None):
        if self.bulk_sheet and self.bulk_sheet.jump_current_cell("right", ctrl=True):
            return "break"
        return None

    def _bulk_jump_ctrl_up(self, event=None):
        if self.bulk_sheet and self.bulk_sheet.jump_current_cell("up", ctrl=True):
            return "break"
        return None

    def _bulk_jump_ctrl_down(self, event=None):
        if self.bulk_sheet and self.bulk_sheet.jump_current_cell("down", ctrl=True):
            return "break"
        return None

    def _show_bulk_shortcuts(self):
        messagebox.showinfo("Bulk Shortcuts", BULK_SHORTCUTS_TEXT)

    def _bulk_begin_edit(self, event=None):
        if not self.bulk_sheet:
            return None
        right_click_context = getattr(self, "_right_click_bulk_context", None) or {}
        col_name = (
            right_click_context.get("col_name", "")
            or
            self.bulk_sheet.selected_editable_column_name()
            or self.bulk_sheet.current_editable_column_name()
        )
        row_ids = []
        if col_name:
            row_ids = list(self.bulk_sheet.selected_target_row_ids(col_name))
        clicked_row_id = right_click_context.get("row_id")
        if clicked_row_id:
            if not row_ids or clicked_row_id not in row_ids:
                row_ids = [clicked_row_id]
        if not row_ids and self.bulk_sheet:
            row_ids = list(self.bulk_sheet.selected_row_ids())
        write_debug(
            "bulk_begin_edit",
            col_name=col_name,
            row_ids=",".join(row_ids),
            row_count=len(row_ids),
            right_click_row_id=clicked_row_id or "",
        )
        if col_name == "buy_rule" and row_ids:
            self._open_buy_rule_editor(int(row_ids[0]))
            write_debug("bulk_begin_edit.buy_rule_editor", row_id=row_ids[0])
            self._right_click_bulk_context = None
            return "break"
        if col_name in BULK_EDITABLE_COLS and len(row_ids) >= 1:
            if len(row_ids) == 1:
                prompt = f"Enter a value for {col_name}:"
            else:
                prompt = f"Enter a value for {col_name} across {len(row_ids)} selected row(s):"
            initial = self.bulk_sheet.current_cell_value()
            value = simpledialog.askstring("Bulk Edit Selection", prompt, parent=self.root, initialvalue=initial)
            write_debug("bulk_begin_edit.prompt_result", col_name=col_name, value="" if value is None else value, cancelled=value is None)
            if value is None:
                return "break"
            before_state = self._capture_bulk_history_state() if hasattr(self, "_capture_bulk_history_state") else None
            for row_id in row_ids:
                self._bulk_apply_editor_value(row_id, col_name, value.strip())
            self._apply_bulk_filter()
            for row_id in row_ids[:12]:
                try:
                    rendered = self._bulk_row_values(self.filtered_items[int(row_id)])
                    write_debug(
                        "bulk_begin_edit.rendered_row",
                        row_id=row_id,
                        col_name=col_name,
                        rendered=" || ".join("" if cell is None else str(cell) for cell in rendered),
                    )
                except Exception as exc:
                    write_debug("bulk_begin_edit.rendered_row_error", row_id=row_id, col_name=col_name, error=str(exc))
            if self.bulk_sheet:
                self.bulk_sheet.clear_selection()
            self._right_click_bulk_context = None
            self._update_bulk_summary()
            self._update_bulk_cell_status()
            if hasattr(self, "_finalize_bulk_history_action"):
                self._finalize_bulk_history_action(f"edit:{col_name}", before_state)
            return "break"
        self.bulk_sheet.sheet.open_cell()
        write_debug("bulk_begin_edit.open_cell", col_name=col_name, row_count=len(row_ids))
        self._right_click_bulk_context = None
        return "break"

    def _bulk_begin_edit_from_menu(self):
        write_debug(
            "bulk_begin_edit.menu_command",
            right_click_context=repr(getattr(self, "_right_click_bulk_context", None)),
        )
        return self._bulk_begin_edit()

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
        before_state = self._capture_bulk_history_state() if hasattr(self, "_capture_bulk_history_state") else None
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
        if hasattr(self, "_finalize_bulk_history_action"):
            self._finalize_bulk_history_action("remove_rows", before_state)
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
        before_state = self._capture_bulk_history_state() if hasattr(self, "_capture_bulk_history_state") else None
        if self.bulk_sheet:
            for row_id in row_ids:
                self._bulk_apply_editor_value(row_id, col_name, value.strip())
            self._apply_bulk_filter()
            self.bulk_sheet.clear_selection()
        else:
            for row_id in row_ids:
                self._bulk_apply_editor_value(row_id, col_name, value.strip())
            self._apply_bulk_filter()
        self._update_bulk_summary()
        self._update_bulk_cell_status()
        if hasattr(self, "_finalize_bulk_history_action"):
            self._finalize_bulk_history_action(f"fill:{col_name}", before_state)

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
        before_state = self._capture_bulk_history_state() if hasattr(self, "_capture_bulk_history_state") else None
        if self.bulk_sheet:
            for row_id in row_ids:
                self._bulk_apply_editor_value(row_id, col_name, "")
            self._apply_bulk_filter()
            self.bulk_sheet.clear_selection()
        else:
            for row_id in row_ids:
                self._bulk_apply_editor_value(row_id, col_name, "")
            self._apply_bulk_filter()
        self._update_bulk_summary()
        self._update_bulk_cell_status()
        if hasattr(self, "_finalize_bulk_history_action"):
            self._finalize_bulk_history_action(f"clear:{col_name}", before_state)

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
        write_debug("bulk_apply_editor_value.begin", row_id=row_id, col_name=col_name, raw=str(raw))
        if col_name == "buy_rule":
            self._open_buy_rule_editor(idx)
            write_debug("bulk_apply_editor_value.buy_rule_editor", row_id=row_id)
            return
        if col_name not in BULK_EDITABLE_COLS:
            write_debug("bulk_apply_editor_value.skip", row_id=row_id, col_name=col_name, reason="not_editable")
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
                write_debug("bulk_apply_editor_value.vendor", row_id=row_id, vendor=new_val)
        elif col_name == "final_qty":
            try:
                qty = int(float(raw))
                self._set_effective_order_qty(item, qty, manual_override=True)
                self._recalculate_item(item)
                write_debug(
                    "bulk_apply_editor_value.final_qty",
                    row_id=row_id,
                    qty=qty,
                    suggested=item.get("suggested_qty"),
                    final=item.get("final_qty"),
                    why=item.get("why", ""),
                )
            except ValueError:
                write_debug("bulk_apply_editor_value.error", row_id=row_id, col_name=col_name, raw=str(raw), reason="value_error")
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
                write_debug(
                    "bulk_apply_editor_value.qoh",
                    row_id=row_id,
                    old_qoh=old_qoh,
                    new_qoh=new_qoh,
                    raw_need=item.get("raw_need"),
                    suggested=item.get("suggested_qty"),
                    final=item.get("final_qty"),
                )
            except ValueError:
                write_debug("bulk_apply_editor_value.error", row_id=row_id, col_name=col_name, raw=str(raw), reason="value_error")
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
                write_debug(
                    "bulk_apply_editor_value.minmax",
                    row_id=row_id,
                    col_name=col_name,
                    parsed=parsed,
                    raw_need=item.get("raw_need"),
                    suggested=item.get("suggested_qty"),
                    final=item.get("final_qty"),
                )
            except ValueError:
                write_debug("bulk_apply_editor_value.error", row_id=row_id, col_name=col_name, raw=str(raw), reason="value_error")
                pass
        elif col_name == "pack_size":
            try:
                old_pack = item.get("pack_size")
                old_policy = item.get("order_policy", "")
                old_suggested = item.get("suggested_qty")
                old_final = item.get("final_qty")
                rule_key, rule = item_workflow.apply_pack_size_edit(item, raw, self.order_rules, get_rule_key)
                self._save_order_rules()
                self._clear_manual_override(item)
                self._recalculate_item(item)
                write_debug(
                    "bulk_apply_editor_value.pack_size",
                    row_id=row_id,
                    line_code=item.get("line_code", ""),
                    item_code=item.get("item_code", ""),
                    old_pack=old_pack,
                    new_pack=item.get("pack_size"),
                    old_policy=old_policy,
                    new_policy=item.get("order_policy", ""),
                    old_suggested=old_suggested,
                    new_suggested=item.get("suggested_qty"),
                    old_final=old_final,
                    new_final=item.get("final_qty"),
                    rule=json.dumps(self.order_rules.get(rule_key, {}), sort_keys=True),
                    why=item.get("why", ""),
                )
            except ValueError:
                write_debug("bulk_apply_editor_value.error", row_id=row_id, col_name=col_name, raw=str(raw), reason="value_error")
                pass

    def _apply_bulk_filter(self):
        ui_bulk.apply_bulk_filter(self)
        sample = ""
        if self.filtered_items:
            item = self.filtered_items[0]
            sample = f"{item.get('line_code', '')}:{item.get('item_code', '')}"
        write_debug("bulk_filter.applied", total=len(self.filtered_items), sample=sample)

    def _open_buy_rule_editor(self, idx):
        item = self.filtered_items[idx] if 0 <= idx < len(self.filtered_items) else {}
        write_debug(
            "bulk_open_buy_rule_editor",
            idx=idx,
            line_code=item.get("line_code", ""),
            item_code=item.get("item_code", ""),
            right_click_context=repr(getattr(self, "_right_click_bulk_context", None)),
        )
        ui_bulk_dialogs.open_buy_rule_editor(self, idx, self._data_path("order_rules"))

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
        self._save_duplicate_whitelist()
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
                item_workflow.apply_pack_size_edit(item, raw, self.order_rules, get_rule_key)
                self._save_order_rules()
                self._clear_manual_override(item)
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
        export_flow.do_export(
            self,
            export_vendor_po,
            self._data_path("order_history"),
            self._data_path("sessions"),
        )

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
