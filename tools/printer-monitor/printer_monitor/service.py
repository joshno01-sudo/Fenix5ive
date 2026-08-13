"""The monitoring loop, usable headless or behind the GUI."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional, Sequence

from .alerts import AlertEngine
from .config import AppConfig
from .inventory import seed_from_reading
from .models import AlertEvent, PrinterReading
from .notify import Notifier
from .poller import poll_printer
from .storage import Storage

log = logging.getLogger(__name__)

ReadingCallback = Callable[[list[PrinterReading]], None]
AlertCallback = Callable[[list[AlertEvent]], None]


class MonitorService:
    """Polls every printer on an interval, records history, raises alerts.

    Runs in a background thread when started via :meth:`start`, or one cycle at
    a time via :meth:`poll_once` (used by tests and the CLI's ``check``).
    """

    def __init__(
        self,
        config: AppConfig,
        storage: Storage,
        notifier: Optional[Notifier] = None,
        on_readings: Optional[ReadingCallback] = None,
        on_alerts: Optional[AlertCallback] = None,
        auto_seed_inventory: bool = True,
    ):
        self.config = config
        self.storage = storage
        self.engine = AlertEngine(config, storage)
        self.notifier = notifier or Notifier(
            config.email,
            popup_enabled=config.alerts.popup_enabled,
            email_enabled=config.alerts.email_enabled,
        )
        self.on_readings = on_readings
        self.on_alerts = on_alerts
        self.auto_seed_inventory = auto_seed_inventory

        self.last_readings: list[PrinterReading] = []
        self.last_poll_at: Optional[float] = None
        self.last_error: Optional[str] = None

        self._thread: Optional[threading.Thread] = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._prune_counter = 0

    # -- lifecycle ---------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            # A loop that was asked to stop but hasn't noticed yet just keeps
            # going — that is what "resume" means, and it avoids two loops.
            self._stop.clear()
            return
        self._thread = None
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="printer-monitor", daemon=True)
        self._thread.start()
        log.info("monitor started (interval %ss)", self.config.poll_interval_seconds)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is None:
            return
        thread.join(timeout=timeout)
        if thread.is_alive():
            # Still finishing a slow poll (several unreachable printers can take
            # a while). Keep the reference so `running` stays True and a later
            # start() can't spawn a second loop alongside it.
            log.warning("monitor thread did not stop within %.0fs; it will exit on its own", timeout)
            return
        self._thread = None

    def poll_now(self) -> None:
        """Ask the loop to run a cycle immediately."""
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            started = time.time()
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001 - the loop must survive anything
                log.exception("poll cycle failed")
                self.last_error = "Poll cycle failed; see the log for details."

            elapsed = time.time() - started
            delay = max(5.0, self.config.poll_interval_seconds - elapsed)
            self._wake.wait(timeout=delay)
            self._wake.clear()

    # -- one cycle ---------------------------------------------------------

    def poll_once(self) -> list[PrinterReading]:
        printers = self.config.enabled_printers()
        readings: list[PrinterReading] = []
        events: list[AlertEvent] = []

        for printer in printers:
            reading = poll_printer(printer)
            readings.append(reading)
            try:
                self.storage.record_reading(reading)
            except Exception:  # noqa: BLE001
                log.exception("failed to record history for %s", printer.id)
            if reading.online and self.auto_seed_inventory:
                try:
                    seed_from_reading(self.storage, reading)
                except Exception:  # noqa: BLE001
                    log.exception("failed to seed supply list for %s", printer.id)
            events.extend(self.engine.evaluate_reading(reading))

        try:
            events.extend(self.engine.evaluate_inventory(self.storage.list_items()))
        except Exception:  # noqa: BLE001
            log.exception("inventory evaluation failed")

        self.last_readings = readings
        self.last_poll_at = time.time()

        if self.on_readings:
            try:
                self.on_readings(readings)
            except Exception:  # noqa: BLE001
                log.exception("readings callback failed")

        self._handle_events(events)
        self._maybe_prune()
        return readings

    def _handle_events(self, events: list[AlertEvent]) -> None:
        fresh = self.engine.filter_new(events)
        if not fresh:
            return

        # Keep the notifier in step with the live config (Settings can change it
        # while the loop is running).
        self.notifier.popup_enabled = self.config.alerts.popup_enabled
        self.notifier.email_enabled = self.config.alerts.email_enabled
        self.notifier.email.settings = self.config.email

        result = self.notifier.dispatch(fresh)
        errors = result.get("errors") or []
        self.last_error = "; ".join(str(e) for e in errors) if errors else None  # type: ignore[union-attr]

        popup_sent = bool(result.get("popup"))
        email_sent = bool(result.get("email"))
        attempted = self.notifier.popup_enabled or self.notifier.email_enabled
        # Only suppress an alert once it actually reached somebody. If every
        # enabled channel failed (SMTP down, no display), leave it un-marked so
        # the next cycle tries again instead of going quiet for repeat_hours.
        # With no channel switched on at all there is nothing to deliver, so the
        # normal de-duplication applies and the history stays readable.
        delivered = popup_sent or email_sent or not attempted
        if not delivered:
            log.warning(
                "no alert channel succeeded; %d alert(s) will be retried next cycle", len(fresh)
            )
            return

        for event in fresh:
            try:
                self.storage.log_alert(event, popup=popup_sent, email=email_sent)
                self.engine.mark_sent(event)
            except Exception:  # noqa: BLE001
                log.exception("failed to record alert %s", event.dedupe_key)

        if self.on_alerts:
            try:
                self.on_alerts(fresh)
            except Exception:  # noqa: BLE001
                log.exception("alerts callback failed")

    def _maybe_prune(self) -> None:
        self._prune_counter += 1
        # Roughly once a day, and always on the first cycle. The `== 1` case
        # matters: with a poll interval over 12 hours `every` is 1, and a
        # `% every != 1` test would never be satisfied.
        every = max(1, int(86400 / max(1, self.config.poll_interval_seconds)))
        if self._prune_counter != 1 and self._prune_counter % every != 0:
            return
        try:
            self.storage.prune_history(self.config.history_days)
        except Exception:  # noqa: BLE001
            log.exception("history prune failed")


def run_forever(
    config: AppConfig, storage: Storage, notifier: Optional[Notifier] = None
) -> MonitorService:
    """Blocking headless run — used by ``printer-monitor monitor``."""
    service = MonitorService(config, storage, notifier=notifier)
    service.start()
    try:
        while service.running:
            time.sleep(1.0)
    except KeyboardInterrupt:
        log.info("interrupted; shutting down")
    finally:
        service.stop()
    return service


def summarize_readings(readings: Sequence[PrinterReading]) -> str:
    """Compact text report — what ``check`` prints and the GUI status bar shows."""
    lines: list[str] = []
    for reading in readings:
        header = f"{reading.printer_name} ({reading.host})"
        if not reading.online:
            lines.append(f"{header}: OFFLINE — {reading.error}")
            continue
        lines.append(f"{header}: {reading.status_text}")
        if reading.model:
            lines.append(f"  Model: {reading.model}" + (f"   S/N: {reading.serial}" if reading.serial else ""))
        if reading.page_count is not None:
            lines.append(f"  Life page count: {reading.page_count:,}")
        for supply in reading.supplies:
            capacity = f"  [{supply.capacity_text}]" if supply.capacity_text else ""
            waste = " (waste receptacle)" if supply.is_waste else ""
            lines.append(f"  - {supply.display_name}: {supply.level_text}{capacity}{waste}")
        for media in reading.inputs:
            loaded = f" — {media.media_name}" if media.media_name else ""
            lines.append(f"  - {media.display_name}: {media.level_text}{loaded}")
        for alert in reading.alerts:
            lines.append(f"  ! {alert.severity}: {alert.description}")
        lines.append("")
    return "\n".join(lines).rstrip()
