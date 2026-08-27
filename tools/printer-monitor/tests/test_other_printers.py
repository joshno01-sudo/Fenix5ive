"""Non-HP office printers: the generic path must handle them unchanged."""

from __future__ import annotations

import pytest

from printer_monitor.alerts import AlertEngine
from printer_monitor.config import AlertSettings, AppConfig, PrinterConfig, Thresholds
from printer_monitor.poller import poll_printer, probe_printer
from printer_monitor.storage import Storage

from .fake_agent import FakeAgent
from .mibs import BROTHER_COLOR_MFP, KYOCERA_MONO_MFP
from .test_poller import printer_for


@pytest.fixture
def brother_reading():
    with FakeAgent(BROTHER_COLOR_MFP) as agent:
        yield poll_printer(printer_for(agent, "generic"))


@pytest.fixture
def kyocera_reading():
    with FakeAgent(KYOCERA_MONO_MFP) as agent:
        yield poll_printer(printer_for(agent, "generic"))


# ---------------------------------------------------------------------------
# Colour laser MFP
# ---------------------------------------------------------------------------


def test_colour_mfp_is_read_without_a_vendor_profile(brother_reading):
    assert brother_reading.online
    assert brother_reading.model == "Brother MFC-L8900CDW"
    assert brother_reading.serial == "U63878K0N123456"
    assert brother_reading.page_count == 88_412


def test_all_four_toners_plus_the_wear_parts(brother_reading):
    names = [s.display_name for s in brother_reading.supplies]
    assert len(names) == 7
    for expected in ("Black", "Cyan", "Magenta", "Yellow"):
        assert any(expected in name for name in names), expected
    assert "Drum Unit" in names
    assert "Belt Unit" in names
    assert "Waste Toner Box" in names


def test_toner_percentages(brother_reading):
    by_name = {s.display_name: s for s in brother_reading.supplies}
    assert by_name["Black Toner Cartridge"].remaining_percent == 62.0
    assert by_name["Cyan Toner Cartridge"].remaining_percent == 18.0
    assert by_name["Magenta Toner Cartridge"].remaining_percent == 4.0
    assert by_name["Yellow Toner Cartridge"].remaining_percent == 77.0


def test_colour_detection_on_a_cmyk_printer(brother_reading):
    by_name = {s.display_name: s for s in brother_reading.supplies}
    assert by_name["Cyan Toner Cartridge"].color == "Cyan"
    assert by_name["Magenta Toner Cartridge"].color == "Magenta"
    assert by_name["Yellow Toner Cartridge"].color == "Yellow"
    assert by_name["Black Toner Cartridge"].color == "Black"
    assert by_name["Drum Unit"].color is None


def test_waste_toner_box_is_inverted(brother_reading):
    """70% full means 30% of life left, same rule as the Latex cartridge."""
    box = next(s for s in brother_reading.supplies if s.display_name == "Waste Toner Box")
    assert box.is_waste
    assert box.remaining_percent == 30.0


def test_drum_and_belt_are_tracked_as_ordinary_consumables(brother_reading):
    by_name = {s.display_name: s for s in brother_reading.supplies}
    drum = by_name["Drum Unit"]
    belt = by_name["Belt Unit"]
    assert drum.type_name == "Drum (OPC)"
    assert drum.remaining_percent == 45.0
    assert not drum.is_waste
    assert belt.type_name == "Transfer unit"
    assert belt.remaining_percent == 90.0


def test_colour_mfp_tray(brother_reading):
    tray = brother_reading.inputs[0]
    assert tray.display_name == "Tray 1"
    assert tray.remaining_percent == 72.0
    assert tray.media_name == "Letter"


def test_colour_mfp_alerts(tmp_path, brother_reading):
    with Storage(tmp_path / "b.db") as storage:
        config = AppConfig(thresholds=Thresholds(supply_warning=20, supply_critical=8))
        events = AlertEngine(config, storage).evaluate_reading(brother_reading)

    by_name = {e.subject_name: e for e in events}
    assert by_name["Magenta Toner Cartridge"].severity == "critical"
    assert by_name["Cyan Toner Cartridge"].severity == "warning"
    assert "Black Toner Cartridge" not in by_name  # 62%
    assert "Waste Toner Box" not in by_name  # 30% of life left


# ---------------------------------------------------------------------------
# Mono MFP reporting a bare percentage
# ---------------------------------------------------------------------------


def test_bare_level_with_no_capacity_is_still_read(kyocera_reading):
    """Unit "other" and capacity -2, but the level really is a percentage."""
    toner = kyocera_reading.supplies[0]
    assert toner.display_name == "TK-1160 Black Toner"
    assert toner.remaining_percent == 11.0
    assert toner.level_text == "11%"


def test_that_printer_still_raises_a_low_alert(tmp_path, kyocera_reading):
    with Storage(tmp_path / "k.db") as storage:
        config = AppConfig(thresholds=Thresholds(supply_warning=20, supply_critical=8))
        events = AlertEngine(config, storage).evaluate_reading(kyocera_reading)
    assert len(events) == 1
    assert events[0].subject_name == "TK-1160 Black Toner"
    assert events[0].severity == "warning"


def test_mono_mfp_cassette(kyocera_reading):
    cassette = kyocera_reading.inputs[0]
    assert cassette.display_name == "Cassette 1"
    assert cassette.remaining_percent == 60.0


# ---------------------------------------------------------------------------
# Mixed fleet
# ---------------------------------------------------------------------------


def test_a_mixed_fleet_polls_in_one_cycle(tmp_path):
    """Four printers from three vendors, monitored together."""
    from printer_monitor.config import SnmpSettings
    from printer_monitor.service import MonitorService

    from .mibs import LASERJET_4100, LATEX_360

    with FakeAgent(LATEX_360) as latex, FakeAgent(
        LASERJET_4100, versions=("1",)
    ) as laser, FakeAgent(BROTHER_COLOR_MFP) as brother, FakeAgent(
        KYOCERA_MONO_MFP
    ) as kyocera:
        printers = [
            ("latex360", latex, "2c"),
            ("lj4100", laser, "1"),
            ("brother", brother, "2c"),
            ("kyocera", kyocera, "2c"),
        ]
        config = AppConfig(
            printers=[
                PrinterConfig(
                    id=printer_id,
                    name=printer_id,
                    host=agent.host,
                    snmp=SnmpSettings(port=agent.port, version=version, timeout=1.5, retries=1),
                )
                for printer_id, agent, version in printers
            ],
            thresholds=Thresholds(supply_warning=20, supply_critical=8),
            alerts=AlertSettings(popup_enabled=False, email_enabled=False, inventory_alerts=False),
        )
        with Storage(tmp_path / "fleet.db") as storage:
            readings = MonitorService(config, storage).poll_once()
            items = storage.list_items()

    assert [r.printer_id for r in readings] == ["latex360", "lj4100", "brother", "kyocera"]
    assert all(r.online for r in readings)
    # Every printer's supplies land on the shelf list, keyed to their printer.
    assert {i.printer_id for i in items} == {"latex360", "lj4100", "brother", "kyocera"}
    assert len([i for i in items if i.printer_id == "brother"]) == 7


def test_readings_keep_config_order_regardless_of_response_speed(tmp_path):
    """Concurrent polling must not reorder the dashboard."""
    from printer_monitor.config import SnmpSettings
    from printer_monitor.service import MonitorService

    with FakeAgent(BROTHER_COLOR_MFP) as fast:
        config = AppConfig(
            printers=[
                # A dead printer first: it takes the full timeout, so if order
                # followed completion it would end up last.
                PrinterConfig(
                    id="slow",
                    name="Unplugged",
                    host="127.0.0.1",
                    snmp=SnmpSettings(port=9, timeout=0.6, retries=0),
                ),
                PrinterConfig(
                    id="fast",
                    name="Brother",
                    host=fast.host,
                    snmp=SnmpSettings(port=fast.port, timeout=1.0, retries=0),
                ),
            ],
            alerts=AlertSettings(popup_enabled=False, email_enabled=False, inventory_alerts=False),
        )
        with Storage(tmp_path / "order.db") as storage:
            readings = MonitorService(config, storage).poll_once()

    assert [r.printer_id for r in readings] == ["slow", "fast"]
    assert not readings[0].online
    assert readings[1].online


def test_duplicate_printer_ids_are_both_still_polled(tmp_path):
    """Two entries can slugify to the same id; neither may vanish from a cycle."""
    from printer_monitor.config import SnmpSettings
    from printer_monitor.service import MonitorService

    with FakeAgent(BROTHER_COLOR_MFP) as one, FakeAgent(KYOCERA_MONO_MFP) as two:
        config = AppConfig(
            printers=[
                PrinterConfig(
                    id="office-mfp",
                    name="Office MFP",
                    host=one.host,
                    snmp=SnmpSettings(port=one.port, timeout=1.0, retries=0),
                ),
                PrinterConfig(
                    id="office-mfp",  # same id, different machine
                    name="Office MFP",
                    host=two.host,
                    snmp=SnmpSettings(port=two.port, timeout=1.0, retries=0),
                ),
            ],
            alerts=AlertSettings(popup_enabled=False, email_enabled=False, inventory_alerts=False),
        )
        with Storage(tmp_path / "dupe.db") as storage:
            readings = MonitorService(config, storage).poll_once()

    assert len(readings) == 2
    assert {r.host for r in readings} == {one.host, two.host}
    assert {r.model for r in readings} == {"Brother MFC-L8900CDW", "ECOSYS M2540dn"}


def test_probe_reports_a_non_hp_printer_clearly():
    with FakeAgent(BROTHER_COLOR_MFP) as agent:
        result = probe_printer(printer_for(agent, "generic"))
    assert result["ok"]
    assert "Brother MFC-L8900CDW" in str(result["message"])
    assert "7 supplies" in str(result["message"])
