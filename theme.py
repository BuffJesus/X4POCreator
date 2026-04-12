"""Canonical design tokens for PO Builder.

One place that names every color, font size, spacing value, and corner
radius the app uses.  Surfaces across ``ui_*.py`` and the bulk sheet should
pull from these tokens instead of hard-coding hex literals so the palette
stays coherent as the UI evolves.

This module is ported from the Tuner app's ``cpp/app/theme.hpp`` token
system.  The palette values are copied verbatim so the two apps share a
visual grammar.  Tuner is a C++ Qt app; PO Builder is tkinter + ttkbootstrap
with the ``darkly`` theme as the baseline.  The composed stylesheet helpers
in the Tuner's theme.hpp don't port directly — CSS-style per-side borders
and rounded corners aren't native tkinter features — so the Tk-specific
helpers live in ``theme_tk.py``.  This file stays pure data so it can be
imported by headless test modules without a display.

Philosophy (see also: Tuner's ``docs/ux-design.md``):

- **No drift.** 5 background levels, 5 accents, 6 type sizes.  When you
  need something between two values, round to the nearer one rather than
  adding a new token.
- **Semantic naming.** Accents are named by intent (primary/ok/warning/
  danger/special) not by hue.  Code reads "accent_danger" (intent) rather
  than "#d65a5a" (choice), so the mapping from "urgent" → "red" happens in
  exactly one place.
- **Progressive disclosure.** The type scale has a clear hierarchy so
  visual weight tracks importance — reserve ``text_primary`` for the few
  headline values you want the eye to land on first.
"""

# ─── Background levels — darkest (outermost) → lightest (inset) ────────────

BG_DEEP     = "#0f1116"  # app shell, behind everything
BG_BASE     = "#14171e"  # tab content backdrop
BG_PANEL    = "#1a1d24"  # card / content container
BG_ELEVATED = "#20242c"  # header strip / hovered card
BG_INSET    = "#262a33"  # input field, inset cell, chip background


# ─── Borders and dividers ──────────────────────────────────────────────────

BORDER         = "#2f343d"  # primary 1px divider
BORDER_SOFT    = "#262a33"  # quiet internal divider
BORDER_ACCENT  = "#5a9ad6"  # focus / selection edge


# ─── Text hierarchy — loud → quiet ─────────────────────────────────────────

TEXT_PRIMARY   = "#e8edf5"  # titles, hero values
TEXT_SECONDARY = "#c9d1e0"  # body text
TEXT_MUTED     = "#8a93a6"  # labels, field names
TEXT_DIM       = "#6a7080"  # captions, separators
TEXT_INVERSE   = "#0f1116"  # text on bright chips


# ─── Semantic accents — exactly one per meaning ────────────────────────────
#
# Don't introduce new hues without a semantic reason.  If you need a "safe"
# color, ask what it means:
#   - primary  → informational, selection, default accent
#   - ok       → value inside healthy zone
#   - warning  → attention needed, not urgent
#   - danger   → urgent, at risk
#   - special  → derived / computed / rare distinctive highlight

ACCENT_PRIMARY = "#5a9ad6"  # blue
ACCENT_OK      = "#5ad687"  # green
ACCENT_WARNING = "#d6a55a"  # amber
ACCENT_DANGER  = "#d65a5a"  # red
ACCENT_SPECIAL = "#9a7ad6"  # purple — derived/computed


# Subtle fills for highlighted regions (row tints, staged-change backgrounds).
# These are dark versions of the semantic accents, designed to layer over
# the BG_BASE / BG_PANEL tier without washing out the foreground text.
FILL_OK_SOFT      = "#1e2a22"  # dark green tint
FILL_WARNING_SOFT = "#2a2520"  # dark amber tint
FILL_DANGER_SOFT  = "#2a1f1f"  # dark red tint
FILL_SKIP_SOFT    = "#1e1e1e"  # slightly darker than base — neutral "stepped back"
FILL_PRIMARY_SOFT = "#1c3a5e"  # blue-tinted dark fill (for selection highlight)


# ─── Type scale — pixel sizes ──────────────────────────────────────────────

FONT_MICRO   = 9   # edge labels, tiny captions
FONT_SMALL   = 10  # muted labels, dividers, chips
FONT_BODY    = 11  # body text
FONT_MEDIUM  = 12  # emphasised value, chip value
FONT_LABEL   = 13  # header label
FONT_HEADING = 16  # section heading
FONT_HERO    = 24  # hero value (totals, banners)


# ─── Spacing scale (pixels) ────────────────────────────────────────────────

SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24


# ─── Corner radius (tkinter can't do rounded corners on native widgets,
# but Canvas-based surfaces can still reference these for consistency) ─────

RADIUS_SM = 4
RADIUS_MD = 6
RADIUS_LG = 10


# ─── Zone lookup — maps a zone name string to the matching accent ──────────
#
# Used by surfaces that receive a status string ("ok" / "warning" / "danger")
# from a service layer and need to pick the matching accent color.

_ZONE_ACCENTS = {
    "ok":       ACCENT_OK,
    "healthy":  ACCENT_OK,
    "warning":  ACCENT_WARNING,
    "review":   ACCENT_WARNING,
    "danger":   ACCENT_DANGER,
    "critical": ACCENT_DANGER,
    "primary":  ACCENT_PRIMARY,
    "assigned": ACCENT_OK,
    "skip":     TEXT_DIM,
    "special":  ACCENT_SPECIAL,
}


def zone_accent(zone: str) -> str:
    """Return the accent color for ``zone``.

    Unknown zones fall back to ``ACCENT_PRIMARY`` so the surface is never
    unpainted.
    """
    return _ZONE_ACCENTS.get(str(zone or "").lower().strip(), ACCENT_PRIMARY)


_ZONE_FILLS = {
    "ok":       FILL_OK_SOFT,
    "healthy":  FILL_OK_SOFT,
    "assigned": FILL_OK_SOFT,
    "warning":  FILL_WARNING_SOFT,
    "review":   FILL_WARNING_SOFT,
    "danger":   FILL_DANGER_SOFT,
    "critical": FILL_DANGER_SOFT,
    "skip":     FILL_SKIP_SOFT,
}


def zone_fill(zone: str) -> str:
    """Return the subtle fill color for ``zone`` (used for row tints)."""
    return _ZONE_FILLS.get(str(zone or "").lower().strip(), BG_PANEL)
