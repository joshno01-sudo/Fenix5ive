"""Threshold evaluation and alert de-duplication.

Turns readings into AlertEvents, then decides which of those actually deserve a
popup/email right now — so a cartridge sitting at 19% doesn't fire every five
minutes for a week.
"""

from __future__ import annotations

import logging
import time
from typing import Iterable, Optional

from .config import AppConfig
from .models import AlertEvent, PrinterReading, SupplyItem
from .storage import Storage

log = logging.getLogger(__name__)


class AlertEngine:
    def __init__(self, config: AppConfig, storage: Storage):
        self.config = config
        self.storage = storage
        # printer_id -> consecutive failed polls
        self._failures: dict[str, int] = {}

    # -- evaluation --------------------------------------------------------

    def evaluate_reading(self, reading: PrinterReading) -> list[AlertEvent]:
        """All threshold breaches in this reading, before de-duplication."""
        events: list[AlertEvent] = []
        thresholds = self.config.thresholds
        settings = self.config.alerts

        if not reading.online:
            self._failures[reading.printer_id] = self._failures.get(reading.printer_id, 0) + 1
            if (
                settings.offline_alerts
                and self._failures[reading.printer_id] >= max(1, settings.offline_after_failures)
            ):
                events.append(
                    AlertEvent(
                        printer_id=reading.printer_id,
                        printer_name=reading.printer_name,
                        subject_key="offline",
                        subject_name="Printer unreachable",
                        kind="printer",
                        severity="warning",
                        message=(
                            f"{reading.printer_name} ({reading.host}) has not answered "
                            f"{self._failures[reading.printer_id]} polls in a row. "
                            f"Last error: {reading.error or 'unknown'}"
                        ),
                        timestamp=reading.timestamp,
                    )
                )
            return events

        self._failures[reading.printer_id] = 0

        # --- supplies -----------------------------------------------------
        for supply in reading.supplies:
            percent = supply.remaining_percent
            if percent is None:
                continue
            warning, critical = thresholds.for_supply(reading.printer_id, supply.key)
            if percent <= critical:
                severity, trip = "critical", critical
            elif percent <= warning:
                severity, trip = "warning", warning
            else:
                self._clear(reading.printer_id, "supply", supply.key, percent, warning)
                continue

            noun = "full" if supply.is_waste else "remaining"
            detail = f"{percent:.0f}% {noun}"
            if supply.is_waste:
                detail = f"{percent:.0f}% life left ({100 - percent:.0f}% full)"
            on_hand = self._on_hand_note(reading.printer_id, supply.key)
            events.append(
                AlertEvent(
                    printer_id=reading.printer_id,
                    printer_name=reading.printer_name,
                    subject_key=supply.key,
                    subject_name=supply.display_name,
                    kind="supply",
                    severity=severity,
                    message=(
                        f"{supply.display_name} on {reading.printer_name} is at {detail} "
                        f"(alert threshold {trip}%).{on_hand}"
                    ),
                    level_percent=percent,
                    threshold=float(trip),
                    timestamp=reading.timestamp,
                )
            )

        # --- media / trays -------------------------------------------------
        for media in reading.inputs:
            percent = media.remaining_percent
            if media.is_empty:
                severity, percent_value, trip = "critical", 0.0, float(thresholds.tray_warning)
                message = f"{media.display_name} on {reading.printer_name} is empty."
            elif percent is not None and percent <= thresholds.tray_warning:
                severity, percent_value = "warning", percent
                trip = float(thresholds.tray_warning)
                message = (
                    f"{media.display_name} on {reading.printer_name} is at {percent:.0f}% "
                    f"(threshold {thresholds.tray_warning}%)."
                )
            else:
                self._clear(
                    reading.printer_id, "tray", media.key, percent, thresholds.tray_warning
                )
                continue
            if media.media_name:
                message += f" Loaded media: {media.media_name}."
            events.append(
                AlertEvent(
                    printer_id=reading.printer_id,
                    printer_name=reading.printer_name,
                    subject_key=media.key,
                    subject_name=media.display_name,
                    kind="tray",
                    severity=severity,
                    message=message,
                    level_percent=percent_value,
                    threshold=trip,
                    timestamp=reading.timestamp,
                )
            )

        # --- the printer's own critical alerts ------------------------------
        if settings.printer_error_alerts:
            for alert in reading.alerts:
                if not alert.is_critical:
                    continue
                events.append(
                    AlertEvent(
                        printer_id=reading.printer_id,
                        printer_name=reading.printer_name,
                        subject_key=f"prtalert-{alert.code}-{alert.group_code}",
                        subject_name=alert.description,
                        kind="printer",
                        severity="critical",
                        message=(
                            f"{reading.printer_name} reports a critical condition: "
                            f"{alert.description} ({alert.group})."
                        ),
                        timestamp=reading.timestamp,
                    )
                )
        return events

    def evaluate_inventory(self, items: Iterable[SupplyItem]) -> list[AlertEvent]:
        """Warn when the shelf itself runs low."""
        if not self.config.alerts.inventory_alerts:
            return []
        events: list[AlertEvent] = []
        for item in items:
            key = f"item-{item.id}"
            if not item.needs_reorder:
                self._clear(item.printer_id or "shop", "inventory", key, None, None)
                continue
            severity = "critical" if item.quantity == 0 else "warning"
            on_hand = "none left" if item.quantity == 0 else f"{item.quantity} left"
            part = f" (P/N {item.part_number})" if item.part_number else ""
            events.append(
                AlertEvent(
                    printer_id=item.printer_id or "shop",
                    printer_name=item.printer_id or "Shop stock",
                    subject_key=key,
                    subject_name=item.name,
                    kind="inventory",
                    severity=severity,
                    message=(
                        f"Shelf stock low: {item.name}{part} — {on_hand}, "
                        f"reorder point {item.reorder_at}. Time to order."
                    ),
                    level_percent=float(item.quantity),
                    threshold=float(item.reorder_at),
                )
            )
        return events

    # -- de-duplication ----------------------------------------------------

    def filter_new(self, events: Iterable[AlertEvent]) -> list[AlertEvent]:
        """Drop events already notified recently at the same-or-higher severity."""
        repeat_seconds = max(0.0, float(self.config.alerts.repeat_hours)) * 3600
        now = time.time()
        out: list[AlertEvent] = []
        for event in events:
            state = self.storage.get_alert_state(event.dedupe_key)
            if state is not None:
                escalated = event.severity == "critical" and state["severity"] != "critical"
                age = now - float(state["last_sent_at"])
                if not escalated and age < repeat_seconds:
                    continue
            out.append(event)
        return out

    def mark_sent(self, event: AlertEvent) -> None:
        self.storage.set_alert_state(event.dedupe_key, event.severity, event.level_percent)

    def _on_hand_note(self, printer_id: str, supply_key: str) -> str:
        """" 2 spare(s) on hand." — appended to supply alerts when we know."""
        try:
            items = self.storage.list_items(printer_id)
        except Exception:  # noqa: BLE001 - a note is never worth failing an alert over
            return ""
        for item in items:
            if item.supply_key != supply_key:
                continue
            if item.quantity == 0:
                return f" No spares on hand — order {item.part_number or item.name}."
            return f" {item.quantity} spare(s) on hand."
        return ""

    def _clear(
        self,
        printer_id: str,
        kind: str,
        subject_key: str,
        percent: Optional[float],
        threshold: Optional[float],
    ) -> None:
        """Reset an alert once the level recovers past the threshold + margin."""
        key = f"{printer_id}|{kind}|{subject_key}"
        if self.storage.get_alert_state(key) is None:
            return
        if percent is not None and threshold is not None:
            if percent < threshold + self.config.alerts.clear_margin_percent:
                return  # inside the hysteresis band; keep the alert latched
        self.storage.clear_alert_state(key)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_summary(events: list[AlertEvent]) -> str:
    if not events:
        return "No alerts."
    if len(events) == 1:
        return events[0].message
    lines = [f"{len(events)} supply alerts:", ""]
    for event in events:
        marker = "!!" if event.severity == "critical" else " *"
        lines.append(f"{marker} {event.message}")
    return "\n".join(lines)
