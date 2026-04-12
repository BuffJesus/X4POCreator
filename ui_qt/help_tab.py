"""Qt Help tab — section list on the left, scrollable body on the right.

Reuses ``ui_help.HELP_SECTIONS`` directly so the content stays in sync
with the tkinter tab.  Each section body uses a simple markdown-like
convention ("# heading1", "## heading2", "- bullet", "`code`") which we
translate to HTML at render time so Qt's ``QTextBrowser`` can display it
with the app's token palette.

Design notes:
- Plain ``QTextBrowser`` (not ``QWebEngineView``) — keeps the build
  light and doesn't need the QtWebEngine addon we deliberately excluded
  from the PyInstaller spec.
- Live search lands in beta1.  For alpha2 we just show the selected
  section body; section navigation is via the list widget on the left.
- The tab is self-contained: pass no arguments, get a ready-to-use
  ``QWidget``.
"""

from __future__ import annotations

import html
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

import theme as t
import theme_qt as tq

# Pure-data import — ``ui_help`` itself imports tkinter at module load,
# so the Qt build reaches directly into ``ui_help_data`` to avoid pulling
# the excluded stack.
from ui_help_data import HELP_SECTIONS  # noqa: E402


_INLINE_CODE_RE = re.compile(r"`([^`]+)`")


def _render_inline(text: str) -> str:
    """Convert inline markers in a single line to HTML.

    - Backtick-wrapped ``code`` → <code> span with inset background
    """
    escaped = html.escape(text)

    def _repl(match: re.Match) -> str:
        content = match.group(1)
        # ``match.group(1)`` was taken from the *unescaped* source, but
        # since backticks never survive HTML escaping, the content is
        # also unescaped — escape it here so user-entered < or & in a
        # code span still renders safely.
        escaped_code = html.escape(content)
        return (
            f"<code style='background:{t.BG_INSET}; color:{t.ACCENT_OK}; "
            f"padding:1px 4px; border-radius:3px; "
            f"font-family:Consolas,monospace;'>{escaped_code}</code>"
        )

    # Rewrite backtick code spans on the **escaped** string.  Because
    # html.escape doesn't touch backticks, we can still match them.
    return _INLINE_CODE_RE.sub(_repl, escaped)


def render_section_html(title: str, body: str) -> str:
    """Translate a (title, body) Help section into a themed HTML doc."""
    lines = (body or "").split("\n")
    parts: list[str] = []
    parts.append(
        f"<div style='color:{t.TEXT_SECONDARY}; "
        f"font-family:Segoe UI, sans-serif;'>"
    )

    # Promote the title to a heading1 when the body doesn't open with one.
    if not lines or not lines[0].lstrip().startswith("#"):
        parts.append(
            f"<h1 style='color:{t.TEXT_PRIMARY}; font-size:20px; "
            f"margin:0 0 10px 0; padding:0;'>"
            f"{html.escape(title)}</h1>"
        )

    in_list = False
    for line in lines:
        stripped = line.lstrip()
        if not stripped:
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append("<div style='height:6px;'></div>")
            continue
        if stripped.startswith("## "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(
                f"<h2 style='color:{t.ACCENT_PRIMARY}; font-size:15px; "
                f"margin:14px 0 4px 0;'>"
                f"{_render_inline(stripped[3:])}</h2>"
            )
            continue
        if stripped.startswith("# "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(
                f"<h1 style='color:{t.TEXT_PRIMARY}; font-size:18px; "
                f"margin:12px 0 6px 0;'>"
                f"{_render_inline(stripped[2:])}</h1>"
            )
            continue
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                parts.append(
                    f"<ul style='margin:4px 0 4px 18px; "
                    f"padding:0; color:{t.TEXT_SECONDARY};'>"
                )
                in_list = True
            parts.append(
                f"<li style='margin:2px 0;'>{_render_inline(stripped[2:])}</li>"
            )
            continue
        # Body text paragraph
        if in_list:
            parts.append("</ul>")
            in_list = False
        parts.append(
            f"<p style='margin:4px 0; color:{t.TEXT_SECONDARY};'>"
            f"{_render_inline(stripped)}</p>"
        )

    if in_list:
        parts.append("</ul>")
    parts.append("</div>")
    return "".join(parts)


class HelpTab(QWidget):
    """Two-pane Help surface.

    Left:  ``QListWidget`` with every section title.
    Right: ``QTextBrowser`` showing the selected section as rich HTML.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG
        )
        outer.setSpacing(t.SPACE_MD)

        # Header banner
        header = QLabel()
        header.setTextFormat(Qt.RichText)
        header.setText(tq.tab_header_html(
            "Help",
            "Documentation for reports, controls, and troubleshooting",
        ))
        header.setStyleSheet(tq.tab_header_style())
        outer.addWidget(header)

        # Split pane
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {t.BORDER}; }}"
        )

        # Section list
        self._sections = QListWidget()
        self._sections.setStyleSheet(
            f"QListWidget {{ background: {t.BG_PANEL}; "
            f"  border: 1px solid {t.BORDER}; "
            f"  border-radius: {t.RADIUS_SM}px; "
            f"  outline: none; font-size: {t.FONT_BODY}px; }}"
            f"QListWidget::item {{ padding: 8px 14px; "
            f"  color: {t.TEXT_MUTED}; border: none; }}"
            f"QListWidget::item:selected {{ background: {t.BG_ELEVATED}; "
            f"  color: {t.TEXT_PRIMARY}; "
            f"  border-left: 3px solid {t.ACCENT_PRIMARY}; }}"
            f"QListWidget::item:hover:!selected {{ background: {t.BG_BASE}; }}"
        )
        for title, intro, _body in HELP_SECTIONS:
            item = QListWidgetItem(title)
            item.setToolTip(intro)
            self._sections.addItem(item)
        self._sections.setMinimumWidth(200)
        self._sections.setMaximumWidth(260)
        splitter.addWidget(self._sections)

        # Body viewer
        self._body = QTextBrowser()
        self._body.setOpenExternalLinks(False)
        self._body.setReadOnly(True)
        self._body.setStyleSheet(
            f"QTextBrowser {{ background: {t.BG_PANEL}; "
            f"  color: {t.TEXT_SECONDARY}; "
            f"  border: 1px solid {t.BORDER}; "
            f"  border-radius: {t.RADIUS_SM}px; "
            f"  padding: {t.SPACE_MD}px; "
            f"  font-size: {t.FONT_BODY}px; }}"
        )
        splitter.addWidget(self._body)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        outer.addWidget(splitter, stretch=1)

        self._sections.currentRowChanged.connect(self._on_section_changed)
        if HELP_SECTIONS:
            self._sections.setCurrentRow(0)

    def _on_section_changed(self, row: int):
        if row < 0 or row >= len(HELP_SECTIONS):
            return
        title, _intro, body = HELP_SECTIONS[row]
        self._body.setHtml(render_section_html(title, body))
