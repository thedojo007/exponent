"""
project_lookup.py

Always-on-top project code lookup for ERP voucher entry.
Type to filter by project name / customer / ERP code. Click a row (or press
Enter on the top match) to copy the ERP code to clipboard.

Usage:
    py project_lookup.py "path\to\ERP상_프로젝트_코드_및_지급_입금_계좌_정리.xlsx"

If no path is given, it looks for the xlsx in the same folder as this script.
"""

import sys
import glob
import os
import tkinter as tk
from tkinter import ttk
import openpyxl


def find_default_path():
    here = os.path.dirname(os.path.abspath(__file__))
    matches = glob.glob(os.path.join(here, "*프로젝트*코드*.xlsx"))
    return matches[0] if matches else None


def load_rows(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    rows = []
    for ws in wb.worksheets:
        if ws.title == "Sheet1":
            continue
        for row in ws.iter_rows(min_row=3, values_only=True):
            if row[1]:  # 미국법인용 코드 present
                rows.append({
                    "local_code": row[1] or "",
                    "erp_code": row[2] or "",
                    "project": row[3] or "",
                    "customer": row[4] or "",
                    "account": row[6] if len(row) > 6 else "",
                })
    return rows


class LookupApp:
    def __init__(self, root, rows):
        self.root = root
        self.rows = rows

        root.title("Project Lookup")
        root.attributes("-topmost", True)
        root.geometry("560x320")

        self.entry = tk.Entry(root, font=("Segoe UI", 13))
        self.entry.pack(fill="x", padx=8, pady=8)
        self.entry.bind("<KeyRelease>", self.on_key)
        self.entry.bind("<Return>", self.on_enter)
        self.entry.focus_set()

        columns = ("erp_code", "project", "customer", "account")
        self.tree = ttk.Treeview(root, columns=columns, show="headings", height=10)
        self.tree.heading("erp_code", text="ERP Code")
        self.tree.heading("project", text="Project")
        self.tree.heading("customer", text="Customer")
        self.tree.heading("account", text="Account")
        self.tree.column("erp_code", width=100)
        self.tree.column("project", width=230)
        self.tree.column("customer", width=100)
        self.tree.column("account", width=90)
        self.tree.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.tree.bind("<Double-1>", self.on_click)

        self.status = tk.Label(root, text="Type to search — click or Enter to copy ERP code",
                                fg="gray", anchor="w")
        self.status.pack(fill="x", padx=8, pady=(0, 6))

        self.refresh("")

    def search(self, query):
        q = query.lower().strip()
        if not q:
            return self.rows
        return [r for r in self.rows if
                q in str(r["project"]).lower() or
                q in str(r["customer"]).lower() or
                q in str(r["erp_code"]).lower() or
                q in str(r["local_code"]).lower()]

    def refresh(self, query):
        for item in self.tree.get_children():
            self.tree.delete(item)
        results = self.search(query)
        for r in results[:50]:
            self.tree.insert("", "end", values=(r["erp_code"], r["project"], r["customer"], r["account"]))
        self.status.config(text=f"{len(results)} match(es)")

    def on_key(self, event):
        self.refresh(self.entry.get())

    def copy_selected_or_top(self):
        selected = self.tree.selection()
        if selected:
            values = self.tree.item(selected[0], "values")
        else:
            children = self.tree.get_children()
            if not children:
                return
            values = self.tree.item(children[0], "values")
        erp_code = values[0]
        self.root.clipboard_clear()
        self.root.clipboard_append(erp_code)
        self.status.config(text=f"Copied: {erp_code}")

    def on_enter(self, event):
        self.copy_selected_or_top()

    def on_click(self, event):
        self.copy_selected_or_top()


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else find_default_path()
    if not path or not os.path.exists(path):
        print("Could not find the project code xlsx. Pass the path as an argument:")
        print('  py project_lookup.py "C:\\path\\to\\ERP상_프로젝트_코드.xlsx"')
        sys.exit(1)

    rows = load_rows(path)
    root = tk.Tk()
    LookupApp(root, rows)
    root.mainloop()


if __name__ == "__main__":
    main()