import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk


class TreeGridEditor:
    """Reusable inline editor/navigation helper for ttk.Treeview grids."""

    def __init__(self, root, tree, editable_cols, get_widget, get_value, apply_value, refresh_row):
        self.root = root
        self.tree = tree
        self.editable_cols = tuple(editable_cols)
        self.get_widget = get_widget
        self.get_value = get_value
        self.apply_value = apply_value
        self.refresh_row = refresh_row
        self.active_col = self.editable_cols[0] if self.editable_cols else ""

    def remember_col(self, col_name):
        if col_name in self.editable_cols:
            self.active_col = col_name

    def move_active_col(self, direction):
        if not self.editable_cols:
            return
        current = self.active_col if self.active_col in self.editable_cols else self.editable_cols[0]
        idx = self.editable_cols.index(current)
        if direction == "Left" and idx > 0:
            idx -= 1
        elif direction == "Right" and idx < len(self.editable_cols) - 1:
            idx += 1
        self.active_col = self.editable_cols[idx]

    def visible_iids(self):
        return list(self.tree.get_children(""))

    def target_row_ids(self, row_id):
        selected = list(self.tree.selection())
        if len(selected) > 1 and row_id in selected:
            return selected
        return [row_id]

    def apply_to_targets(self, row_id, col_name, raw_value):
        targets = self.target_row_ids(row_id)
        for target_row in targets:
            self.apply_value(target_row, col_name, raw_value)
            self.refresh_row(target_row)
        if targets:
            self.tree.selection_set(targets)
            self.tree.focus(row_id)

    def autosize_column(self, col_name, heading_text="", min_width=40, max_width=520):
        font = tkfont.nametofont("TkDefaultFont")
        width = font.measure(str(heading_text or col_name)) + 28
        for row_id in self.visible_iids():
            try:
                cell_text = self.tree.set(row_id, col_name)
            except Exception:
                cell_text = ""
            width = max(width, font.measure(str(cell_text)) + 28)
        self.tree.column(col_name, width=max(min_width, min(max_width, width)))

    def adjacent_cell(self, row_id, col_name, direction):
        if col_name not in self.editable_cols:
            return None
        row_ids = self.visible_iids()
        if row_id not in row_ids:
            return None
        row_pos = row_ids.index(row_id)
        col_pos = self.editable_cols.index(col_name)
        delta = {
            "Left": (0, -1),
            "Right": (0, 1),
            "Up": (-1, 0),
            "Down": (1, 0),
        }.get(direction)
        if delta is None:
            return None
        next_row = row_pos + delta[0]
        next_col = col_pos + delta[1]
        if next_col < 0 or next_col >= len(self.editable_cols):
            return None
        if next_row < 0 or next_row >= len(row_ids):
            return None
        return row_ids[next_row], self.editable_cols[next_col]

    def open_editor(self, row_id, col_name):
        self.remember_col(col_name)
        if col_name not in self.editable_cols:
            return
        bbox = self.tree.bbox(row_id, col_name)
        if not bbox:
            return

        widget = self.get_widget(col_name)
        current_val = self.get_value(row_id, col_name)
        widget.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        if isinstance(widget, ttk.Combobox):
            widget.set(current_val)
        else:
            widget.insert(0, current_val)
        try:
            widget.select_range(0, tk.END)
        except Exception:
            pass
        widget.focus_set()

        def _close():
            if widget.winfo_exists():
                widget.destroy()

        def _save(e=None):
            self.apply_to_targets(row_id, col_name, widget.get().strip())
            _close()

        def _cancel(e=None):
            _close()

        def _save_and_move(direction):
            def _handler(e=None):
                target = self.adjacent_cell(row_id, col_name, direction)
                _save()
                if target:
                    next_row, next_col = target
                    self.tree.selection_set(next_row)
                    self.tree.focus(next_row)
                    self.tree.see(next_row)
                    self.root.after(1, lambda: self.open_editor(next_row, next_col))
                return "break"
            return _handler

        widget.bind("<Return>", _save)
        widget.bind("<Escape>", _cancel)
        widget.bind("<FocusOut>", _save)
        for direction in ("Left", "Right", "Up", "Down"):
            widget.bind(f"<{direction}>", _save_and_move(direction))

    def keyboard_edit(self):
        row_id = self.tree.focus() or next(iter(self.tree.selection()), "")
        if not row_id:
            return "break"
        self.open_editor(row_id, self.active_col)
        return "break"

    def horizontal_nav(self, direction):
        self.move_active_col(direction)
        return "break"
