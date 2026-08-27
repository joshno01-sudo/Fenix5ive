"""Regression tests for failure-path behaviour found in review."""

from __future__ import annotations

import os
import smtplib
import stat
import threading
import time

import pytest

from printer_monitor.config import (
    AlertSettings,
    AppConfig,
    EmailSettings,
    PrinterConfig,
    SnmpSettings,
    Thresholds,
    default_config,
)
from printer_monitor.models import Supply
from printer_monitor.notify import Notifier
from printer_monitor.poller import poll_printer, probe_printer
from printer_monitor.service import MonitorService
from printer_monitor.storage import Storage

from .fake_agent import FakeAgent
from .mibs import LATEX_360


@pytest.fixture
def storage(tmp_path):
    with Storage(tmp_path / "robust.db") as store:
        yield store


# ---------------------------------------------------------------------------
# The poller must never raise
# ---------------------------------------------------------------------------


def test_bad_snmp_version_in_config_does_not_abort_the_poll():
    """A hand-edited config with a nonsense version must not kill the cycle."""
    printer = PrinterConfig(id="x", name="Bad", host="127.0.0.1")
    printer.snmp.version = "9z"  # bypasses the GUI's validation
    reading = poll_printer(printer)
    assert not reading.online
    assert "unsupported SNMP version" in (reading.error or "")


def test_bad_snmp_version_is_reported_by_the_test_button():
    printer = PrinterConfig(id="x", name="Bad", host="127.0.0.1")
    printer.snmp.version = "9z"
    result = probe_printer(printer)
    assert not result["ok"]
    assert "Bad SNMP settings" in str(result["message"])


def test_one_broken_printer_does_not_stop_the_others(storage):
    with FakeAgent(LATEX_360) as agent:
        broken = PrinterConfig(id="broken", name="Broken", host="127.0.0.1")
        broken.snmp.version = "nope"
        good = PrinterConfig(
            id="good",
            name="Good",
            host=agent.host,
            snmp=SnmpSettings(port=agent.port, timeout=1.0, retries=0),
        )
        config = AppConfig(printers=[broken, good], alerts=AlertSettings(popup_enabled=False))
        readings = MonitorService(config, storage).poll_once()

    assert len(readings) == 2
    assert {r.printer_id: r.online for r in readings} == {"broken": False, "good": True}


# ---------------------------------------------------------------------------
# Alerts must not be de-duplicated away when nobody received them
# ---------------------------------------------------------------------------


def failing_notifier() -> Notifier:
    settings = EmailSettings(
        smtp_host="smtp.invalid", from_addr="a@b.c", to_addrs=["d@e.f"], timeout=0.1
    )
    notifier = Notifier(settings, popup_enabled=False, email_enabled=True)

    def explode(*_args, **_kwargs):
        raise smtplib.SMTPException("server down")

    notifier.email.send_alerts = explode  # type: ignore[method-assign]
    return notifier


def config_for(agent: FakeAgent) -> AppConfig:
    return AppConfig(
        printers=[
            PrinterConfig(
                id="latex360",
                name="HP Latex 360",
                host=agent.host,
                snmp=SnmpSettings(port=agent.port, timeout=1.0, retries=0),
            )
        ],
        thresholds=Thresholds(supply_warning=20, supply_critical=8),
        alerts=AlertSettings(popup_enabled=False, email_enabled=True, inventory_alerts=False),
    )


def test_failed_delivery_is_retried_next_cycle(storage):
    with FakeAgent(LATEX_360) as agent:
        service = MonitorService(config_for(agent), storage, notifier=failing_notifier())
        service.poll_once()
        assert storage.recent_alerts() == []  # nothing claimed as delivered
        assert service.last_error and "Email" in service.last_error

        # Second cycle with a working sender: the same alerts are still pending,
        # not suppressed by the failed first attempt.
        service.notifier = recording_notifier()
        service.poll_once()
        assert service.last_error is None

    logged = storage.recent_alerts()
    assert logged, "alerts were suppressed even though the first send failed"
    assert any("Black" in row["subject_name"] for row in logged)
    assert all(row["notified_email"] == 1 for row in logged)


def recording_notifier() -> Notifier:
    """Email enabled and succeeding, but nothing leaves the process."""
    settings = EmailSettings(smtp_host="smtp.test", from_addr="a@b.c", to_addrs=["d@e.f"])
    notifier = Notifier(settings, popup_enabled=False, email_enabled=True)
    notifier.sent: list = []  # type: ignore[attr-defined]
    notifier.email.send_alerts = lambda events: notifier.sent.extend(events)  # type: ignore[method-assign]
    return notifier


def working_notifier() -> Notifier:
    """No channels enabled — nothing to deliver, so de-duplication applies."""
    return Notifier(EmailSettings(), popup_enabled=False, email_enabled=False)


def test_successful_delivery_suppresses_the_repeat(storage):
    with FakeAgent(LATEX_360) as agent:
        config = config_for(agent)
        config.alerts.email_enabled = False  # nothing to deliver -> dedupe applies
        service = MonitorService(config, storage, notifier=working_notifier())
        service.poll_once()
        first = len(storage.recent_alerts())
        service.poll_once()
        assert len(storage.recent_alerts()) == first


# ---------------------------------------------------------------------------
# Thread lifecycle
# ---------------------------------------------------------------------------


def test_pause_then_resume_never_runs_two_loops(storage):
    with FakeAgent(LATEX_360) as agent:
        config = config_for(agent)
        config.alerts.email_enabled = False
        config.poll_interval_seconds = 30
        service = MonitorService(config, storage, notifier=working_notifier())

        service.start()
        service.stop()
        service.start()
        service.stop()
        service.start()
        try:
            time.sleep(0.3)
            live = [t for t in threading.enumerate() if t.name == "printer-monitor" and t.is_alive()]
            assert len(live) <= 1, f"{len(live)} monitor loops running at once"
        finally:
            service.stop()


def test_stop_is_safe_before_start(storage):
    service = MonitorService(AppConfig(), storage, notifier=working_notifier())
    service.stop()  # must not raise
    assert not service.running


# ---------------------------------------------------------------------------
# History pruning
# ---------------------------------------------------------------------------


def test_pruning_runs_with_a_very_long_poll_interval(storage):
    """With an interval over 12 hours the once-a-day counter must still fire."""
    now = time.time()
    with storage._lock:  # noqa: SLF001
        storage._conn.execute(
            "INSERT INTO supply_history (printer_id, supply_key, supply_name, percent, "
            "level_raw, max_capacity, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("p", "k", "K", 50, 50, 100, now - 400 * 86400),
        )
        storage._conn.commit()

    config = AppConfig(printers=[], history_days=180)
    config.poll_interval_seconds = 86400
    service = MonitorService(config, storage, notifier=working_notifier())
    service.poll_once()
    service.poll_once()

    assert storage.supply_history("p", "k") == []


# ---------------------------------------------------------------------------
# Threshold override keys
# ---------------------------------------------------------------------------


def test_global_override_without_a_printer_id_is_stored_usably():
    """The Settings dialog can produce an override with no printer attached."""
    thresholds = Thresholds(supply_warning=20, supply_critical=8)
    thresholds.set_supply_override("", "maintenance-cartridge", 40, 20)

    assert "maintenance-cartridge" in thresholds.per_supply
    assert ":maintenance-cartridge" not in thresholds.per_supply
    assert thresholds.for_supply("latex360", "maintenance-cartridge") == (40, 20)
    assert thresholds.for_supply("lj4100", "maintenance-cartridge") == (40, 20)

    thresholds.clear_supply_override("", "maintenance-cartridge")
    assert thresholds.for_supply("latex360", "maintenance-cartridge") == (20, 8)


# ---------------------------------------------------------------------------
# Percent-unit supplies with an unknown capacity
# ---------------------------------------------------------------------------


def test_percent_supply_without_a_capacity_still_reports_a_level():
    """Unit=percent with maxCapacity=-2 means the level already is a percentage."""
    supply = Supply(
        index=1,
        description="Black Cartridge",
        type_code=3,
        unit_code=19,
        level_raw=12,
        max_capacity_raw=-2,
    )
    assert supply.remaining_percent == 12.0
    assert supply.level_state == "ok"


def test_percent_supply_assumption_is_not_applied_to_other_units():
    supply = Supply(index=1, description="Ink", unit_code=15, level_raw=12, max_capacity_raw=-2)
    assert supply.remaining_percent is None


def test_percent_supply_with_a_nonsense_level_is_still_unknown():
    supply = Supply(index=1, description="Ink", unit_code=19, level_raw=250, max_capacity_raw=-2)
    assert supply.remaining_percent is None


def test_such_a_supply_can_raise_an_alert(storage):
    from printer_monitor.alerts import AlertEngine
    from printer_monitor.models import PrinterReading

    config = AppConfig(thresholds=Thresholds(supply_warning=20, supply_critical=8))
    engine = AlertEngine(config, storage)
    reading = PrinterReading(
        printer_id="lj4100",
        printer_name="HP LaserJet 4100",
        host="h",
        online=True,
        supplies=[
            Supply(
                index=1,
                description="Black Cartridge",
                type_code=3,
                unit_code=19,
                level_raw=5,
                max_capacity_raw=-2,
            )
        ],
    )
    events = engine.evaluate_reading(reading)
    assert len(events) == 1
    assert events[0].severity == "critical"


# ---------------------------------------------------------------------------
# Config file permissions
# ---------------------------------------------------------------------------


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions only")
def test_the_temp_file_is_never_world_readable(tmp_path, monkeypatch):
    """The SMTP password must not be exposed in the pre-rename temp file."""
    from pathlib import Path

    seen_modes: list[int] = []
    real_replace = Path.replace

    target = tmp_path / "config.json"
    tmp = target.with_suffix(".json.tmp")

    def spy(self, dst):
        # Capture the temp file's mode at the moment it is swapped into place.
        # Patching Path.replace rather than os.replace: pathlib only calls
        # os.replace directly from 3.11 on, so an os-level spy silently never
        # fires on older versions and the test passes without checking anything.
        seen_modes.append(stat.S_IMODE(os.stat(self).st_mode))
        return real_replace(self, dst)

    monkeypatch.setattr(Path, "replace", spy)
    config = AppConfig(email=EmailSettings(password="super-secret"))
    config.save(target)

    assert seen_modes == [0o600], f"temp file mode was {oct(seen_modes[0]) if seen_modes else 'n/a'}"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert not tmp.exists()


def test_saving_twice_overwrites_cleanly(tmp_path):
    target = tmp_path / "config.json"
    config = AppConfig(poll_interval_seconds=60)
    config.save(target)
    config.poll_interval_seconds = 120
    config.save(target)
    assert AppConfig.load(target).poll_interval_seconds == 120


# ---------------------------------------------------------------------------
# Console encoding
# ---------------------------------------------------------------------------


def test_cli_output_survives_a_limited_console(tmp_path, monkeypatch):
    """A classic Windows cp437 console cannot encode an em dash.

    Supply names contain them, so without a tolerant stream `stock` died with a
    UnicodeEncodeError instead of printing the list.
    """
    import io
    import sys

    from printer_monitor.cli import main

    buffer = io.TextIOWrapper(io.BytesIO(), encoding="cp437", errors="strict")
    monkeypatch.setattr(sys, "stdout", buffer)

    config = tmp_path / "config.json"
    default_config().save(config)
    args = ["--config", str(config), "--db", str(tmp_path / "d.db"), "stock"]

    assert main(args + ["--seed"]) == 0
    assert main(args) == 0

    buffer.flush()
    printed = buffer.buffer.getvalue().decode("cp437")
    assert "Printhead" in printed
    assert "starter item" in printed


def test_tolerating_the_console_does_not_break_utf8(tmp_path, monkeypatch):
    """On a capable console the characters must still come through intact."""
    import io
    import sys

    from printer_monitor.cli import main

    buffer = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", errors="strict")
    monkeypatch.setattr(sys, "stdout", buffer)

    config = tmp_path / "config.json"
    default_config().save(config)
    main(["--config", str(config), "--db", str(tmp_path / "d.db"), "stock", "--seed"])
    main(["--config", str(config), "--db", str(tmp_path / "d.db"), "stock"])

    buffer.flush()
    printed = buffer.buffer.getvalue().decode("utf-8")
    assert "Printhead — Cyan / Black" in printed
