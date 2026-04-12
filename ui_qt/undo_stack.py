"""Simple undo/redo stack for bulk grid edits.

Each entry is a snapshot of the affected items before the edit.
On undo, the current state is pushed to the redo stack and the
snapshot is restored.  On redo, the reverse happens.

This is deliberately simpler than the tkinter build's
``session_state_flow`` history mechanism — it captures full item
dicts rather than per-field deltas.  For the 63K-item dataset,
each snapshot is the set of *changed* items only (not the full
list), so memory stays bounded.
"""

from __future__ import annotations

import copy
from typing import Optional


MAX_UNDO_DEPTH = 50


class UndoEntry:
    __slots__ = ("label", "item_snapshots", "removed_items", "removed_indices")

    def __init__(self, label: str, item_snapshots: dict | None = None,
                 removed_items: list | None = None, removed_indices: list | None = None):
        self.label = label
        # {row_index: deep_copy_of_item_before_edit}
        self.item_snapshots = item_snapshots or {}
        # For removal operations: list of (index, item_copy) pairs
        self.removed_items = removed_items or []
        self.removed_indices = removed_indices or []


class BulkUndoStack:
    """Undo/redo stack for the bulk grid."""

    def __init__(self):
        self._undo: list[UndoEntry] = []
        self._redo: list[UndoEntry] = []

    def can_undo(self) -> bool:
        return len(self._undo) > 0

    def can_redo(self) -> bool:
        return len(self._redo) > 0

    @property
    def undo_label(self) -> str:
        return self._undo[-1].label if self._undo else ""

    @property
    def redo_label(self) -> str:
        return self._redo[-1].label if self._redo else ""

    def clear(self):
        self._undo.clear()
        self._redo.clear()

    # ── Capture + push ────────────────────────────────────────────

    def push_edit(self, label: str, items_list: list, affected_rows: list[int]):
        """Capture before-state of affected rows and push an undo entry."""
        snapshots = {}
        for row in affected_rows:
            if 0 <= row < len(items_list):
                snapshots[row] = copy.deepcopy(items_list[row])
        if not snapshots:
            return
        self._undo.append(UndoEntry(label, item_snapshots=snapshots))
        if len(self._undo) > MAX_UNDO_DEPTH:
            self._undo.pop(0)
        self._redo.clear()

    def push_removal(self, label: str, removed_pairs: list[tuple[int, dict]]):
        """Capture a row removal for undo."""
        if not removed_pairs:
            return
        indices = [idx for idx, _ in removed_pairs]
        items = [copy.deepcopy(item) for _, item in removed_pairs]
        self._undo.append(UndoEntry(
            label,
            removed_items=items,
            removed_indices=indices,
        ))
        if len(self._undo) > MAX_UNDO_DEPTH:
            self._undo.pop(0)
        self._redo.clear()

    # ── Undo / Redo ───────────────────────────────────────────────

    def undo(self, items_list: list) -> Optional[UndoEntry]:
        """Undo the last action.  Returns the entry that was undone, or None."""
        if not self._undo:
            return None
        entry = self._undo.pop()

        if entry.removed_items:
            # Undo a removal: re-insert the items at their original indices
            current_snapshots = {}  # For redo: capture what's at those positions now
            for idx, item in sorted(zip(entry.removed_indices, entry.removed_items)):
                items_list.insert(idx, item)
            self._redo.append(UndoEntry(
                entry.label,
                removed_items=entry.removed_items,
                removed_indices=entry.removed_indices,
            ))
            return entry

        if entry.item_snapshots:
            # Undo an edit: swap current items with snapshots
            redo_snapshots = {}
            for row, old_item in entry.item_snapshots.items():
                if 0 <= row < len(items_list):
                    redo_snapshots[row] = copy.deepcopy(items_list[row])
                    items_list[row] = old_item
            self._redo.append(UndoEntry(entry.label, item_snapshots=redo_snapshots))
            return entry

        return None

    def redo(self, items_list: list) -> Optional[UndoEntry]:
        """Redo the last undone action.  Returns the entry, or None."""
        if not self._redo:
            return None
        entry = self._redo.pop()

        if entry.removed_items:
            # Redo a removal: remove the items again
            for idx in sorted(entry.removed_indices, reverse=True):
                if 0 <= idx < len(items_list):
                    items_list.pop(idx)
            self._undo.append(UndoEntry(
                entry.label,
                removed_items=entry.removed_items,
                removed_indices=entry.removed_indices,
            ))
            return entry

        if entry.item_snapshots:
            # Redo an edit: swap again
            undo_snapshots = {}
            for row, new_item in entry.item_snapshots.items():
                if 0 <= row < len(items_list):
                    undo_snapshots[row] = copy.deepcopy(items_list[row])
                    items_list[row] = new_item
            self._undo.append(UndoEntry(entry.label, item_snapshots=undo_snapshots))
            return entry

        return None
