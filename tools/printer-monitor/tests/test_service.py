"""The monitor loop end-to-end: poll, record, alert, de-duplicate."""

from __future__ import annotations

import time

import pytest

from printer_monitor.config import AlertSettings, AppConfig, PrinterConfig, SnmpSettings, Thresholds
from printer_monitor.notify import Notifier
from printer_monitor.service import MonitorService
from printer_monitor.storage import Storage

from .fake_agent import FakeAgent
from .mibs import LASERJET_4100, LATEX_360


class RecordingNotifier(Notifier):
    """A Notifier that records batches instead of sending anything."""

    def __init__(self):
        from printer_monitor.config import EmailSettings

        super().__init__(EmailSettings(), popup_enabled=False, email_enabled=False)
        self.batches = []

    def dispatch(self, events):
        self.batches.append(list(events))
        return {"popup": True, "email": False, "errors": []}

    @property
    def all_events(self):
        return [event for batch in self.batches for event in batch]


@pytest.fixture
def storage(tmp_path):
    with Storage(tmp_path / "service.db") as store:
        yield store


def config_for(*agents: tuple[FakeAgent, str, str]) -> AppConfig:
    printers = []
    for agent, printer_id, version in agents:
        printers.append(
            PrinterConfig(
                id=printer_id,
                name=printer_id,
                host=agent.host,
                snmp=SnmpSettings(
                    community=agent.community,
                    version=version,
                    port=agent.port,
                    timeout=1.0,
                    retries=1,
                ),
            )
        )
    return AppConfig(
        poll_interval_seconds=30,
        printers=printers,
        thresholds=Thresholds(supply_warning=20, supply_critical=8, tray_warning=10),
        alerts=AlertSettings(popup_enabled=True, email_enabled=False, inventory_alerts=False),
    )


def test_poll_once_covers_both_printers(storage):
    with FakeAgent(LATEX_360) as latex, FakeAgent(LASERJET_4100, versions=("1",)) as laser:
        config = config_for((latex, "latex360", "2c"), (laser, "lj4100", "1"))
        notifier = RecordingNotifier()
        service = MonitorService(config, storage, notifier=notifier)

        readings = service.poll_once()

    assert len(readings) == 2
    assert all(r.online for r in readings)
    assert {r.printer_id for r in readings} == {"latex360", "lj4100"}


def test_poll_once_raises_the_expected_alerts(storage):
    with FakeAgent(LATEX_360) as latex:
        config = config_for((latex, "latex360", "2c"))
        notifier = RecordingNotifier()
        MonitorService(config, storage, notifier=notifier).poll_once()

    names = {e.subject_name for e in notifier.all_events}
    # Yellow 15% (warning), Black 6% (critical), maintenance cartridge 18% (warning),
    # and the light cyan/light magenta printhead at 41%... which is above 20%, so not that one.
    assert "HP 831 Latex Yellow" in names
    assert "HP 831 Latex Black" in names
    assert "Maintenance Cartridge" in names
    assert "HP 831 Latex Cyan" not in names  # 70%

    severities = {e.subject_name: e.severity for e in notifier.all_events}
    assert severities["HP 831 Latex Black"] == "critical"
    assert severities["HP 831 Latex Yellow"] == "warning"


def test_history_is_recorded(storage):
    with FakeAgent(LATEX_360) as latex:
        config = config_for((latex, "latex360", "2c"))
        MonitorService(config, storage, notifier=RecordingNotifier()).poll_once()

    rows = storage.supply_history("latex360", "hp-831-latex-cyan")
    assert len(rows) == 1
    assert rows[0]["percent"] == 70.0


def test_second_poll_does_not_re_alert(storage):
    with FakeAgent(LATEX_360) as latex:
        config = config_for((latex, "latex360", "2c"))
        notifier = RecordingNotifier()
        service = MonitorService(config, storage, notifier=notifier)

        service.poll_once()
        first = len(notifier.all_events)
        service.poll_once()

    assert first > 0
    assert len(notifier.all_events) == first  # nothing new the second time


def test_alerts_are_logged_to_the_database(storage):
    with FakeAgent(LATEX_360) as latex:
        config = config_for((latex, "latex360", "2c"))
        MonitorService(config, storage, notifier=RecordingNotifier()).poll_once()

    logged = storage.recent_alerts()
    assert logged
    assert storage.unacknowledged_alert_count() == len(logged)
    storage.acknowledge_alerts()
    assert storage.unacknowledged_alert_count() == 0


def test_supply_list_is_seeded_from_the_printer(storage):
    with FakeAgent(LATEX_360) as latex:
        config = config_for((latex, "latex360", "2c"))
        MonitorService(config, storage, notifier=RecordingNotifier()).poll_once()

    items = storage.list_items("latex360")
    assert len(items) == 12
    assert all(item.supply_key for item in items)


def test_seeding_can_be_switched_off(storage):
    with FakeAgent(LATEX_360) as latex:
        config = config_for((latex, "latex360", "2c"))
        MonitorService(
            config, storage, notifier=RecordingNotifier(), auto_seed_inventory=False
        ).poll_once()
    assert storage.list_items() == []


def test_offline_printer_is_recorded_not_raised(storage):
    config = AppConfig(
        printers=[
            PrinterConfig(
                id="dead",
                name="Unplugged",
                host="127.0.0.1",
                snmp=SnmpSettings(port=9, timeout=0.2, retries=0),
            )
        ],
        alerts=AlertSettings(offline_after_failures=1, inventory_alerts=False),
    )
    notifier = RecordingNotifier()
    service = MonitorService(config, storage, notifier=notifier)
    readings = service.poll_once()

    assert not readings[0].online
    assert [e.kind for e in notifier.all_events] == ["printer"]


def test_disabled_printers_are_skipped(storage):
    with FakeAgent(LATEX_360) as latex:
        config = config_for((latex, "latex360", "2c"))
        config.printers[0].enabled = False
        readings = MonitorService(config, storage, notifier=RecordingNotifier()).poll_once()
    assert readings == []


def test_background_thread_polls_and_stops(storage):
    with FakeAgent(LATEX_360) as latex:
        config = config_for((latex, "latex360", "2c"))
        config.poll_interval_seconds = 30
        notifier = RecordingNotifier()
        seen = []
        service = MonitorService(
            config, storage, notifier=notifier, on_readings=seen.append
        )
        service.start()
        assert service.running

        deadline = time.time() + 8
        while not seen and time.time() < deadline:
            time.sleep(0.05)
        service.stop()

    assert seen, "the loop never produced a reading"
    assert not service.running


def test_callbacks_receive_readings_and_alerts(storage):
    with FakeAgent(LATEX_360) as latex:
        config = config_for((latex, "latex360", "2c"))
        readings_seen, alerts_seen = [], []
        service = MonitorService(
            config,
            storage,
            notifier=RecordingNotifier(),
            on_readings=readings_seen.append,
            on_alerts=alerts_seen.append,
        )
        service.poll_once()

    assert len(readings_seen) == 1
    assert len(alerts_seen) == 1
    assert alerts_seen[0]


def test_a_failing_callback_does_not_break_the_cycle(storage):
    with FakeAgent(LATEX_360) as latex:
        config = config_for((latex, "latex360", "2c"))

        def broken(_readings):
            raise RuntimeError("boom")

        service = MonitorService(
            config, storage, notifier=RecordingNotifier(), on_readings=broken
        )
        readings = service.poll_once()

    assert readings and readings[0].online


def test_burn_rate_estimate(storage):
    """Two weeks of history at a steady burn should predict the remaining days."""
    now = time.time()
    with storage._lock:  # noqa: SLF001 - seeding history directly is the point
        for day, percent in enumerate([100, 90, 80, 70, 60, 50, 40]):
            storage._conn.execute(
                "INSERT INTO supply_history (printer_id, supply_key, supply_name, percent, "
                "level_raw, max_capacity, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("latex360", "cyan", "Cyan", percent, percent, 100, now - (6 - day) * 86400),
            )
        storage._conn.commit()

    # 10% per day, 40% left -> about 4 days.
    assert storage.estimate_days_remaining("latex360", "cyan") == pytest.approx(4.0, abs=0.2)


def test_burn_rate_ignores_history_before_a_refill(storage):
    now = time.time()
    with storage._lock:  # noqa: SLF001
        series = [(6, 60), (5, 40), (4, 20), (3, 100), (2, 90), (1, 80)]
        for days_ago, percent in series:
            storage._conn.execute(
                "INSERT INTO supply_history (printer_id, supply_key, supply_name, percent, "
                "level_raw, max_capacity, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("latex360", "cyan", "Cyan", percent, percent, 100, now - days_ago * 86400),
            )
        storage._conn.commit()

    # Only the post-refill decline counts: 100 -> 80 over 2 days = 10%/day, 80 left -> 8 days.
    assert storage.estimate_days_remaining("latex360", "cyan") == pytest.approx(8.0, abs=0.3)


def test_burn_rate_needs_data(storage):
    assert storage.estimate_days_remaining("latex360", "cyan") is None


def test_prune_history_drops_old_rows(storage):
    now = time.time()
    with storage._lock:  # noqa: SLF001
        for days_ago in (400, 200, 5):
            storage._conn.execute(
                "INSERT INTO supply_history (printer_id, supply_key, supply_name, percent, "
                "level_raw, max_capacity, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("p", "k", "K", 50, 50, 100, now - days_ago * 86400),
            )
        storage._conn.commit()

    assert storage.prune_history(days=180) == 2
    assert len(storage.supply_history("p", "k")) == 1
