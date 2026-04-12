import re
import tkinter as tk
from tkinter import ttk
import shipping_flow
from ui_scroll import attach_vertical_mousewheel


# ─── Help rendering colors (pulled from po_builder.py's clam theme) ────────────
# Hardcoding here rather than passing app.style through because tk.Text tags
# need direct color strings and the help tab is the only place they're used.
_HELP_BG = "#252538"
_HELP_FG = "#d6d6e5"
_HELP_HEADING1 = "#c4a3ff"   # PURPLE_BRIGHT
_HELP_HEADING2 = "#a084d9"   # PURPLE
_HELP_CODE_BG = "#1e1e2e"
_HELP_CODE_FG = "#f3c672"
_HELP_BULLET = "#8bb4ff"
_HELP_MATCH_BG = "#5b4670"   # search-hit highlight

# v0.10.0-alpha2: HELP_SECTIONS and CONTEXTUAL_HELP_MAP moved to
# ``ui_help_data.py`` so the Qt Help tab can import them without
# transitively pulling in tkinter (which this module imports at the
# top for its tk.Text-based rendering code).  Re-exported here so
# every existing caller that imports from ``ui_help`` keeps working.
from ui_help_data import CONTEXTUAL_HELP_MAP, HELP_SECTIONS  # noqa: F401




def _section_titles():
    """All Help tab titles in the order they appear in the notebook."""
    return tuple(title for title, _intro, _body in HELP_SECTIONS)


def _configure_help_text_tags(body):
    """Install the tag palette the parser below writes against."""
    base_family = "Segoe UI"
    body.tag_configure(
        "heading1",
        foreground=_HELP_HEADING1,
        font=(base_family, 13, "bold"),
        spacing1=10,
        spacing3=4,
    )
    body.tag_configure(
        "heading2",
        foreground=_HELP_HEADING2,
        font=(base_family, 11, "bold"),
        spacing1=8,
        spacing3=2,
    )
    body.tag_configure(
        "bullet",
        foreground=_HELP_BULLET,
        font=(base_family, 10, "bold"),
    )
    body.tag_configure(
        "code",
        background=_HELP_CODE_BG,
        foreground=_HELP_CODE_FG,
        font=("Consolas", 10),
    )
    body.tag_configure(
        "body",
        foreground=_HELP_FG,
        font=(base_family, 10),
        spacing1=2,
        spacing3=2,
        lmargin1=4,
        lmargin2=4,
    )
    body.tag_configure(
        "match",
        background=_HELP_MATCH_BG,
        foreground="#ffffff",
    )


# Body-text line styles:
#   "# Heading 1"      → large purple heading
#   "## Heading 2"     → medium purple heading
#   Lines that START with "- " or "* "  → bullet (first two chars tagged)
#   Backtick-wrapped words (`like_this`) → inline code style
# Everything else is body.  This format matches how HELP_SECTIONS bodies
# are already written today — the old plain-text dump rendered them as
# flat text; the new renderer just adds tags without asking the content
# to change.  Section bodies that *don't* start their top line with a
# "# " heading get one synthesized from the section title so every
# section has a clear visual top.
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")


def _render_help_body(body, title, body_text):
    """Write *body_text* into *body* with styled tags.

    The first line is checked for a leading "# " / "## " marker; if
    absent, the section title is promoted to a heading1 so every
    section has a visual anchor the search highlight can land on.
    """
    lines = (body_text or "").split("\n")
    if not lines or not lines[0].lstrip().startswith("#"):
        body.insert("end", f"{title}\n", "heading1")

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("## "):
            body.insert("end", stripped[3:] + "\n", "heading2")
            continue
        if stripped.startswith("# "):
            body.insert("end", stripped[2:] + "\n", "heading1")
            continue
        if stripped.startswith("- ") or stripped.startswith("* "):
            indent = line[: len(line) - len(stripped)]
            body.insert("end", indent, "body")
            body.insert("end", stripped[:2], "bullet")
            _insert_inline("body", body, stripped[2:] + "\n")
            continue
        _insert_inline("body", body, line + "\n")


def _insert_inline(default_tag, body, text):
    """Insert *text* with inline `code` spans picked out in their own tag."""
    pos = 0
    for match in _INLINE_CODE_RE.finditer(text):
        if match.start() > pos:
            body.insert("end", text[pos:match.start()], default_tag)
        body.insert("end", match.group(1), "code")
        pos = match.end()
    if pos < len(text):
        body.insert("end", text[pos:], default_tag)


def _highlight_matches(body, needle):
    """Apply the `match` tag to every occurrence of *needle* in *body*.

    Clears any prior `match` tags first.  Returns the 1-based line
    number of the first match (so the caller can scroll it into view)
    or 0 when there are no matches.
    """
    body.tag_remove("match", "1.0", "end")
    if not needle:
        return 0
    first_line = 0
    start = "1.0"
    needle_len = len(needle)
    while True:
        pos = body.search(needle, start, stopindex="end", nocase=True)
        if not pos:
            break
        end = f"{pos}+{needle_len}c"
        body.tag_add("match", pos, end)
        if first_line == 0:
            first_line = int(pos.split(".")[0])
        start = end
    return first_line


def _build_help_page(parent, title, intro, body_text):
    page = ttk.Frame(parent, padding=12)
    ttk.Label(page, text=intro, style="SubHeader.TLabel", wraplength=900, justify="left").pack(anchor="w", pady=(0, 8))

    body_frame = ttk.Frame(page)
    body_frame.pack(fill=tk.BOTH, expand=True)

    body = tk.Text(
        body_frame,
        wrap="word",
        height=28,
        padx=12,
        pady=12,
        relief="flat",
        borderwidth=0,
        background=_HELP_BG,
        foreground=_HELP_FG,
        insertbackground=_HELP_FG,
        selectbackground=_HELP_MATCH_BG,
        cursor="arrow",
    )
    body.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    scroll = ttk.Scrollbar(body_frame, orient="vertical", command=body.yview)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)
    body.configure(yscrollcommand=scroll.set)
    attach_vertical_mousewheel(body)

    _configure_help_text_tags(body)
    _render_help_body(body, title, body_text)
    body.configure(state="disabled")
    page._help_body_widget = body  # referenced by the search driver
    page._help_body_text = body_text
    page._help_title = title
    return page


def _apply_help_search(notebook, pages, needle):
    """Highlight matches across every help page and focus the first hit.

    Returns a (total_matches, total_hit_pages) tuple so the search bar
    can show a count.
    """
    total = 0
    hit_pages = 0
    first_hit_index = None
    for idx, page in enumerate(pages):
        body = page._help_body_widget
        body.configure(state="normal")
        first_line = _highlight_matches(body, needle)
        body.configure(state="disabled")
        # Count the matches on this page.
        range_count = 0
        pos = "1.0"
        while True:
            match_start = body.tag_nextrange("match", pos)
            if not match_start:
                break
            range_count += 1
            pos = match_start[1]
        total += range_count
        if range_count:
            hit_pages += 1
            if first_hit_index is None:
                first_hit_index = idx
                body.see(f"{first_line}.0")
    if first_hit_index is not None and needle:
        try:
            notebook.select(first_hit_index)
        except tk.TclError:
            pass
    return total, hit_pages


def build_help_tab(app):
    frame = ttk.Frame(app.notebook, padding=16)
    app.notebook.add(frame, text="  Help  ")

    ttk.Label(frame, text="Help", style="Header.TLabel").pack(anchor="w")
    ttk.Label(
        frame,
        text="Reference for reports, calculations, controls, maintenance behavior, and common troubleshooting steps.",
        style="SubHeader.TLabel",
        wraplength=900,
    ).pack(anchor="w", pady=(2, 10))
    ttk.Label(
        frame,
        text="UX rule: no new required field unless the app cannot infer or default it safely, and no new prompt unless different user choices materially change the outcome.",
        style="Info.TLabel",
        wraplength=900,
    ).pack(anchor="w", pady=(0, 10))

    settings_frame = ttk.LabelFrame(frame, text="Workflow Defaults", padding=10)
    settings_frame.pack(fill=tk.X, pady=(0, 10))
    ttk.Label(
        settings_frame,
        text="Mixed immediate/planned export behavior:",
        style="Info.TLabel",
    ).pack(side=tk.LEFT, padx=(0, 8))
    behavior_map = {
        "all_exportable": "Export All Exportable",
        "immediate_only": "Immediate Only",
        "ask_when_mixed": "Ask When Mixed",
    }
    reverse_behavior_map = {label: key for key, label in behavior_map.items()}
    var_mixed_export = tk.StringVar(value=behavior_map.get(app._get_mixed_export_behavior(), "Export All Exportable"))
    combo_mixed_export = ttk.Combobox(
        settings_frame,
        textvariable=var_mixed_export,
        state="readonly",
        width=24,
        values=list(behavior_map.values()),
    )
    combo_mixed_export.pack(side=tk.LEFT)
    combo_mixed_export.bind(
        "<<ComboboxSelected>>",
        lambda _e: app._set_mixed_export_behavior(reverse_behavior_map.get(var_mixed_export.get(), "all_exportable")),
    )

    ttk.Label(
        settings_frame,
        text="Planned-only export behavior:",
        style="Info.TLabel",
    ).pack(side=tk.LEFT, padx=(18, 8))
    planned_only_map = {
        "export_automatically": "Export Automatically",
        "ask_before_export": "Ask Before Export",
    }
    reverse_planned_only_map = {label: key for key, label in planned_only_map.items()}
    var_planned_only = tk.StringVar(
        value=planned_only_map.get(app._get_planned_only_export_behavior(), "Export Automatically")
    )
    combo_planned_only = ttk.Combobox(
        settings_frame,
        textvariable=var_planned_only,
        state="readonly",
        width=22,
        values=list(planned_only_map.values()),
    )
    combo_planned_only.pack(side=tk.LEFT)
    combo_planned_only.bind(
        "<<ComboboxSelected>>",
        lambda _e: app._set_planned_only_export_behavior(
            reverse_planned_only_map.get(var_planned_only.get(), "export_automatically")
        ),
    )

    ttk.Label(
        settings_frame,
        text="Review & Export default focus:",
        style="Info.TLabel",
    ).pack(side=tk.LEFT, padx=(18, 8))
    focus_map = {
        "all_items": "All Items",
        "exceptions_only": "Exceptions Only",
    }
    reverse_focus_map = {label: key for key, label in focus_map.items()}
    var_review_focus = tk.StringVar(value=focus_map.get(app._get_review_export_focus(), "Exceptions Only"))
    combo_review_focus = ttk.Combobox(
        settings_frame,
        textvariable=var_review_focus,
        state="readonly",
        width=18,
        values=list(focus_map.values()),
    )
    combo_review_focus.pack(side=tk.LEFT)
    combo_review_focus.bind(
        "<<ComboboxSelected>>",
        lambda _e: app._set_review_export_focus(reverse_focus_map.get(var_review_focus.get(), "exceptions_only")),
    )

    ttk.Label(
        settings_frame,
        text="Default vendor shipping preset:",
        style="Info.TLabel",
    ).pack(side=tk.LEFT, padx=(18, 8))
    preset_options = shipping_flow.vendor_policy_preset_options()
    preset_map = {"": "No Default"}
    preset_map.update({key: label for key, label in preset_options})
    reverse_preset_map = {label: key for key, label in preset_map.items()}
    var_vendor_preset = tk.StringVar(value=preset_map.get(app._get_default_vendor_policy_preset(), "No Default"))
    combo_vendor_preset = ttk.Combobox(
        settings_frame,
        textvariable=var_vendor_preset,
        state="readonly",
        width=24,
        values=list(preset_map.values()),
    )
    combo_vendor_preset.pack(side=tk.LEFT)
    combo_vendor_preset.bind(
        "<<ComboboxSelected>>",
        lambda _e: app._set_default_vendor_policy_preset(reverse_preset_map.get(var_vendor_preset.get(), "")),
    )

    ttk.Label(
        settings_frame,
        text="Remove-not-needed default:",
        style="Info.TLabel",
    ).pack(side=tk.LEFT, padx=(18, 8))
    remove_scope_map = {
        "unassigned_only": "Unassigned Only",
        "include_assigned": "Include Assigned",
    }
    reverse_remove_scope_map = {label: key for key, label in remove_scope_map.items()}
    var_remove_scope = tk.StringVar(
        value=remove_scope_map.get(app._get_remove_not_needed_scope(), "Unassigned Only")
    )
    combo_remove_scope = ttk.Combobox(
        settings_frame,
        textvariable=var_remove_scope,
        state="readonly",
        width=18,
        values=list(remove_scope_map.values()),
    )
    combo_remove_scope.pack(side=tk.LEFT)
    combo_remove_scope.bind(
        "<<ComboboxSelected>>",
        lambda _e: app._set_remove_not_needed_scope(
            reverse_remove_scope_map.get(var_remove_scope.get(), "unassigned_only")
        ),
    )

    ttk.Label(
        frame,
        text=(
            "Recommended routine path: keep Review & Export on Exceptions Only, use Release Plan for vendor timing decisions, "
            "save export defaults so the common path stays one-click, and use a default vendor shipping preset only when "
            "most unconfigured vendors should follow the same rule."
        ),
        style="Info.TLabel",
        wraplength=920,
        justify="left",
    ).pack(anchor="w", pady=(0, 10))

    # ── Search bar ──
    search_frame = ttk.Frame(frame)
    search_frame.pack(fill=tk.X, pady=(0, 8))
    ttk.Label(search_frame, text="Search help:").pack(side=tk.LEFT, padx=(0, 4))
    app.var_help_search = tk.StringVar(value="")
    entry_help_search = ttk.Entry(search_frame, textvariable=app.var_help_search, width=40)
    entry_help_search.pack(side=tk.LEFT, padx=(0, 8))
    lbl_help_search_status = ttk.Label(search_frame, text="", style="Info.TLabel")
    lbl_help_search_status.pack(side=tk.LEFT)

    def _clear_search():
        app.var_help_search.set("")

    ttk.Button(search_frame, text="Clear", command=_clear_search).pack(side=tk.LEFT, padx=(8, 0))

    help_notebook = ttk.Notebook(frame)
    help_notebook.pack(fill=tk.BOTH, expand=True)

    help_pages = []
    for title, intro, body_text in HELP_SECTIONS:
        page = _build_help_page(help_notebook, title, intro, body_text)
        help_notebook.add(page, text=f"  {title}  ")
        help_pages.append(page)

    # Expose the pages and notebook so contextual-help callers (and
    # future Help-tab integrations) can jump to a specific section
    # without reaching into build_help_tab internals.
    app._help_notebook = help_notebook
    app._help_pages = help_pages

    def _on_search_change(*_args):
        needle = str(app.var_help_search.get() or "").strip()
        total, hit_pages = _apply_help_search(help_notebook, help_pages, needle)
        if not needle:
            lbl_help_search_status.config(text="")
        elif total == 0:
            lbl_help_search_status.config(text="No matches")
        else:
            suffix = "" if hit_pages == 1 else "s"
            lbl_help_search_status.config(text=f"{total} match(es) on {hit_pages} page{suffix}")

    app.var_help_search.trace_add("write", _on_search_change)


def build_context_help_button(parent, app, context_key, *, text="?", width=2):
    """Return a tiny '?' button that jumps the Help tab to *context_key*.

    Callers place the button next to confusing controls (Reorder Cycle,
    Acceptable Overstock, etc.).  Pure ttk so it inherits the theme.
    The factory returns the widget so the caller can .pack/.grid it
    however they like — this helper never lays out its own button.
    """
    return ttk.Button(
        parent,
        text=text,
        width=width,
        command=lambda: open_help_for(app, context_key),
    )


def focus_help_section(app, section_title):
    """Switch the Help notebook to *section_title* and raise the Help tab.

    Silently ignored if the Help tab hasn't been built yet (should never
    happen in the real app — build_help_tab runs during startup).
    """
    notebook = getattr(app, "_help_notebook", None)
    pages = getattr(app, "_help_pages", None) or []
    if notebook is None or not pages:
        return False
    for idx, page in enumerate(pages):
        if getattr(page, "_help_title", "") == section_title:
            try:
                notebook.select(idx)
            except tk.TclError:
                return False
            # Also raise the Help tab on the outer app notebook.
            outer = getattr(app, "notebook", None)
            if outer is not None:
                help_frame = notebook.master
                for tab_id in outer.tabs():
                    try:
                        if outer.nametowidget(tab_id) is help_frame:
                            outer.select(tab_id)
                            break
                    except tk.TclError:
                        continue
            return True
    return False


def open_help_for(app, context_key):
    """Jump to the Help section registered for *context_key*.

    Callers pass a short stable identifier (e.g. `"reorder_cycle"`);
    the CONTEXTUAL_HELP_MAP resolves it to the section title.  Falls
    back to the first section when the key isn't registered so the
    operator always lands somewhere useful.
    """
    title = CONTEXTUAL_HELP_MAP.get(context_key)
    if title is None and HELP_SECTIONS:
        title = HELP_SECTIONS[0][0]
    if title is None:
        return False
    return focus_help_section(app, title)
