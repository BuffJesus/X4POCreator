# Release Notes — v0.8.0

**Date:** 2026-04-08

---

## Summary

v0.8.0 opens the v0.8.x UX modernization train with **Phase 1: Help
tab rebuild**.  The Help tab gains a live search box, syntax-styled
rendering (headings, bullets, inline code), and a contextual help
API that lets any control in the app open the Help tab jumped to
the right section.

1082 tests pass (13 new).

---

## What's new

### Help tab search

A new **Search help** entry field at the top of the Help tab
filters every page live as the operator types.  Matches are
highlighted with a purple background across *every* section
simultaneously, and the notebook auto-switches to the first section
that contains a hit.  The search is case-insensitive substring.

The header shows "N match(es) on M page(s)" or "No matches" so the
operator can tell whether their search hit before they start
scrolling.

### Tagged body rendering

The plain-text help bodies now render with four tag styles:

- `# Heading 1` — large PURPLE_BRIGHT heading
- `## Heading 2` — medium PURPLE heading
- `- bullet` / `* bullet` — bullets get a colored marker
- `` `inline code` `` — monospace amber on dark background

Section bodies that don't start with a `#` heading get one
synthesized from the section title, so every page has a visual
anchor that the search highlight can land on.

**Content is unchanged** — the renderer parses the existing plain
text.  No help content was rewritten for this release.

### Contextual help API

Two new public helpers in `ui_help.py`:

- `focus_help_section(app, section_title)` — jumps the Help
  notebook to a specific section title and raises the outer Help
  tab.
- `open_help_for(app, context_key)` — shorter form that resolves
  a short stable key (`"reorder_cycle"`, `"skip_filter"`, etc.)
  through `CONTEXTUAL_HELP_MAP` and lands the operator on the right
  section.  Falls back to the first section when the key is
  unknown so the operator always ends up somewhere useful.
- `build_context_help_button(parent, app, context_key)` — factory
  for tiny "?" buttons that wire straight to `open_help_for`.

The map covers 18 context keys today: ordering (reorder cycle,
history days, acceptable overstock, confirmed stocking), filters
(skip, no pack), dialogs (supplier map, vendor review, session
diff, session history, bulk remove not needed, shared data
folder), and every major tab topic (shortcuts, maintenance,
shipping & release, review & export, reports, troubleshooting).

Existing dialogs don't wire `?` buttons yet — the API is ready
and v0.8.1+ will add the buttons next to the controls that most
need them.

### Theming the help body

`tk.Text` now renders with the same dark background as the rest
of the app (`_HELP_BG = #252538`) instead of the default ttk
white/gray.  Cursor set to arrow so the body doesn't look editable.
Small thing, but the Help tab used to visually "float" on top of
the app — it now fits in.

---

## Architecture

`ui_help.py` gained four pure helper functions (testable without
a display via headless `tk.Tk()`):

- `_configure_help_text_tags(body)` — installs the tag palette.
- `_render_help_body(body, title, body_text)` — parses plain-text
  markers and writes tagged text.
- `_highlight_matches(body, needle)` — live search highlighter.
- `_apply_help_search(notebook, pages, needle)` — cross-page search
  driver that counts matches and focuses the first hit page.

Plus the three public helpers documented above.

`_build_help_page` now takes the section title so it can
synthesize a heading when the body doesn't start with `#`, and
stores the body widget + title on the page frame so the search
driver and contextual-help helper can find them.

The existing `tests/test_ui_help.py` content checks are unchanged.

---

## Test count

| Release | Tests |
|---------|-------|
| v0.7.7  |  1068 |
| v0.8.0  |  1082 |

14 new tests in `tests/test_ui_help.py`:

- `ContextualHelpMapTests` — every mapped key resolves to a real
  section
- `FocusHelpSectionTests` — not-built / unknown / matching
- `OpenHelpForTests` — mapped key routes correctly; unknown key
  falls back to the first section
- `RenderHelpBodyTests` — H1 / H2 tags, synthesized title,
  inline code spans, bullet markers
- `HighlightMatchesTests` — blank needle / all occurrences
  case-insensitive / no-match return

All five renderer tests use a real headless `tk.Tk()` root and
skip gracefully when no display is available (so CI doesn't
fail on a headless runner).

---

## Files changed

- `ui_help.py` — tagged renderer, search, contextual-help API
- `tests/test_ui_help.py` — 13 new regression tests + shared
  `_headless_tk_root` helper
- `app_version.py` — bumped to 0.8.0

---

## Roadmap status

This is the first release in the v0.8.x **UX modernization train**
sketched in the Phase 1-5 plan:

| Phase | Status |
|---|---|
| 1 — Help tab rebuild | ✓ closed (v0.8.0) |
| 2 — Bulk grid Excel/Sheets polish | planning (see below) |
| 3 — Toolbar icon consolidation | planning |
| 4 — Load tab polish | planning |
| 5 — Review tab readiness checklist | planning |

The operator also flagged two concrete items during v0.8.0
development that will shape the next releases:

- **Muscle-memory sheet gestures don't work** (e.g. clicking a
  column header to sort) — Phase 2 lead item.
- **Sheet actions are slow on the 8-year 59K-item dataset** —
  measured: filter change ~640ms, first paint ~775ms.  Phase 2
  perf work.
- **Per-item notes column** for operators who want to leave a
  note on a line before export — new Phase 2 item.

v0.8.1 will be the first bite of Phase 2 — concrete plan in the
next chat response.
