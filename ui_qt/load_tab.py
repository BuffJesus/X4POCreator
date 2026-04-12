"""Qt Load tab — file pickers, folder scan, parse worker.

Mirrors the functional surface of the tkinter ``ui_load.py`` but stays
framework-independent at the data-definition layer: the same
``LOAD_FILE_SECTIONS`` tuple defines both versions, so any new source
report added to ``ui_load.py`` automatically shows up here too.

Parsing runs on a ``QThread`` so the main GUI thread stays responsive
while ``load_flow.parse_all_files`` churns through the ~293 MB detailed
sales CSV.  Progress text is streamed through a Qt signal back to the
main thread.

The tab emits two signals the shell can hook into:

- ``load_started``  — fired when the worker begins (disable sidebar,
  show progress)
- ``load_finished(result_dict)``  — fired with the parse result when the
  worker is done; the shell decides what to do next (apply to session,
  switch to Bulk tab, surface warnings)

For alpha2 the shell just shows a completion message box with a summary
— the sessions → bulk tab flow lands in alpha3 when the bulk grid
exists.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

from PySide6.QtCore import (
    QObject,
    QThread,
    Qt,
    Signal,
)
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import theme as t
import theme_qt as tq

# Reuse the shared pure-data module so both UIs stay in sync.  We go
# straight to ``ui_load_data`` (not ``ui_load``) so the Qt build never
# imports tkinter transitively — the Qt PyInstaller spec excludes it.
from ui_load_data import LOAD_FILE_SECTIONS  # noqa: E402


# Map from `LOAD_FILE_SECTIONS` browse_key → the key used by
# ``load_flow.parse_all_files`` and ``parsers.scan_directory_for_reports``.
# The two modules use slightly different names for historical reasons:
# the UI rows key off "detailedsales" while the parser emits
# "detailedsales" too, but load_flow's paths dict uses "detailedsales" as
# well — these map 1:1, documented here to prevent a rename from drifting.
BROWSE_KEY_TO_PARSER_KEY = {
    "detailedsales": "detailedsales",
    "receivedparts": "receivedparts",
    "minmax":        "minmax",
    "packsize":      "packsize",
    "onhand":        "onhand",
    "po":            "po",
    "susp":          "susp",
}

REQUIRED_BROWSE_KEYS = ("detailedsales", "receivedparts")


def _report_name(browse_key: str) -> str:
    return {
        "detailedsales": "Detailed Part Sales",
        "receivedparts": "Received Parts Detail",
        "minmax":        "On Hand Min/Max Sales",
        "packsize":      "Order Multiples",
        "onhand":        "On Hand Report",
        "po":            "Open PO Listing",
        "susp":          "Suspended Items",
    }.get(browse_key, browse_key)


# ─── Worker thread ─────────────────────────────────────────────────────────

class ParseWorker(QObject):
    """QObject-in-QThread parser.

    Lives in its own QThread so the main event loop can redraw during
    the parse.  Communicates with the UI via signals only — never touch
    widgets from inside ``run()``.
    """

    progress = Signal(str)        # progress message for the UI
    finished = Signal(dict)       # parse result dict on success
    failed   = Signal(str)        # error message on exception

    def __init__(
        self,
        paths: dict,
        stored_schema_hashes: Optional[dict] = None,
        parse_callable: Optional[Callable] = None,
    ):
        super().__init__()
        self.paths = paths
        self.stored_schema_hashes = stored_schema_hashes or {}
        # parse_callable override is for tests.  Production path imports
        # load_flow lazily so alpha2 tests that mock the parser don't
        # have to pull in the full parse stack.
        self._parse_callable = parse_callable

    def run(self):
        try:
            parse_fn = self._parse_callable
            if parse_fn is None:
                import load_flow
                parse_fn = load_flow.parse_all_files
            self.progress.emit("Starting file load...")

            def _progress_cb(message: str):
                # Always marshal back through the signal — never call
                # directly into a QWidget from the worker thread.
                self.progress.emit(str(message))

            # Upstream kwargs are stable.  Keep them keyed so any future
            # addition to parse_all_files doesn't silently position-shift.
            result = parse_fn(
                self.paths,
                old_po_warning_days=90,
                short_sales_window_days=60,
                progress_callback=_progress_cb,
                stored_schema_hashes=self.stored_schema_hashes,
            )
            self.finished.emit(result or {})
        except Exception as exc:  # pragma: no cover - safety net
            self.failed.emit(str(exc))


# ─── Helper widgets ────────────────────────────────────────────────────────

class FilePickerRow(QWidget):
    """Label + path entry + browse button for one source CSV.

    Exposes a simple ``set_path`` / ``path()`` interface so scan results
    can populate it without the caller touching internal widgets.
    """

    path_changed = Signal()

    def __init__(self, label: str, hint: str, required: bool = False, parent=None):
        super().__init__(parent)
        self._required = required
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(t.SPACE_SM)

        # Status badge
        self._badge = QLabel("\u25CB")  # empty circle
        self._badge.setFixedWidth(18)
        self._badge.setAlignment(Qt.AlignCenter)
        self._badge.setStyleSheet(f"color: {t.TEXT_DIM}; font-size: {t.FONT_MEDIUM}px;")
        layout.addWidget(self._badge)

        label_col = QVBoxLayout()
        label_col.setContentsMargins(0, 0, 0, 0)
        label_col.setSpacing(0)

        primary = QLabel(label)
        primary.setStyleSheet(
            f"color: {t.TEXT_PRIMARY}; font-size: {t.FONT_BODY}px; font-weight: bold;"
        )
        label_col.addWidget(primary)

        hint_label = QLabel(hint)
        hint_label.setStyleSheet(
            f"color: {t.TEXT_DIM}; font-size: {t.FONT_MICRO}px;"
        )
        hint_label.setWordWrap(True)
        label_col.addWidget(hint_label)

        label_wrap = QWidget()
        label_wrap.setLayout(label_col)
        label_wrap.setFixedWidth(250)
        layout.addWidget(label_wrap)

        self._entry = QLineEdit()
        self._entry.setPlaceholderText("Path to CSV\u2026")
        self._entry.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._entry, stretch=1)

        browse_btn = QPushButton("Browse\u2026")
        browse_btn.setFixedWidth(100)
        browse_btn.clicked.connect(self._on_browse)
        layout.addWidget(browse_btn)

    def _on_text_changed(self):
        self._update_badge()
        self.path_changed.emit()

    def _update_badge(self):
        path = self._entry.text().strip()
        if path and os.path.isfile(path):
            self._badge.setText("\u2713")  # checkmark
            self._badge.setStyleSheet(f"color: {t.ACCENT_OK}; font-size: {t.FONT_MEDIUM}px; font-weight: bold;")
        elif path:
            self._badge.setText("\u2717")  # X mark — path set but file not found
            self._badge.setStyleSheet(f"color: {t.ACCENT_DANGER}; font-size: {t.FONT_MEDIUM}px; font-weight: bold;")
        elif self._required:
            self._badge.setText("\u25CF")  # filled circle — required, empty
            self._badge.setStyleSheet(f"color: {t.ACCENT_WARNING}; font-size: {t.FONT_MEDIUM}px;")
        else:
            self._badge.setText("\u25CB")  # empty circle — optional, empty
            self._badge.setStyleSheet(f"color: {t.TEXT_DIM}; font-size: {t.FONT_MEDIUM}px;")

    def _on_browse(self):
        start_dir = os.path.dirname(self._entry.text()) if self._entry.text() else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select CSV",
            start_dir,
            "CSV files (*.csv);;All files (*)",
        )
        if path:
            self._entry.setText(path)

    def path(self) -> str:
        return self._entry.text().strip()

    def set_path(self, value: str):
        self._entry.setText(value or "")


class FileSection(QFrame):
    """Card container for a related group of FilePickerRows."""

    def __init__(self, title: str, summary: str, rows: list[tuple[str, str, str]],
                 required_keys: set | None = None, parent=None):
        """rows is a list of (label, browse_key, hint) tuples."""
        super().__init__(parent)
        self.setStyleSheet(tq.card_style(t.ACCENT_PRIMARY))
        _required = required_keys or set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SPACE_MD, t.SPACE_MD, t.SPACE_MD, t.SPACE_MD)
        layout.setSpacing(t.SPACE_SM)

        header = QLabel(title)
        header.setStyleSheet(
            f"color: {t.TEXT_PRIMARY}; font-size: {t.FONT_LABEL}px; font-weight: bold;"
        )
        layout.addWidget(header)

        summary_label = QLabel(summary)
        summary_label.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FONT_SMALL}px;"
        )
        summary_label.setWordWrap(True)
        layout.addWidget(summary_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {t.BORDER_SOFT}; background: {t.BORDER_SOFT};")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        self.pickers: dict[str, FilePickerRow] = {}
        for label, browse_key, hint in rows:
            picker = FilePickerRow(label, hint, required=browse_key in _required)
            layout.addWidget(picker)
            self.pickers[browse_key] = picker


# ─── Main Load tab ─────────────────────────────────────────────────────────

class LoadTab(QWidget):
    """Top-level Qt Load tab.

    Self-contained: the only coupling to the rest of the app is via
    signals (``load_finished``, ``load_failed``) and a callable factory
    that can be overridden in tests.

    Usage:

        tab = LoadTab()
        tab.load_finished.connect(on_result)
        shell.stack.addWidget(tab)
    """

    load_started  = Signal()
    load_finished = Signal(dict)  # parse result
    load_failed   = Signal(str)

    def __init__(self, *, app_settings: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self._app_settings = app_settings if app_settings is not None else {}
        self._worker: Optional[ParseWorker] = None
        self._thread: Optional[QThread] = None
        self._pickers: dict[str, FilePickerRow] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Scroll area so long forms stay usable at small window sizes ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(
            t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG
        )
        content_layout.setSpacing(t.SPACE_MD)
        scroll.setWidget(content)

        # ─── Hero banner ────────────────────────────────────────
        hero = QLabel()
        hero.setTextFormat(Qt.RichText)
        hero.setText(tq.tab_header_html(
            "Load Files",
            "Point PO Builder at the X4 CSV exports to start a run",
        ))
        hero.setStyleSheet(tq.tab_header_style())
        content_layout.addWidget(hero)

        # ─── Quick Start (only if last_scan_folder exists) ──────
        last_folder = str(self._app_settings.get("last_scan_folder", "") or "").strip()
        if last_folder and os.path.isdir(last_folder):
            quick = self._build_quick_start_card(last_folder)
            content_layout.addWidget(quick)

        # ─── Folder scan card ───────────────────────────────────
        scan_card = self._build_scan_card(last_folder)
        content_layout.addWidget(scan_card)

        # ─── File picker sections ───────────────────────────────
        for section in LOAD_FILE_SECTIONS:
            rows = [
                (row["label"], row["browse_key"], row["hint"])
                for row in section["rows"]
            ]
            section_card = FileSection(
                section["title"], section["summary"], rows,
                required_keys=set(REQUIRED_BROWSE_KEYS),
            )
            content_layout.addWidget(section_card)
            for key, picker in section_card.pickers.items():
                self._pickers[key] = picker
                picker.path_changed.connect(self._update_load_button_state)

        # ─── Status + progress strip ────────────────────────────
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FONT_BODY}px;"
        )
        self._status_label.setWordWrap(True)
        content_layout.addWidget(self._status_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # busy indicator (marquee)
        self._progress.setVisible(False)
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(
            f"QProgressBar {{ border: 1px solid {t.BORDER}; "
            f"  border-radius: 3px; background: {t.BG_PANEL}; }}"
            f"QProgressBar::chunk {{ background: {t.ACCENT_PRIMARY}; }}"
        )
        content_layout.addWidget(self._progress)

        # ─── Footer (Load button) ───────────────────────────────
        footer = QHBoxLayout()
        footer.setContentsMargins(0, t.SPACE_SM, 0, 0)
        footer.addStretch(1)

        self._load_button = QPushButton("Load Files →")
        self._load_button.setFixedHeight(36)
        self._load_button.setMinimumWidth(160)
        self._load_button.setStyleSheet(
            f"QPushButton {{ background: {t.ACCENT_PRIMARY}; "
            f"  color: {t.TEXT_INVERSE}; border: none; "
            f"  border-radius: {t.RADIUS_SM}px; font-weight: bold; "
            f"  font-size: {t.FONT_MEDIUM}px; padding: 6px 18px; }}"
            f"QPushButton:hover {{ background: #6bb0ea; }}"
            f"QPushButton:disabled {{ background: {t.BG_INSET}; "
            f"  color: {t.TEXT_DIM}; }}"
        )
        self._load_button.clicked.connect(self._on_load_clicked)
        footer.addWidget(self._load_button)

        content_layout.addStretch(1)
        content_layout.addLayout(footer)

        self._update_load_button_state()

    # ─── Scan / quick-start cards ──────────────────────────────

    def _build_quick_start_card(self, last_folder: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(tq.card_style(t.ACCENT_OK))
        layout = QVBoxLayout(card)
        layout.setContentsMargins(t.SPACE_MD, t.SPACE_MD, t.SPACE_MD, t.SPACE_MD)
        layout.setSpacing(t.SPACE_XS)

        title = QLabel("Quick Start")
        title.setStyleSheet(
            f"color: {t.TEXT_PRIMARY}; font-size: {t.FONT_LABEL}px; font-weight: bold;"
        )
        layout.addWidget(title)

        path_label = QLabel(f"Last folder: {last_folder}")
        path_label.setStyleSheet(
            f"color: {t.TEXT_DIM}; font-size: {t.FONT_SMALL}px;"
        )
        path_label.setWordWrap(True)
        layout.addWidget(path_label)

        btn = QPushButton("Scan & Load Now")
        btn.setFixedHeight(30)
        btn.setFixedWidth(180)
        btn.clicked.connect(lambda: self._quick_load(last_folder))
        layout.addWidget(btn)
        return card

    def _build_scan_card(self, initial_path: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(tq.card_style())
        layout = QVBoxLayout(card)
        layout.setContentsMargins(t.SPACE_MD, t.SPACE_MD, t.SPACE_MD, t.SPACE_MD)
        layout.setSpacing(t.SPACE_SM)

        title = QLabel("Auto-Detect from Folder")
        title.setStyleSheet(
            f"color: {t.TEXT_PRIMARY}; font-size: {t.FONT_LABEL}px; font-weight: bold;"
        )
        layout.addWidget(title)

        summary = QLabel(
            "Select a folder containing the weekly X4 exports and PO Builder "
            "will identify each CSV automatically."
        )
        summary.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FONT_SMALL}px;"
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        row = QHBoxLayout()
        self._scan_entry = QLineEdit()
        self._scan_entry.setText(initial_path)
        self._scan_entry.setPlaceholderText("Folder path…")
        row.addWidget(self._scan_entry, stretch=1)

        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(100)
        browse_btn.clicked.connect(self._on_browse_folder)
        row.addWidget(browse_btn)

        scan_btn = QPushButton("Scan && Populate")
        scan_btn.setFixedWidth(140)
        scan_btn.clicked.connect(self._on_scan_folder)
        row.addWidget(scan_btn)

        layout.addLayout(row)

        self._scan_status = QLabel("")
        self._scan_status.setStyleSheet(
            f"color: {t.TEXT_DIM}; font-size: {t.FONT_SMALL}px;"
        )
        self._scan_status.setWordWrap(True)
        layout.addWidget(self._scan_status)

        return card

    # ─── Actions ───────────────────────────────────────────────

    def _on_browse_folder(self):
        start = self._scan_entry.text().strip()
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Folder Containing X4 Report CSVs",
            start,
        )
        if path:
            self._scan_entry.setText(path)

    def _on_scan_folder(self):
        folder = self._scan_entry.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.information(self, "No Folder", "Please select a valid folder first.")
            return
        try:
            import parsers
            found = parsers.scan_directory_for_reports(folder)
        except Exception as exc:
            QMessageBox.critical(self, "Scan Failed", f"Could not scan folder:\n{exc}")
            return

        populated = []
        for browse_key, picker in self._pickers.items():
            parser_key = BROWSE_KEY_TO_PARSER_KEY.get(browse_key, browse_key)
            filepath = found.get(parser_key) or found.get(browse_key)
            if filepath:
                picker.set_path(filepath)
                populated.append(_report_name(browse_key))

        if populated:
            self._scan_status.setText(
                f"\u2713  Found {len(populated)} report(s): {', '.join(populated)}"
            )
            self._app_settings["last_scan_folder"] = folder
        else:
            self._scan_status.setText(
                "No X4 report CSVs detected in that folder."
            )
        self._update_load_button_state()

    def _quick_load(self, folder: str):
        self._scan_entry.setText(folder)
        self._on_scan_folder()
        # Small delay isn't needed under Qt — just fire the load directly
        # once the pickers are populated.
        self._on_load_clicked()

    def _update_load_button_state(self):
        ready = all(self._pickers.get(k) and self._pickers[k].path() for k in REQUIRED_BROWSE_KEYS)
        self._load_button.setEnabled(ready)
        if not ready:
            self._status_label.setText(
                "Detailed Part Sales and Received Parts Detail are required before loading."
            )
            self._status_label.setStyleSheet(
                f"color: {t.TEXT_DIM}; font-size: {t.FONT_BODY}px;"
            )

    def current_paths(self) -> dict:
        """Return the current paths dict in the shape load_flow expects."""
        out = {}
        for browse_key, picker in self._pickers.items():
            parser_key = BROWSE_KEY_TO_PARSER_KEY.get(browse_key, browse_key)
            out[parser_key] = picker.path()
        return out

    def _on_load_clicked(self):
        paths = self.current_paths()
        if not paths.get("detailedsales") or not paths.get("receivedparts"):
            QMessageBox.warning(
                self,
                "Missing File",
                "Load both Detailed Part Sales and Received Parts Detail CSVs.",
            )
            return

        stored_hashes = {}
        raw = self._app_settings.get("csv_schema_hashes", {}) if self._app_settings else {}
        if isinstance(raw, dict):
            stored_hashes = {str(k): str(v) for k, v in raw.items() if v}

        self._start_worker(paths, stored_hashes)

    # ─── Worker lifecycle ──────────────────────────────────────

    def _start_worker(self, paths: dict, stored_hashes: dict):
        # Defensive: never stack two workers on top of each other.
        if self._thread is not None and self._thread.isRunning():
            QMessageBox.information(
                self, "Load in Progress", "A load is already running — please wait."
            )
            return

        self._load_button.setEnabled(False)
        self._progress.setVisible(True)
        self._status_label.setText("Starting file load…")
        self._status_label.setStyleSheet(
            f"color: {t.ACCENT_PRIMARY}; font-size: {t.FONT_BODY}px;"
        )
        self.load_started.emit()

        self._thread = QThread(self)
        self._worker = ParseWorker(paths, stored_hashes)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        # Tear down both objects once the worker signals done.
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _cleanup_thread(self):
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None
        self._progress.setVisible(False)
        self._update_load_button_state()

    def _on_progress(self, message: str):
        self._status_label.setText(message)

    def _on_finished(self, result: dict):
        # Persist fresh schema hashes so the next load has a baseline.
        fresh_hashes = result.get("csv_schema_hashes") if isinstance(result, dict) else None
        if isinstance(fresh_hashes, dict) and fresh_hashes:
            self._app_settings["csv_schema_hashes"] = dict(fresh_hashes)

        sales_items = result.get("sales_items") or []
        self._status_label.setStyleSheet(
            f"color: {t.ACCENT_OK}; font-size: {t.FONT_BODY}px;"
        )
        summary = f"Loaded {len(sales_items)} sales item(s)."
        warnings = result.get("warnings") or []
        if warnings:
            summary += f"  {len(warnings)} warning(s) found."
        self._status_label.setText(summary)
        self.load_finished.emit(result)

    def _on_failed(self, error: str):
        self._status_label.setStyleSheet(
            f"color: {t.ACCENT_DANGER}; font-size: {t.FONT_BODY}px;"
        )
        self._status_label.setText(f"Load failed: {error}")
        self.load_failed.emit(error)
        QMessageBox.critical(self, "Parse Error", f"Failed to parse source files:\n{error}")
