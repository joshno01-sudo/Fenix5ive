"""Data structures shared between the poller, storage, alerts and the GUI."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from . import printer_mib as mib

# Units where a bare 0-100 level with no stated capacity should be read as a
# percentage: percent itself, plus other(1)/unknown(2), which is what several
# office-printer vendors report instead.
_PERCENTISH_UNITS = {1, 2, mib.UNIT_PERCENT}


@dataclass
class Supply:
    """One row of the printer's supplies table."""

    index: int
    description: str
    type_code: int = 2
    class_code: int = 3
    unit_code: int = 19
    level_raw: int = mib.LEVEL_UNKNOWN
    max_capacity_raw: int = mib.LEVEL_UNKNOWN
    colorant: Optional[str] = None

    # -- derived -----------------------------------------------------------

    @property
    def type_name(self) -> str:
        return mib.supply_type_name(self.type_code)

    @property
    def unit_name(self) -> str:
        return mib.SUPPLY_UNIT.get(self.unit_code, f"unit {self.unit_code}")

    @property
    def is_waste(self) -> bool:
        return mib.is_waste_receptacle(self.type_code, self.class_code)

    @property
    def color(self) -> Optional[str]:
        return mib.guess_color(self.description, self.colorant)

    @property
    def effective_capacity(self) -> Optional[int]:
        """Max capacity, filling in the obvious value for percent-based supplies.

        Plenty of firmware reports a level of 0-100 but leaves max capacity at
        -2 (unknown) — HP does it with the unit set to percent, and several
        office-printer vendors do it with the unit left as other/unknown. In
        both cases the level already is a percentage, so 100 is the capacity.
        Without this those supplies would report no level at all and never
        alert, which is the worse failure of the two.
        """
        if self.max_capacity_raw > 0:
            return self.max_capacity_raw
        if self.unit_code in _PERCENTISH_UNITS and 0 <= self.level_raw <= 100:
            return 100
        return None

    @property
    def fraction_used(self) -> Optional[float]:
        """0.0-1.0 of capacity currently occupied, or None when unknown."""
        capacity = self.effective_capacity
        if self.level_raw < 0 or not capacity:
            return None
        return min(1.0, self.level_raw / capacity)

    @property
    def remaining_percent(self) -> Optional[float]:
        """Percent of usable life left, normalised across supply kinds.

        For consumables the printer reports what is left. For waste
        receptacles it reports how full they are, so that gets inverted — this
        way a threshold of 15% always means "15% of life left", whether it is
        a cyan cartridge or the Latex maintenance cartridge.
        """
        used = self.fraction_used
        if used is None:
            return None
        return round((1.0 - used) * 100.0, 1) if self.is_waste else round(used * 100.0, 1)

    @property
    def level_state(self) -> str:
        """``ok`` | ``some`` | ``unknown`` — how trustworthy the number is."""
        if self.remaining_percent is not None:
            return "ok"
        if self.level_raw == mib.LEVEL_SOME_REMAINING:
            return "some"
        return "unknown"

    @property
    def level_text(self) -> str:
        pct = self.remaining_percent
        if pct is not None:
            return f"{pct:.0f}%"
        if self.level_raw == mib.LEVEL_SOME_REMAINING:
            return "Some remaining"
        if self.level_raw == mib.LEVEL_OTHER:
            return "Present"
        return "Unknown"

    @property
    def capacity_text(self) -> str:
        """e.g. ``"775 ml"`` for a Latex cartridge, when the units allow it."""
        if self.max_capacity_raw <= 0:
            return ""
        unit = self.unit_code
        cap = self.max_capacity_raw
        if unit == mib.UNIT_PERCENT:
            return ""
        if unit == 15:  # tenths of a millilitre
            return f"{cap / 10:.0f} ml"
        if unit == 14:  # hundredths of a fluid ounce
            return f"{cap / 100:.1f} fl oz"
        if unit == 13:  # tenths of a gram
            return f"{cap / 10:.0f} g"
        if unit == 8:
            return f"{cap:,} sheets"
        if unit == 7:
            return f"{cap:,} impressions"
        if unit == 11:
            return f"{cap:,} hours"
        if unit == 18:
            return f"{cap:,} items"
        if unit == 17:
            return f"{cap:,} m"
        if unit == 16:
            return f"{cap:,} ft"
        return f"{cap:,} {self.unit_name}"

    @property
    def key(self) -> str:
        """Stable identifier for thresholds, history and alert de-duplication.

        Uses the description rather than the table index, because HP firmware
        renumbers the supplies table after a cartridge swap.
        """
        base = (self.description or f"supply-{self.index}").strip().lower()
        return "-".join(base.split())

    @property
    def display_name(self) -> str:
        if self.description:
            return self.description
        color = self.color
        if color:
            return f"{color} {self.type_name}"
        return f"{self.type_name} #{self.index}"


@dataclass
class MediaInput:
    """A paper tray or, on the Latex, a substrate roll."""

    index: int
    name: str
    description: str = ""
    media_name: str = ""
    level_raw: int = mib.LEVEL_UNKNOWN
    max_capacity_raw: int = mib.LEVEL_UNKNOWN
    status_code: int = 0
    unit_code: int = 8

    @property
    def remaining_percent(self) -> Optional[float]:
        if self.level_raw < 0 or self.max_capacity_raw <= 0:
            return None
        return round(min(100.0, self.level_raw / self.max_capacity_raw * 100.0), 1)

    @property
    def level_text(self) -> str:
        # "Empty" is checked before the percentage: a tray reporting 0 of 500
        # sheets should read as empty, not as a bare "0%".
        if self.level_raw == 0:
            return "Empty"
        pct = self.remaining_percent
        if pct is not None:
            return f"{pct:.0f}%"
        if self.level_raw == mib.LEVEL_SOME_REMAINING:
            return "Loaded"
        if self.level_raw == mib.LEVEL_OTHER:
            return "Present"
        return "Unknown"

    @property
    def is_empty(self) -> bool:
        return self.level_raw == 0

    @property
    def key(self) -> str:
        base = (self.name or self.description or f"input-{self.index}").strip().lower()
        return "tray-" + "-".join(base.split())

    @property
    def display_name(self) -> str:
        return self.name or self.description or f"Tray {self.index}"


@dataclass
class PrinterAlert:
    """A row from the printer's own alert table (prtAlertTable)."""

    index: int
    severity_code: int
    group_code: int
    code: int
    description: str

    @property
    def severity(self) -> str:
        return mib.ALERT_SEVERITY.get(self.severity_code, "unknown")

    @property
    def group(self) -> str:
        return mib.ALERT_GROUP.get(self.group_code, "other")

    @property
    def is_critical(self) -> bool:
        return self.severity_code == 3


@dataclass
class PrinterReading:
    """Everything one poll of one printer produced."""

    printer_id: str
    printer_name: str
    host: str
    timestamp: float = field(default_factory=time.time)

    online: bool = False
    error: Optional[str] = None

    # identity
    model: str = ""
    serial: str = ""
    system_name: str = ""
    console_message: str = ""

    # status
    printer_status_code: Optional[int] = None
    device_status_code: Optional[int] = None
    detected_errors: list[str] = field(default_factory=list)

    # counters
    page_count: Optional[int] = None
    uptime_ticks: Optional[int] = None

    supplies: list[Supply] = field(default_factory=list)
    inputs: list[MediaInput] = field(default_factory=list)
    alerts: list[PrinterAlert] = field(default_factory=list)

    @property
    def status_text(self) -> str:
        if not self.online:
            return "Offline"
        parts: list[str] = []
        if self.printer_status_code in mib.PRINTER_STATUS:
            parts.append(mib.PRINTER_STATUS[self.printer_status_code].title())
        elif self.device_status_code in mib.DEVICE_STATUS:
            parts.append(mib.DEVICE_STATUS[self.device_status_code].title())
        if self.detected_errors:
            parts.append(", ".join(self.detected_errors))
        return " — ".join(parts) if parts else "Online"

    @property
    def has_error_state(self) -> bool:
        return bool(self.detected_errors) or self.device_status_code == 5

    def supply_by_key(self, key: str) -> Optional[Supply]:
        for supply in self.supplies:
            if supply.key == key:
                return supply
        return None


@dataclass
class SupplyItem:
    """A row in the on-hand supply list (what's on the shelf, not in the printer)."""

    id: Optional[int] = None
    name: str = ""
    printer_id: str = ""
    part_number: str = ""
    category: str = "Ink"
    quantity: int = 0
    reorder_at: int = 1
    unit: str = "each"
    notes: str = ""
    supply_key: str = ""
    # False until somebody actually counts the shelf. Starter/auto-added rows
    # begin at zero, and "nobody has counted this yet" is not the same as "we
    # have run out" — without this, seeding a fresh list would fire an alert for
    # every row at once.
    counted: bool = False
    updated_at: float = field(default_factory=time.time)

    @property
    def needs_reorder(self) -> bool:
        return self.counted and self.quantity <= self.reorder_at


@dataclass
class AlertEvent:
    """A threshold breach worth telling somebody about."""

    printer_id: str
    printer_name: str
    subject_key: str
    subject_name: str
    kind: str  # supply | tray | printer | inventory
    severity: str  # warning | critical
    message: str
    level_percent: Optional[float] = None
    threshold: Optional[float] = None
    timestamp: float = field(default_factory=time.time)

    @property
    def dedupe_key(self) -> str:
        return f"{self.printer_id}|{self.kind}|{self.subject_key}"

    @property
    def title(self) -> str:
        prefix = "CRITICAL" if self.severity == "critical" else "Low supply"
        return f"{prefix}: {self.printer_name} — {self.subject_name}"
