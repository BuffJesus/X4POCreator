import tkinter as tk
from tkinter import ttk, messagebox, simpledialog


def open_vendor_manager(app):
    dlg = tk.Toplevel(app.root)
    dlg.title("Vendor Manager")
    dlg.configure(bg="#1e1e2e")
    dlg.transient(app.root)
    dlg.grab_set()

    ttk.Label(dlg, text="Vendor Manager", style="Header.TLabel").pack(anchor="w", padx=16, pady=(16, 4))
    ttk.Label(
        dlg,
        text=(
            "Add, rename, or remove vendor codes used by the app. "
            "Renaming a vendor also updates matching vendor assignments in the current session."
        ),
        style="SubHeader.TLabel",
        wraplength=680,
    ).pack(anchor="w", padx=16, pady=(0, 10))

    list_frame = ttk.Frame(dlg)
    list_frame.pack(fill=tk.BOTH, expand=True, padx=16)

    vendor_list = tk.Listbox(
        list_frame,
        activestyle="none",
        exportselection=False,
        width=36,
        height=18,
        bg="#1f2330",
        fg="#f4f4f6",
        selectbackground="#5b4cc4",
        selectforeground="#ffffff",
        relief="flat",
        highlightthickness=0,
    )
    vendor_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=vendor_list.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    vendor_list.configure(yscrollcommand=scrollbar.set)

    def _refresh(selected_code=None):
        current = selected_code
        if current is None:
            selection = vendor_list.curselection()
            if selection:
                current = vendor_list.get(selection[0])
        vendor_list.delete(0, tk.END)
        for code in app.vendor_codes_used:
            vendor_list.insert(tk.END, code)
        if current:
            try:
                idx = app.vendor_codes_used.index(current)
            except ValueError:
                idx = None
            if idx is not None:
                vendor_list.selection_set(idx)
                vendor_list.see(idx)

    def _selected_vendor():
        selection = vendor_list.curselection()
        if not selection:
            return ""
        return vendor_list.get(selection[0])

    def _add():
        value = simpledialog.askstring("Add Vendor", "Enter the new vendor code:", parent=dlg)
        if value is None:
            return
        normalized = app._remember_vendor_code(value)
        if not normalized:
            messagebox.showinfo("Invalid Vendor", "Enter a vendor code before saving.", parent=dlg)
            return
        _refresh(normalized)

    def _edit():
        current = _selected_vendor()
        if not current:
            messagebox.showinfo("Select Vendor", "Select a vendor to rename first.", parent=dlg)
            return
        value = simpledialog.askstring("Rename Vendor", "Enter the updated vendor code:", initialvalue=current, parent=dlg)
        if value is None:
            return
        renamed = app._rename_vendor_code(current, value)
        if not renamed:
            messagebox.showinfo("Invalid Vendor", "Enter a vendor code before saving.", parent=dlg)
            return
        _refresh(renamed)

    def _remove():
        current = _selected_vendor()
        if not current:
            messagebox.showinfo("Select Vendor", "Select a vendor to remove first.", parent=dlg)
            return
        if not messagebox.askyesno(
            "Remove Vendor",
            (
                f"Remove vendor '{current}' from the saved vendor list?\n\n"
                "This does not clear existing vendor assignments already on rows."
            ),
            parent=dlg,
        ):
            return
        app._remove_vendor_code(current)
        _refresh()

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(fill=tk.X, padx=16, pady=12)
    action_row = ttk.Frame(btn_frame)
    action_row.pack(anchor="w", fill=tk.X)
    ttk.Button(action_row, text="Add", command=_add).pack(side=tk.LEFT, padx=4)
    ttk.Button(action_row, text="Rename", command=_edit).pack(side=tk.LEFT, padx=4)
    ttk.Button(action_row, text="Remove", command=_remove).pack(side=tk.LEFT, padx=4)

    close_row = ttk.Frame(btn_frame)
    close_row.pack(anchor="e", fill=tk.X, pady=(8, 0))
    ttk.Button(close_row, text="Close", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)

    _refresh()
    app._autosize_dialog(dlg, min_w=520, min_h=420, max_w_ratio=0.75, max_h_ratio=0.8)
    dlg.wait_window()
