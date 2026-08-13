"""The on-screen alert popup."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Sequence

from ..models import AlertEvent

CRITICAL_COLOR = "#c62828"
WARNING_COLOR = "#ef6c00"
BG = "#ffffff"


class AlertPopup(tk.Toplevel):
    """Always-on-top window listing the alerts that just fired."""

    def __init__(
        self,
        parent: tk.Misc,
        events: Sequence[AlertEvent],
        on_close: Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent)
        self.events = list(events)
        self._on_close = on_close

        critical = any(e.severity == "critical" for e in self.events)
        accent = CRITICAL_COLOR if critical else WARNING_COLOR

        self.title("Printer Supply Alert")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._close)

        header = tk.Frame(self, bg=accent)
        header.pack(fill="x")
        headline = (
            "Printer needs attention" if critical else "Printer supplies running low"
        )
        tk.Label(
            header,
            text=headline,
            bg=accent,
            fg="white",
            font=("Segoe UI", 14, "bold"),
            padx=18,
            pady=12,
        ).pack(anchor="w")

        body = tk.Frame(self, bg=BG, padx=18, pady=14)
        body.pack(fill="both", expand=True)

        for event in sorted(self.events, key=lambda e: (e.severity != "critical", e.printer_name)):
            self._add_row(body, event)

        footer = tk.Frame(self, bg="#f4f4f4", padx=18, pady=12)
        footer.pack(fill="x")
        ttk.Button(footer, text="Dismiss", command=self._close).pack(side="right")
        if len(self.events) > 1:
            tk.Label(
                footer,
                text=f"{len(self.events)} items need attention",
                bg="#f4f4f4",
                fg="#555",
                font=("Segoe UI", 9),
            ).pack(side="left")

        self._center(parent)
        self.lift()
        self.bell()
        self.focus_force()

    def _add_row(self, parent: tk.Frame, event: AlertEvent) -> None:
        critical = event.severity == "critical"
        color = CRITICAL_COLOR if critical else WARNING_COLOR

        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(0, 12))

        badge = tk.Label(
            row,
            text="CRITICAL" if critical else "LOW",
            bg=color,
            fg="white",
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=2,
        )
        badge.grid(row=0, column=0, sticky="nw", padx=(0, 10), pady=(2, 0))

        text = tk.Frame(row, bg=BG)
        text.grid(row=0, column=1, sticky="w")
        tk.Label(
            text,
            text=f"{event.printer_name} — {event.subject_name}",
            bg=BG,
            font=("Segoe UI", 11, "bold"),
            anchor="w",
            justify="left",
        ).pack(anchor="w")
        tk.Label(
            text,
            text=event.message,
            bg=BG,
            fg="#444",
            font=("Segoe UI", 9),
            wraplength=460,
            anchor="w",
            justify="left",
        ).pack(anchor="w", pady=(2, 0))

        if event.level_percent is not None and event.kind in ("supply", "tray"):
            self._add_bar(text, event.level_percent, color)

    def _add_bar(self, parent: tk.Frame, percent: float, color: str) -> None:
        width, height = 200, 8
        canvas = tk.Canvas(
            parent, width=width, height=height, bg=BG, highlightthickness=0, bd=0
        )
        canvas.pack(anchor="w", pady=(6, 0))
        canvas.create_rectangle(0, 0, width, height, fill="#e6e6e6", outline="")
        filled = max(2, int(width * max(0.0, min(100.0, percent)) / 100))
        canvas.create_rectangle(0, 0, filled, height, fill=color, outline="")

    def _center(self, parent: tk.Misc) -> None:
        """Centre on the parent window, or on the screen when it's hidden."""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        try:
            if parent.winfo_viewable():
                x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
                y = parent.winfo_rooty() + (parent.winfo_height() - height) // 3
            else:
                raise tk.TclError("parent not viewable")
        except tk.TclError:
            x = (self.winfo_screenwidth() - width) // 2
            y = (self.winfo_screenheight() - height) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _close(self) -> None:
        try:
            self.destroy()
        finally:
            if self._on_close:
                self._on_close()
