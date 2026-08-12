"""Dashboard tab: live levels for every supply on every printer."""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from typing import Optional

from .. import printer_mib as mib
from ..models import PrinterReading, Supply
from ..storage import Storage

BG = "#ffffff"
CARD_BG = "#fafafa"
CRITICAL = "#c62828"
WARNING = "#ef6c00"
OK = "#2e7d32"
MUTED = "#9e9e9e"


class DashboardTab(ttk.Frame):
    def __init__(self, parent: tk.Misc, app):
        super().__init__(parent, padding=0)
        self.app = app
        self.storage: Storage = app.storage
        self._cards: dict[str, "PrinterCard"] = {}

        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
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
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

        self.placeholder = tk.Label(
            self.inner,
            text=(
                "No readings yet.\n\n"
                "Add your printers' IP addresses in Settings, then press Refresh."
            ),
            bg=BG,
            fg="#777",
            font=("Segoe UI", 11),
            justify="center",
            pady=60,
        )
        self.placeholder.pack(fill="x")

    def _on_wheel(self, event) -> None:
        if not self.winfo_ismapped():
            return
        delta = -1 * (event.delta // 120 if abs(event.delta) >= 120 else event.delta)
        self.canvas.yview_scroll(delta, "units")

    def update_readings(self, readings: list[PrinterReading]) -> None:
        if readings:
            self.placeholder.pack_forget()

        seen: set[str] = set()
        for reading in readings:
            seen.add(reading.printer_id)
            card = self._cards.get(reading.printer_id)
            if card is None:
                card = PrinterCard(self.inner, self.app)
                card.pack(fill="x", padx=16, pady=(16, 0))
                self._cards[reading.printer_id] = card
            card.update_reading(reading)

        for printer_id in list(self._cards):
            if printer_id not in seen:
                self._cards.pop(printer_id).destroy()

        self.canvas.configure(scrollregion=self.canvas.bbox("all"))


class PrinterCard(tk.Frame):
    """One printer: identity, status, then a bar per supply and per tray."""

    def __init__(self, parent: tk.Misc, app):
        super().__init__(parent, bg=CARD_BG, highlightbackground="#e0e0e0", highlightthickness=1)
        self.app = app
        self.storage: Storage = app.storage

        header = tk.Frame(self, bg=CARD_BG)
        header.pack(fill="x", padx=16, pady=(14, 8))

        self.name_label = tk.Label(
            header, text="", bg=CARD_BG, font=("Segoe UI", 13, "bold"), anchor="w"
        )
        self.name_label.pack(side="left")

        self.status_label = tk.Label(header, text="", bg=CARD_BG, font=("Segoe UI", 9), anchor="e")
        self.status_label.pack(side="right")

        self.meta_label = tk.Label(
            self, text="", bg=CARD_BG, fg="#666", font=("Segoe UI", 8), anchor="w", justify="left"
        )
        self.meta_label.pack(fill="x", padx=16)

        self.body = tk.Frame(self, bg=CARD_BG)
        self.body.pack(fill="x", padx=16, pady=(10, 16))

        self._rows: dict[str, "LevelRow"] = {}

    def update_reading(self, reading: PrinterReading) -> None:
        self.name_label.configure(text=reading.printer_name)

        if not reading.online:
            self.status_label.configure(text="● OFFLINE", fg=CRITICAL)
            self.meta_label.configure(text=f"{reading.host} — {reading.error or 'no response'}")
        else:
            color = WARNING if reading.has_error_state else OK
            self.status_label.configure(text=f"● {reading.status_text}", fg=color)
            meta = [reading.host]
            if reading.model:
                meta.append(reading.model)
            if reading.serial:
                meta.append(f"S/N {reading.serial}")
            if reading.page_count is not None:
                meta.append(f"{reading.page_count:,} pages")
            stamp = time.strftime("%I:%M %p", time.localtime(reading.timestamp))
            meta.append(f"updated {stamp}")
            text = "   ·   ".join(meta)
            if reading.console_message:
                text += f"\nFront panel: {reading.console_message}"
            self.meta_label.configure(text=text)

        wanted: list[tuple[str, dict]] = []
        for supply in reading.supplies:
            warning, critical = self.app.config.thresholds.for_supply(
                reading.printer_id, supply.key
            )
            wanted.append(
                (
                    supply.key,
                    {
                        "label": supply.display_name,
                        "percent": supply.remaining_percent,
                        "text": supply.level_text,
                        "warning": warning,
                        "critical": critical,
                        "swatch": _swatch_for(supply),
                        "detail": self._supply_detail(reading, supply),
                    },
                )
            )
        for media in reading.inputs:
            wanted.append(
                (
                    media.key,
                    {
                        "label": media.display_name,
                        "percent": media.remaining_percent,
                        "text": media.level_text,
                        "warning": self.app.config.thresholds.tray_warning,
                        "critical": 0,
                        "swatch": "#b0bec5",
                        "detail": media.media_name,
                    },
                )
            )

        for key, spec in wanted:
            row = self._rows.get(key)
            if row is None:
                row = LevelRow(self.body)
                row.pack(fill="x", pady=3)
                self._rows[key] = row
            row.update_values(**spec)

        keys = {key for key, _ in wanted}
        for key in list(self._rows):
            if key not in keys:
                self._rows.pop(key).destroy()

        if not wanted and reading.online:
            self.meta_label.configure(
                text=self.meta_label.cget("text")
                + "\nThis printer reported no supply data over SNMP."
            )

    def _supply_detail(self, reading: PrinterReading, supply: Supply) -> str:
        bits: list[str] = []
        if supply.capacity_text:
            bits.append(supply.capacity_text)
        if supply.is_waste:
            bits.append("waste — fills up")
        days = self.storage.estimate_days_remaining(reading.printer_id, supply.key)
        if days is not None and days < 400:
            bits.append(f"~{days:.0f} days at current use")
        on_hand = self._on_hand(reading.printer_id, supply.key)
        if on_hand is not None:
            bits.append(f"{on_hand} spare(s) on hand" if on_hand else "no spares on hand")
        return "   ·   ".join(bits)

    def _on_hand(self, printer_id: str, supply_key: str) -> Optional[int]:
        for item in self.storage.list_items(printer_id):
            if item.supply_key == supply_key:
                return item.quantity
        return None


class LevelRow(tk.Frame):
    """A label, a level bar and a percentage."""

    BAR_WIDTH = 240
    BAR_HEIGHT = 14

    def __init__(self, parent: tk.Misc):
        super().__init__(parent, bg=CARD_BG)
        self.columnconfigure(1, weight=0)
        self.columnconfigure(3, weight=1)

        self.swatch = tk.Canvas(
            self, width=12, height=12, bg=CARD_BG, highlightthickness=0, bd=0
        )
        self.swatch.grid(row=0, column=0, padx=(0, 8))
        self._swatch_id = self.swatch.create_oval(1, 1, 11, 11, fill="#ccc", outline="#999")

        self.label = tk.Label(
            self, text="", bg=CARD_BG, font=("Segoe UI", 10), anchor="w", width=30
        )
        self.label.grid(row=0, column=1, sticky="w")

        self.bar = tk.Canvas(
            self,
            width=self.BAR_WIDTH,
            height=self.BAR_HEIGHT,
            bg=CARD_BG,
            highlightthickness=0,
            bd=0,
        )
        self.bar.grid(row=0, column=2, padx=10)

        self.value = tk.Label(
            self, text="", bg=CARD_BG, font=("Segoe UI", 10, "bold"), anchor="w", width=16
        )
        self.value.grid(row=0, column=3, sticky="w")

        self.detail = tk.Label(
            self, text="", bg=CARD_BG, fg="#777", font=("Segoe UI", 8), anchor="w"
        )
        self.detail.grid(row=1, column=1, columnspan=3, sticky="w", pady=(0, 2))

    def update_values(
        self,
        label: str,
        percent: Optional[float],
        text: str,
        warning: int,
        critical: int,
        swatch: str,
        detail: str = "",
    ) -> None:
        self.label.configure(text=_truncate(label, 34))
        self.swatch.itemconfigure(self._swatch_id, fill=swatch)

        color = _level_color(percent, warning, critical)
        self.value.configure(text=text, fg=color if percent is not None else MUTED)
        self.detail.configure(text=detail)
        if not detail:
            self.detail.grid_remove()
        else:
            self.detail.grid()

        self.bar.delete("all")
        self.bar.create_rectangle(
            0, 0, self.BAR_WIDTH, self.BAR_HEIGHT, fill="#e8e8e8", outline=""
        )
        if percent is None:
            self.bar.create_text(
                self.BAR_WIDTH / 2,
                self.BAR_HEIGHT / 2,
                text="level not reported",
                fill="#999",
                font=("Segoe UI", 7),
            )
            return
        filled = max(2, int(self.BAR_WIDTH * max(0.0, min(100.0, percent)) / 100))
        self.bar.create_rectangle(0, 0, filled, self.BAR_HEIGHT, fill=color, outline="")
        # Threshold tick so it's obvious where the alert fires.
        tick = int(self.BAR_WIDTH * max(0, min(100, warning)) / 100)
        self.bar.create_line(tick, 0, tick, self.BAR_HEIGHT, fill="#555", dash=(2, 2))


def _level_color(percent: Optional[float], warning: int, critical: int) -> str:
    if percent is None:
        return MUTED
    if percent <= critical:
        return CRITICAL
    if percent <= warning:
        return WARNING
    return OK


def _swatch_for(supply: Supply) -> str:
    color = supply.color
    if color and color in mib.COLOR_SWATCHES:
        return mib.COLOR_SWATCHES[color]
    if supply.is_waste:
        return "#8d6e63"
    return "#90a4ae"


def _truncate(text: str, length: int) -> str:
    return text if len(text) <= length else text[: length - 1] + "…"
