"""
Excel / Spreadsheet Editor for WhatsApp Automation
Powered by tksheet (https://github.com/ragardner/tksheet)
Allows users to directly view, add, paste numbers, edit cells, and save Excel (.xlsx) / CSV files
without needing Microsoft Excel installed!
"""

import os
import re
import csv
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from typing import Callable, Optional, List

try:
    from tksheet import Sheet
    TKSHEET_AVAILABLE = True
except ImportError:
    TKSHEET_AVAILABLE = False


class ExcelEditorDialog(tk.Toplevel):
    DEFAULT_HEADERS = ["Phone", "Name", "Message", "Attachment"]

    def __init__(self, parent, current_file: Optional[str] = None, on_saved_callback: Optional[Callable[[str, int], None]] = None):
        super().__init__(parent)
        self.title("Built-in Excel & Contact Editor")
        self.geometry("920x620")
        self.minsize(750, 500)

        self.parent = parent
        self.current_file = current_file
        self.on_saved_callback = on_saved_callback
        self.is_modified = False

        self._build_ui()
        if self.current_file and os.path.isfile(self.current_file):
            self.load_file(self.current_file)
        else:
            self._load_blank_template()

    def _build_ui(self):
        # Top Toolbar
        toolbar = ttk.Frame(self, padding="10 8 10 6")
        toolbar.pack(fill="x")

        # File actions
        ttk.Button(toolbar, text="📂 Open File...", command=self._action_open_file).pack(side="left", padx=2)
        ttk.Button(toolbar, text="💾 Save & Use", command=self._action_save).pack(side="left", padx=2)
        ttk.Button(toolbar, text="💾 Save As...", command=self._action_save_as).pack(side="left", padx=2)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)

        # Row actions
        ttk.Button(toolbar, text="➕ Add Row", command=self.add_row).pack(side="left", padx=2)
        ttk.Button(toolbar, text="➖ Delete Row", command=self.delete_selected_rows).pack(side="left", padx=2)
        ttk.Button(toolbar, text="📋 Quick Paste Numbers", command=self.open_quick_paste_dialog).pack(side="left", padx=2)
        ttk.Button(toolbar, text="🧹 Clear", command=self._action_clear).pack(side="left", padx=2)

        # Quick tip label on right
        ttk.Label(toolbar, text="💡 Double-click any cell to edit | Ctrl+C / Ctrl+V supported", font=("Segoe UI", 8), foreground="#555").pack(side="right", padx=5)

        # Main Sheet Container
        self.sheet_container = ttk.Frame(self)
        self.sheet_container.pack(fill="both", expand=True, padx=10, pady=5)

        if TKSHEET_AVAILABLE:
            self.sheet = Sheet(
                self.sheet_container,
                headers=self.DEFAULT_HEADERS,
                show_row_index=True,
                show_top_left=True,
                empty_horizontal=0,
                empty_vertical=0
            )
            self.sheet.enable_bindings(
                "single_select",
                "drag_select",
                "select_all",
                "column_select",
                "row_select",
                "column_width_resize",
                "double_click_column_resize",
                "row_height_resize",
                "arrowkeys",
                "row_drag_and_drop",
                "column_drag_and_drop",
                "right_click_popup_menu",
                "rc_select",
                "rc_insert_column",
                "rc_delete_column",
                "rc_insert_row",
                "rc_delete_row",
                "copy",
                "cut",
                "paste",
                "delete",
                "undo",
                "edit_cell"
            )
            self.sheet.pack(fill="both", expand=True)
            self.sheet.set_options(auto_resize_columns=120)
        else:
            lbl_err = ttk.Label(self.sheet_container, text="tksheet is not installed. Please run 'pip install tksheet'", font=("Segoe UI", 11), foreground="red")
            lbl_err.pack(expand=True)

        # Bottom Status Bar
        self.status_bar = ttk.Frame(self, padding="10 4 10 6")
        self.status_bar.pack(fill="x")
        self.status_lbl = ttk.Label(self.status_bar, text="Ready.", font=("Segoe UI", 9))
        self.status_lbl.pack(side="left")
        self.row_count_lbl = ttk.Label(self.status_bar, text="Rows: 0", font=("Segoe UI", 9, "bold"))
        self.row_count_lbl.pack(side="right")

    def _load_blank_template(self):
        if not TKSHEET_AVAILABLE:
            return
        initial_rows = [
            ["+919876543210", "Alex Mercer", "Hello {name}, your scheduled notification is ready.", ""],
            ["+14155552671", "Sarah Connor", "Hi {name}, thank you for connecting with us!", ""],
            ["", "", "", ""],
            ["", "", "", ""],
            ["", "", "", ""],
        ]
        self.sheet.headers(self.DEFAULT_HEADERS)
        self.sheet.set_sheet_data(initial_rows)
        self._update_status("Loaded blank template with sample columns.")

    def load_file(self, file_path: str):
        if not TKSHEET_AVAILABLE or not os.path.isfile(file_path):
            return

        ext = os.path.splitext(file_path)[1].lower()
        rows = []
        headers = []

        try:
            if ext in (".xlsx", ".xls"):
                import openpyxl
                wb = openpyxl.load_workbook(file_path, data_only=True)
                sheet = wb.active
                data_iter = sheet.iter_rows(values_only=True)
                raw_headers = next(data_iter, None)
                if raw_headers:
                    headers = [str(h) if h is not None else f"Column {i+1}" for i, h in enumerate(raw_headers)]
                    for r in data_iter:
                        if r and any(r):
                            rows.append([str(v) if v is not None else "" for v in r])

            elif ext == ".csv":
                with open(file_path, "r", encoding="utf-8-sig", errors="ignore") as f:
                    reader = csv.reader(f)
                    headers = next(reader, None)
                    for r in reader:
                        if r and any(r):
                            rows.append(r)

            if not headers:
                headers = self.DEFAULT_HEADERS
            if not rows:
                rows = [["", "", "", ""]]

            # Pad rows to header count
            for r in rows:
                while len(r) < len(headers):
                    r.append("")

            self.sheet.headers(headers)
            self.sheet.set_sheet_data(rows)
            self.current_file = file_path
            self._update_status(f"Loaded: {os.path.basename(file_path)}")

        except Exception as e:
            messagebox.showerror("Error Opening File", f"Failed to load {file_path}:\n{e}")

    def add_row(self):
        if not TKSHEET_AVAILABLE:
            return
        headers = self.sheet.headers()
        empty_row = ["" for _ in range(len(headers) if headers else 4)]
        self.sheet.insert_row(row=empty_row)
        self._update_status("Added new row.")

    def delete_selected_rows(self):
        if not TKSHEET_AVAILABLE:
            return
        selected = self.sheet.get_selected_rows()
        if not selected:
            # Delete last row if none selected
            total = self.sheet.get_total_rows()
            if total > 0:
                self.sheet.delete_row(total - 1)
        else:
            for r in sorted(selected, reverse=True):
                self.sheet.delete_row(r)
        self._update_status("Deleted row(s).")

    def _action_open_file(self):
        f = filedialog.askopenfilename(
            parent=self,
            title="Open Excel or CSV File",
            filetypes=[("Excel & CSV Files", "*.xlsx;*.xls;*.csv"), ("Excel Files", "*.xlsx;*.xls"), ("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        if f:
            self.load_file(f)

    def _action_save(self):
        if self.current_file:
            self._save_to_path(self.current_file)
        else:
            self._action_save_as()

    def _action_save_as(self):
        f = filedialog.asksaveasfilename(
            parent=self,
            title="Save Spreadsheet As",
            defaultextension=".xlsx",
            filetypes=[("Excel Workbook (*.xlsx)", "*.xlsx"), ("CSV (Comma Delimited) (*.csv)", "*.csv")]
        )
        if f:
            self.current_file = f
            self._save_to_path(f)

    def _save_to_path(self, file_path: str):
        if not TKSHEET_AVAILABLE:
            return

        headers = self.sheet.headers()
        data = self.sheet.get_sheet_data()

        # Clean empty trailing rows
        clean_rows = []
        for r in data:
            if any(str(cell).strip() for cell in r):
                clean_rows.append([str(cell).strip() for cell in r])

        if not clean_rows:
            messagebox.showwarning("Empty Sheet", "There are no contacts to save!", parent=self)
            return

        ext = os.path.splitext(file_path)[1].lower()

        try:
            if ext == ".csv":
                with open(file_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                    writer.writerows(clean_rows)

            elif ext in (".xlsx", ".xls"):
                import openpyxl
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "Contacts"
                ws.append(headers)
                for r in clean_rows:
                    ws.append(r)
                wb.save(file_path)

            self.current_file = file_path
            self._update_status(f"Saved {len(clean_rows)} rows to {os.path.basename(file_path)}.")
            messagebox.showinfo("Saved Successfully", f"Saved {len(clean_rows)} contacts to:\n{file_path}", parent=self)

            if self.on_saved_callback:
                self.on_saved_callback(file_path, len(clean_rows))

        except Exception as e:
            messagebox.showerror("Save Error", f"Could not save file:\n{e}", parent=self)

    def _action_clear(self):
        if messagebox.askyesno("Clear Sheet", "Are you sure you want to clear all data in the table?", parent=self):
            self._load_blank_template()

    def open_quick_paste_dialog(self):
        """Dialog to paste raw phone numbers (one per line) and automatically populate the spreadsheet."""
        dialog = tk.Toplevel(self)
        dialog.title("Quick Paste Numbers & Contacts")
        dialog.geometry("520x420")
        dialog.transient(self)

        ttk.Label(dialog, text="Paste Numbers or Contacts Below:", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=15, pady=(10, 4))
        ttk.Label(dialog, text="Formats accepted:\n • Just phone numbers: 9876543210 (one per line)\n • Phone and Name: 9876543210, John Doe", font=("Segoe UI", 8), foreground="#555").pack(anchor="w", padx=15)

        txt_box = tk.Text(dialog, height=12, font=("Segoe UI", 10))
        txt_box.pack(fill="both", expand=True, padx=15, pady=8)

        def do_import():
            content = txt_box.get("1.0", "end-1c").strip()
            if not content:
                dialog.destroy()
                return

            lines = content.splitlines()
            imported_count = 0

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                phone = ""
                name = ""

                if "," in line:
                    parts = line.split(",", 1)
                    phone = parts[0].strip()
                    name = parts[1].strip()
                elif "\t" in line:
                    parts = line.split("\t", 1)
                    phone = parts[0].strip()
                    name = parts[1].strip()
                else:
                    phone = line

                # Clean phone digits
                clean_p = re.sub(r"[^\d+]", "", phone)
                if clean_p:
                    self.sheet.insert_row(row=[clean_p, name, "", ""])
                    imported_count += 1

            self._update_status(f"Imported {imported_count} numbers from quick paste.")
            dialog.destroy()

        b_row = ttk.Frame(dialog)
        b_row.pack(fill="x", padx=15, pady=10)
        ttk.Button(b_row, text="Add to Sheet", command=do_import).pack(side="right", padx=5)
        ttk.Button(b_row, text="Cancel", command=dialog.destroy).pack(side="right")

    def _update_status(self, text: str):
        self.status_lbl.config(text=text)
        if TKSHEET_AVAILABLE:
            total = len([r for r in self.sheet.get_sheet_data() if any(r)])
            self.row_count_lbl.config(text=f"Rows: {total}")

