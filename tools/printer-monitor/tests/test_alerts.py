"""Threshold evaluation, de-duplication and hysteresis."""

from __future__ import annotations

import time

import pytest

from printer_monitor.alerts import AlertEngine, format_summary
from printer_monitor.config import AppConfig, PrinterConfig, Thresholds
from printer_monitor.models import MediaInput, PrinterAlert, PrinterReading, Supply, SupplyItem
from printer_monitor.storage import Storage


@pytest.fixture
def storage(tmp_path):
    with Storage(tmp_path / "alerts.db") as store:
        yield store


@pytest.fixture
def config():
    return AppConfig(
        printers=[PrinterConfig(id="latex360", name="HP Latex 360", host="10.0.0.5")],
        thresholds=Thresholds(supply_warning=20, supply_critical=8, tray_warning=10),
    )


@pytest.fixture
def engine(config, storage):
    return AlertEngine(config, storage)


def reading_with(*supplies: Supply, **kwargs) -> PrinterReading:
    return PrinterReading(
        printer_id=kwargs.pop("printer_id", "latex360"),
        printer_name=kwargs.pop("printer_name", "HP Latex 360"),
        host="10.0.0.5",
        online=kwargs.pop("online", True),
        supplies=list(supplies),
        **kwargs,
    )


def ink(name: str, percent: float) -> Supply:
    """A consumable reporting ``percent`` remaining, in percent units."""
    return Supply(
        index=1,
        description=name,
        type_code=6,
        class_code=3,
        unit_code=19,
        level_raw=int(percent),
        max_capacity_raw=100,
    )


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------


def test_healthy_supply_raises_nothing(engine):
    assert engine.evaluate_reading(reading_with(ink("Cyan", 80))) == []


def test_warning_at_threshold(engine):
    events = engine.evaluate_reading(reading_with(ink("Cyan", 20)))
    assert len(events) == 1
    assert events[0].severity == "warning"
    assert events[0].level_percent == 20.0
    assert events[0].threshold == 20.0
    assert "20%" in events[0].message


def test_just_above_threshold_is_quiet(engine):
    assert engine.evaluate_reading(reading_with(ink("Cyan", 21))) == []


def test_critical_takes_precedence(engine):
    events = engine.evaluate_reading(reading_with(ink("Black", 6)))
    assert len(events) == 1
    assert events[0].severity == "critical"
    assert events[0].threshold == 8.0


def test_unknown_level_never_alerts(engine):
    """A "some remaining" reading has no number, so it can't be judged low."""
    unknown = Supply(index=1, description="Light Magenta", level_raw=-3, max_capacity_raw=7750)
    assert engine.evaluate_reading(reading_with(unknown)) == []


def test_waste_receptacle_alerts_when_nearly_full(engine):
    """A maintenance cartridge at 95% full has 5% life left -> critical."""
    cartridge = Supply(
        index=12,
        description="Maintenance Cartridge",
        type_code=8,
        class_code=4,
        unit_code=19,
        level_raw=95,
        max_capacity_raw=100,
    )
    events = engine.evaluate_reading(reading_with(cartridge))
    assert len(events) == 1
    assert events[0].severity == "critical"
    assert events[0].level_percent == 5.0
    assert "5% life left" in events[0].message
    assert "95% full" in events[0].message


def test_per_supply_override(engine, config):
    config.thresholds.set_supply_override("latex360", "cyan", warning=50, critical=30)
    events = engine.evaluate_reading(reading_with(ink("Cyan", 45)))
    assert len(events) == 1
    assert events[0].threshold == 50.0
    assert events[0].severity == "warning"


def test_override_only_applies_to_its_printer(engine, config):
    config.thresholds.set_supply_override("other-printer", "cyan", warning=90, critical=80)
    assert engine.evaluate_reading(reading_with(ink("Cyan", 45))) == []


def test_multiple_supplies_produce_multiple_events(engine):
    events = engine.evaluate_reading(
        reading_with(ink("Cyan", 80), ink("Yellow", 15), ink("Black", 4))
    )
    assert sorted(e.severity for e in events) == ["critical", "warning"]


def test_empty_tray_is_critical(engine):
    tray = MediaInput(index=3, name="Tray 3", level_raw=0, max_capacity_raw=500)
    events = engine.evaluate_reading(reading_with(inputs=[tray]))
    assert len(events) == 1
    assert events[0].kind == "tray"
    assert events[0].severity == "critical"
    assert "empty" in events[0].message.lower()


def test_low_tray_warns_with_media_name(engine):
    tray = MediaInput(
        index=2, name="Tray 2", media_name="Letter", level_raw=40, max_capacity_raw=500
    )
    events = engine.evaluate_reading(reading_with(inputs=[tray]))
    assert len(events) == 1
    assert events[0].severity == "warning"
    assert "Letter" in events[0].message


def test_loaded_roll_does_not_alert(engine):
    roll = MediaInput(index=1, name="Roll 1", level_raw=-3, max_capacity_raw=-2)
    assert engine.evaluate_reading(reading_with(inputs=[roll])) == []


def test_printer_critical_alert_is_forwarded(engine):
    alert = PrinterAlert(
        index=1, severity_code=3, group_code=8, code=1101, description="Tray 3 empty"
    )
    events = engine.evaluate_reading(reading_with(alerts=[alert]))
    assert len(events) == 1
    assert events[0].kind == "printer"
    assert "Tray 3 empty" in events[0].message


def test_printer_warning_alert_is_not_forwarded(engine):
    alert = PrinterAlert(
        index=2, severity_code=4, group_code=11, code=1102, description="Black cartridge low"
    )
    assert engine.evaluate_reading(reading_with(alerts=[alert])) == []


def test_printer_error_forwarding_can_be_switched_off(engine, config):
    config.alerts.printer_error_alerts = False
    alert = PrinterAlert(index=1, severity_code=3, group_code=8, code=1, description="Jam")
    assert engine.evaluate_reading(reading_with(alerts=[alert])) == []


# ---------------------------------------------------------------------------
# Offline detection
# ---------------------------------------------------------------------------


def test_offline_alerts_only_after_repeated_failures(engine, config):
    config.alerts.offline_after_failures = 3
    offline = reading_with(online=False, error="timed out")

    assert engine.evaluate_reading(offline) == []
    assert engine.evaluate_reading(offline) == []
    events = engine.evaluate_reading(offline)
    assert len(events) == 1
    assert "has not answered 3 polls" in events[0].message


def test_a_successful_poll_resets_the_offline_counter(engine, config):
    config.alerts.offline_after_failures = 2
    offline = reading_with(online=False, error="timed out")
    engine.evaluate_reading(offline)
    engine.evaluate_reading(reading_with(ink("Cyan", 90)))
    assert engine.evaluate_reading(offline) == []


# ---------------------------------------------------------------------------
# Inventory alerts
# ---------------------------------------------------------------------------


def test_inventory_alert_when_at_reorder_point(engine):
    items = [
        SupplyItem(
            id=1, name="Cyan ink", printer_id="latex360", quantity=1, reorder_at=1, counted=True
        )
    ]
    events = engine.evaluate_inventory(items)
    assert len(events) == 1
    assert events[0].kind == "inventory"
    assert events[0].severity == "warning"
    assert "1 left" in events[0].message


def test_inventory_alert_is_critical_when_out(engine):
    items = [
        SupplyItem(
            id=1, name="Cyan ink", quantity=0, reorder_at=1, part_number="CZ123A", counted=True
        )
    ]
    events = engine.evaluate_inventory(items)
    assert events[0].severity == "critical"
    assert "none left" in events[0].message
    assert "CZ123A" in events[0].message


def test_well_stocked_item_is_quiet(engine):
    plenty = SupplyItem(id=1, name="Cyan", quantity=6, reorder_at=2, counted=True)
    assert engine.evaluate_inventory([plenty]) == []


def test_inventory_alerts_can_be_switched_off(engine, config):
    config.alerts.inventory_alerts = False
    out = SupplyItem(id=1, name="Cyan", quantity=0, counted=True)
    assert engine.evaluate_inventory([out]) == []


def test_uncounted_shelf_row_does_not_alert(engine):
    """Seeding a starter list must not fire an alert for every row at once."""
    never_counted = SupplyItem(id=1, name="Cyan ink", quantity=0, reorder_at=1)
    assert engine.evaluate_inventory([never_counted]) == []


def test_supply_alert_mentions_spares_on_hand(engine, storage):
    storage.upsert_item(
        SupplyItem(name="Cyan", printer_id="latex360", supply_key="cyan", quantity=2)
    )
    events = engine.evaluate_reading(reading_with(ink("Cyan", 10)))
    assert "2 spare(s) on hand" in events[0].message


def test_supply_alert_says_when_there_are_no_spares(engine, storage):
    storage.upsert_item(
        SupplyItem(
            name="Cyan", printer_id="latex360", supply_key="cyan", quantity=0, part_number="CZ1A"
        )
    )
    events = engine.evaluate_reading(reading_with(ink("Cyan", 10)))
    assert "No spares on hand" in events[0].message
    assert "CZ1A" in events[0].message


# ---------------------------------------------------------------------------
# De-duplication / repeat suppression
# ---------------------------------------------------------------------------


def test_same_alert_is_not_repeated_immediately(engine):
    events = engine.evaluate_reading(reading_with(ink("Cyan", 15)))
    fresh = engine.filter_new(events)
    assert len(fresh) == 1
    for event in fresh:
        engine.mark_sent(event)

    again = engine.filter_new(engine.evaluate_reading(reading_with(ink("Cyan", 14))))
    assert again == []


def test_alert_repeats_once_the_repeat_window_passes(engine, config, storage):
    config.alerts.repeat_hours = 12
    event = engine.evaluate_reading(reading_with(ink("Cyan", 15)))[0]
    engine.mark_sent(event)

    # Backdate the record by 13 hours.
    storage.set_alert_state(event.dedupe_key, event.severity, event.level_percent)
    with storage._lock:  # noqa: SLF001 - deliberate: fake the clock in the store
        storage._conn.execute(
            "UPDATE alert_state SET last_sent_at = ?", (time.time() - 13 * 3600,)
        )
        storage._conn.commit()

    assert len(engine.filter_new(engine.evaluate_reading(reading_with(ink("Cyan", 14))))) == 1


def test_escalation_to_critical_breaks_through_suppression(engine):
    """A warning already sent must not mask the later critical alert."""
    warning = engine.evaluate_reading(reading_with(ink("Cyan", 15)))[0]
    engine.mark_sent(warning)

    critical = engine.filter_new(engine.evaluate_reading(reading_with(ink("Cyan", 5))))
    assert len(critical) == 1
    assert critical[0].severity == "critical"


def test_refill_clears_the_latch_so_the_next_dip_alerts_again(engine, storage):
    event = engine.evaluate_reading(reading_with(ink("Cyan", 15)))[0]
    engine.mark_sent(event)
    assert storage.get_alert_state(event.dedupe_key) is not None

    # Refilled well clear of the threshold -> state resets.
    engine.evaluate_reading(reading_with(ink("Cyan", 100)))
    assert storage.get_alert_state(event.dedupe_key) is None

    assert len(engine.filter_new(engine.evaluate_reading(reading_with(ink("Cyan", 15))))) == 1


def test_hysteresis_keeps_the_latch_just_above_the_threshold(engine, config):
    """A cartridge hovering at 22% (threshold 20 + 5 margin) must stay latched."""
    config.alerts.clear_margin_percent = 5
    event = engine.evaluate_reading(reading_with(ink("Cyan", 19)))[0]
    engine.mark_sent(event)

    engine.evaluate_reading(reading_with(ink("Cyan", 22)))  # inside the band
    assert engine.storage.get_alert_state(event.dedupe_key) is not None

    engine.evaluate_reading(reading_with(ink("Cyan", 26)))  # clear of it
    assert engine.storage.get_alert_state(event.dedupe_key) is None


def test_dedupe_key_separates_printers_and_kinds():
    from printer_monitor.models import AlertEvent

    a = AlertEvent("p1", "P1", "cyan", "Cyan", "supply", "warning", "m")
    b = AlertEvent("p2", "P2", "cyan", "Cyan", "supply", "warning", "m")
    c = AlertEvent("p1", "P1", "cyan", "Cyan", "tray", "warning", "m")
    assert len({a.dedupe_key, b.dedupe_key, c.dedupe_key}) == 3


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def test_format_summary():
    from printer_monitor.models import AlertEvent

    assert format_summary([]) == "No alerts."
    one = AlertEvent("p", "P", "k", "Cyan", "supply", "warning", "Cyan is low")
    assert format_summary([one]) == "Cyan is low"
    two = AlertEvent("p", "P", "k2", "Black", "supply", "critical", "Black is out")
    text = format_summary([one, two])
    assert "2 supply alerts" in text
    assert "Black is out" in text


def test_alert_title():
    from printer_monitor.models import AlertEvent

    warning = AlertEvent("p", "HP Latex 360", "k", "Cyan", "supply", "warning", "m")
    critical = AlertEvent("p", "HP Latex 360", "k", "Cyan", "supply", "critical", "m")
    assert warning.title == "Low supply: HP Latex 360 — Cyan"
    assert critical.title.startswith("CRITICAL:")
