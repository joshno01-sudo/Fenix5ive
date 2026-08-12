"""Supply list tab: on-hand stock, adjusted with + / - buttons."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional

from .. import inventory
from ..models import SupplyItem
from ..storage import Storage

BG = "#ffffff"
CARD_BG = "#fafafa"
LOW = "#c62828"
WARN = "#ef6c00"
OK = "#2e7d32"

CATEGORIES = ["Ink", "Toner", "Printhead", "Maintenance", "Media", "Parts", "Other"]


class SuppliesTab(ttk.Frame):
    def __init__(self, parent: tk.Misc, app):
        super().__init__(parent, padding=0)
        self.app = app
        self.storage: Storage = app.storage
        # Row widgets currently shown — ItemRows, or a single placeholder label.
        self._rows: list[tk.Widget] = []

        toolbar = ttk.Frame(self, padding=(12, 10))
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="Add item", command=self.add_item).pack(side="left")
        ttk.Button(toolbar, text="Edit", command=self.edit_selected).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Delete", command=self.delete_selected).pack(side="left", padx=(6, 0))
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(toolbar, text="Load starter list", command=self.seed_defaults).pack(side="left")
        ttk.Button(toolbar, text="Export CSV", command=self.export_csv).pack(side="left", padx=(6, 0))

        self.summary = ttk.Label(toolbar, text="")
        self.summary.pack(side="right")

        filter_bar = ttk.Frame(self, padding=(12, 0))
        filter_bar.pack(fill="x")
        ttk.Label(filter_bar, text="Show:").pack(side="left")
        self.filter_var = tk.StringVar(value="All printers")
        self.filter_combo = ttk.Combobox(
            filter_bar, textvariable=self.filter_var, state="readonly", width=24
        )
        self.filter_combo.pack(side="left", padx=(6, 0))
        self.filter_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        self.reorder_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            filter_bar,
            text="Only items at/below reorder point",
            variable=self.reorder_only,
            command=self.refresh,
        ).pack(side="left", padx=(14, 0))

        # Column headings
        heading = tk.Frame(self, bg="#efefef")
        heading.pack(fill="x", padx=12, pady=(10, 0))
        for text, width in (
            ("Item", 34),
            ("Part #", 14),
            ("Category", 12),
            ("Printer", 12),
            ("On hand", 20),
            ("Reorder at", 10),
        ):
            tk.Label(
                heading,
                text=text,
                bg="#efefef",
                font=("Segoe UI", 9, "bold"),
                width=width,
                anchor="w",
                padx=4,
                pady=6,
            ).pack(side="left")

        # Scrollable list
        container = tk.Frame(self, bg=BG)
        container.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.canvas = tk.Canvas(container, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind(
            "<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind(
            "<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width)
        )

        self.selected_id: Optional[int] = None
        self.refresh()

    # -- data --------------------------------------------------------------

    def refresh(self) -> None:
        options = ["All printers"] + [p.name for p in self.app.config.printers] + ["Shop stock"]
        self.filter_combo.configure(values=options)
        if self.filter_var.get() not in options:
            self.filter_var.set("All printers")

        items = self.storage.list_items()
        chosen = self.filter_var.get()
        if chosen == "Shop stock":
            items = [i for i in items if not i.printer_id]
        elif chosen != "All printers":
            printer = next((p for p in self.app.config.printers if p.name == chosen), None)
            if printer:
                items = [i for i in items if i.printer_id == printer.id]
        if self.reorder_only.get():
            items = [i for i in items if i.needs_reorder]

        for row in self._rows:
            row.destroy()
        self._rows = []

        if not items:
            placeholder = tk.Label(
                self.inner,
                text=(
                    "Nothing in the supply list yet.\n\n"
                    'Press "Load starter list" for the usual Latex 360 and LaserJet 4100 '
                    "consumables,\nor add items one at a time. Polling a printer also adds "
                    "whatever supplies it reports.\n\n"
                    "Use + and − to count what's on the shelf. Rows stay grey and quiet "
                    "until\nyou count them for the first time."
                ),
                bg=BG,
                fg="#777",
                font=("Segoe UI", 10),
                justify="center",
                pady=50,
            )
            placeholder.pack(fill="x")
            self._rows = [placeholder]
        else:
            for index, item in enumerate(items):
                row = ItemRow(self.inner, self, item, index)
                row.pack(fill="x")
                self._rows.append(row)

        stats = inventory.summarize(self.storage.list_items())
        self.summary.configure(
            text=(
                f"{stats['total_rows']} items · {stats['total_units']} units on hand · "
                f"{stats['needs_reorder']} need reordering"
            )
        )
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def select(self, item_id: Optional[int]) -> None:
        self.selected_id = item_id
        for row in self._rows:
            if isinstance(row, ItemRow):
                row.set_selected(row.item.id == item_id)

    def adjust(self, item: SupplyItem, delta: int) -> None:
        if item.id is None:
            return
        reason = "manual +" if delta > 0 else "manual -"
        self.storage.adjust_quantity(item.id, delta, reason)
        self.refresh()
        self.app.refresh_alert_badge()

    # -- actions -----------------------------------------------------------

    def add_item(self) -> None:
        dialog = ItemDialog(self, self.app, title="Add supply item")
        if dialog.result:
            self.storage.upsert_item(dialog.result)
            self.refresh()

    def edit_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            messagebox.showinfo("Edit item", "Click an item in the list first.", parent=self)
            return
        dialog = ItemDialog(self, self.app, title="Edit supply item", item=item)
        if dialog.result:
            self.storage.upsert_item(dialog.result)
            self.refresh()

    def delete_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            messagebox.showinfo("Delete item", "Click an item in the list first.", parent=self)
            return
        if not messagebox.askyesno(
            "Delete item",
            f"Remove “{item.name}” from the supply list?\n\nIts stock history goes too.",
            parent=self,
        ):
            return
        assert item.id is not None
        self.storage.delete_item(item.id)
        self.selected_id = None
        self.refresh()

    def seed_defaults(self) -> None:
        added = 0
        for printer in self.app.config.printers:
            added += inventory.seed_defaults(self.storage, printer.id, printer.profile)
        self.refresh()
        messagebox.showinfo(
            "Starter list",
            f"Added {added} item(s)." if added else "Everything from the starter list is already here.",
            parent=self,
        )

    def export_csv(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export supply list",
            defaultextension=".csv",
            initialfile="printer-supplies.csv",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        # newline="" keeps csv's own \r\n from becoming \r\r\n on Windows, which
        # shows up in Excel as a blank row between every entry.
        with open(path, "w", newline="", encoding="utf-8") as handle:
            handle.write(inventory.to_csv(self.storage.list_items()))
        messagebox.showinfo("Export", f"Saved to {path}", parent=self)

    def show_history(self, item: SupplyItem) -> None:
        if item.id is None:
            return
        entries = self.storage.stock_log(item.id, limit=100)
        if not entries:
            messagebox.showinfo(
                "Stock history", f"No movements recorded for {item.name} yet.", parent=self
            )
            return
        import time as _time

        lines = [
            f"{_time.strftime('%d %b %Y %I:%M %p', _time.localtime(row['changed_at']))}   "
            f"{row['delta']:+d}  →  {row['quantity']}   {row['reason']}"
            for row in entries
        ]
        window = tk.Toplevel(self)
        window.title(f"Stock history — {item.name}")
        window.configure(bg=BG)
        text = tk.Text(window, width=64, height=min(24, len(lines) + 2), font=("Consolas", 9))
        text.pack(padx=12, pady=12, fill="both", expand=True)
        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")
        ttk.Button(window, text="Close", command=window.destroy).pack(pady=(0, 12))

    def _selected_item(self) -> Optional[SupplyItem]:
        if self.selected_id is None:
            return None
        return self.storage.get_item(self.selected_id)


class ItemRow(tk.Frame):
    """One shelf item, with the +/- controls."""

    def __init__(self, parent: tk.Misc, tab: SuppliesTab, item: SupplyItem, index: int):
        self.base_bg = BG if index % 2 == 0 else "#f7f7f7"
        super().__init__(parent, bg=self.base_bg)
        self.tab = tab
        self.item = item

        self._cell(item.name, 34, bold=True)
        self._cell(item.part_number or "—", 14)
        self._cell(item.category, 12)
        self._cell(self._printer_label(), 12)

        # -- quantity controls
        qty_frame = tk.Frame(self, bg=self.base_bg, width=20)
        qty_frame.pack(side="left", padx=4, pady=4)

        minus = tk.Button(
            qty_frame,
            text="−",
            width=2,
            font=("Segoe UI", 11, "bold"),
            relief="flat",
            bg="#e0e0e0",
            activebackground="#cfcfcf",
            command=lambda: self.tab.adjust(self.item, -1),
        )
        minus.pack(side="left")
        if item.quantity == 0:
            minus.configure(state="disabled", bg="#f0f0f0", fg="#bbb")

        self.qty_label = tk.Label(
            qty_frame,
            text=str(item.quantity),
            bg=self.base_bg,
            width=4,
            font=("Segoe UI", 11, "bold"),
            fg=self._qty_color(),
        )
        self.qty_label.pack(side="left", padx=2)

        tk.Button(
            qty_frame,
            text="+",
            width=2,
            font=("Segoe UI", 11, "bold"),
            relief="flat",
            bg="#e0e0e0",
            activebackground="#cfcfcf",
            command=lambda: self.tab.adjust(self.item, 1),
        ).pack(side="left")

        tk.Label(
            qty_frame, text=item.unit, bg=self.base_bg, fg="#888", font=("Segoe UI", 8), width=5
        ).pack(side="left", padx=(4, 0))

        self._cell(str(item.reorder_at), 10)

        if item.needs_reorder:
            tk.Label(
                self,
                text="ORDER" if item.quantity else "OUT",
                bg=LOW if item.quantity == 0 else WARN,
                fg="white",
                font=("Segoe UI", 8, "bold"),
                padx=6,
            ).pack(side="left", padx=6)

        self.bind("<Button-1>", self._on_click)
        for child in self.winfo_children():
            if not isinstance(child, tk.Button):
                child.bind("<Button-1>", self._on_click)
        self.bind("<Double-Button-1>", lambda e: self.tab.show_history(self.item))

    def _printer_label(self) -> str:
        if not self.item.printer_id:
            return "Shop stock"
        printer = self.tab.app.config.printer(self.item.printer_id)
        return printer.name if printer else self.item.printer_id

    def _qty_color(self) -> str:
        if not self.item.counted:
            return "#9e9e9e"  # never counted — no judgement either way
        if self.item.quantity == 0:
            return LOW
        if self.item.needs_reorder:
            return WARN
        return OK

    def _cell(self, text: str, width: int, bold: bool = False) -> None:
        tk.Label(
            self,
            text=_truncate(text, width + 4),
            bg=self.base_bg,
            width=width,
            anchor="w",
            padx=4,
            pady=6,
            font=("Segoe UI", 9, "bold" if bold else "normal"),
        ).pack(side="left")

    def _on_click(self, _event=None) -> None:
        self.tab.select(self.item.id)

    def set_selected(self, selected: bool) -> None:
        bg = "#e3f2fd" if selected else self.base_bg
        self.configure(bg=bg)
        for child in self.winfo_children():
            if isinstance(child, (tk.Label, tk.Frame)):
                try:
                    child.configure(bg=bg)
                except tk.TclError:
                    pass
                for grandchild in child.winfo_children():
                    if isinstance(grandchild, tk.Label):
                        try:
                            grandchild.configure(bg=bg)
                        except tk.TclError:
                            pass


class ItemDialog(simpledialog.Dialog):
    """Add/edit form for a shelf item."""

    def __init__(self, parent: tk.Misc, app, title: str, item: Optional[SupplyItem] = None):
        self.app = app
        self.item = item
        self.result: Optional[SupplyItem] = None
        super().__init__(parent, title=title)

    def body(self, master):  # noqa: D102 - tkinter API
        master.configure(padx=12, pady=8)
        item = self.item

        self.name_var = tk.StringVar(value=item.name if item else "")
        self.part_var = tk.StringVar(value=item.part_number if item else "")
        self.category_var = tk.StringVar(value=item.category if item else "Ink")
        self.qty_var = tk.StringVar(value=str(item.quantity) if item else "0")
        self.reorder_var = tk.StringVar(value=str(item.reorder_at) if item else "1")
        self.unit_var = tk.StringVar(value=item.unit if item else "each")
        self.notes_var = tk.StringVar(value=item.notes if item else "")

        printer_names = ["Shop stock (no printer)"] + [p.name for p in self.app.config.printers]
        current = "Shop stock (no printer)"
        if item and item.printer_id:
            printer = self.app.config.printer(item.printer_id)
            if printer:
                current = printer.name
        self.printer_var = tk.StringVar(value=current)

        rows = [
            ("Item name", ttk.Entry(master, textvariable=self.name_var, width=42)),
            ("Part number", ttk.Entry(master, textvariable=self.part_var, width=42)),
            (
                "Category",
                ttk.Combobox(
                    master,
                    textvariable=self.category_var,
                    values=CATEGORIES,
                    state="readonly",
                    width=40,
                ),
            ),
            (
                "Belongs to",
                ttk.Combobox(
                    master,
                    textvariable=self.printer_var,
                    values=printer_names,
                    state="readonly",
                    width=40,
                ),
            ),
            ("On hand", ttk.Entry(master, textvariable=self.qty_var, width=10)),
            ("Reorder at", ttk.Entry(master, textvariable=self.reorder_var, width=10)),
            ("Unit", ttk.Entry(master, textvariable=self.unit_var, width=16)),
            ("Notes", ttk.Entry(master, textvariable=self.notes_var, width=42)),
        ]
        for row, (label, widget) in enumerate(rows):
            ttk.Label(master, text=label).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 10))
            widget.grid(row=row, column=1, sticky="w", pady=4)

        ttk.Label(
            master,
            text="“Reorder at” is the on-hand count that triggers a reorder alert.",
            foreground="#666",
            font=("Segoe UI", 8),
        ).grid(row=len(rows), column=0, columnspan=2, sticky="w", pady=(8, 0))
        return None

    def validate(self) -> bool:  # noqa: D102 - tkinter API
        if not self.name_var.get().strip():
            messagebox.showwarning("Item name", "Give the item a name.", parent=self)
            return False
        for label, var in (("On hand", self.qty_var), ("Reorder at", self.reorder_var)):
            try:
                if int(var.get()) < 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning(label, f"“{label}” must be a whole number, 0 or more.", parent=self)
                return False
        return True

    def apply(self) -> None:  # noqa: D102 - tkinter API
        printer_id = ""
        chosen = self.printer_var.get()
        printer = next((p for p in self.app.config.printers if p.name == chosen), None)
        if printer:
            printer_id = printer.id

        item = self.item or SupplyItem()
        item.name = self.name_var.get().strip()
        item.part_number = self.part_var.get().strip()
        item.category = self.category_var.get()
        item.printer_id = printer_id
        item.quantity = int(self.qty_var.get())
        item.reorder_at = int(self.reorder_var.get())
        item.unit = self.unit_var.get().strip() or "each"
        item.notes = self.notes_var.get().strip()
        # Typing a number in this form is a count, even if the number is zero.
        item.counted = True
        self.result = item


def _truncate(text: str, length: int) -> str:
    text = str(text)
    return text if len(text) <= length else text[: length - 1] + "…"
