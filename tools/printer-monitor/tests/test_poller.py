"""End-to-end polling against fake Latex 360 and LaserJet 4100 agents."""

from __future__ import annotations

import pytest

from printer_monitor.config import PrinterConfig, SnmpSettings
from printer_monitor.poller import poll_printer, probe_printer
from printer_monitor.service import summarize_readings

from .fake_agent import FakeAgent
from .mibs import LASERJET_4100, LATEX_360


def printer_for(agent: FakeAgent, profile: str = "generic", version: str = "2c") -> PrinterConfig:
    return PrinterConfig(
        id="test",
        name="Test Printer",
        host=agent.host,
        profile=profile,
        snmp=SnmpSettings(
            community=agent.community, version=version, port=agent.port, timeout=1.5, retries=1
        ),
    )


@pytest.fixture
def latex_reading():
    with FakeAgent(LATEX_360) as agent:
        yield poll_printer(printer_for(agent, "hp_latex"))


@pytest.fixture
def laserjet_reading():
    """The 4100 fixture speaks SNMPv1 only, like an older JetDirect card."""
    with FakeAgent(LASERJET_4100, versions=("1",)) as agent:
        yield poll_printer(printer_for(agent, "hp_laserjet", version="1"))


# ---------------------------------------------------------------------------
# HP Latex 360
# ---------------------------------------------------------------------------


def test_latex_identity(latex_reading):
    assert latex_reading.online
    assert latex_reading.error is None
    assert latex_reading.model == "HP Latex 360"
    assert latex_reading.serial == "MY7BD1802X"
    assert latex_reading.page_count == 148_205
    assert latex_reading.console_message == "Ready to print"
    assert latex_reading.status_text == "Idle"


def test_latex_finds_every_supply(latex_reading):
    """7 inks + 4 printheads + the maintenance cartridge."""
    assert len(latex_reading.supplies) == 12
    names = [s.display_name for s in latex_reading.supplies]
    assert "HP 831 Latex Cyan" in names
    assert "Maintenance Cartridge" in names
    assert sum(1 for n in names if n.startswith("Printhead")) == 4


def test_latex_ink_percentages(latex_reading):
    """Volume-based levels (tenths of a millilitre) convert to percent."""
    by_name = {s.display_name: s for s in latex_reading.supplies}
    assert by_name["HP 831 Latex Cyan"].remaining_percent == 70.0
    assert by_name["HP 831 Latex Magenta"].remaining_percent == 40.0
    assert by_name["HP 831 Latex Yellow"].remaining_percent == 15.0
    assert by_name["HP 831 Latex Black"].remaining_percent == 6.0
    assert by_name["HP 831 Latex Light Cyan"].remaining_percent == 100.0


def test_latex_reports_cartridge_capacity(latex_reading):
    cyan = next(s for s in latex_reading.supplies if s.display_name == "HP 831 Latex Cyan")
    assert cyan.capacity_text == "775 ml"


def test_latex_some_remaining_is_not_a_percentage(latex_reading):
    """-3 means "some left, amount unknown" and must never read as a number."""
    light_magenta = next(
        s for s in latex_reading.supplies if s.display_name == "HP 831 Latex Light Magenta"
    )
    assert light_magenta.remaining_percent is None
    assert light_magenta.level_state == "some"
    assert light_magenta.level_text == "Some remaining"


def test_maintenance_cartridge_level_is_inverted(latex_reading):
    """A receptacle reports how *full* it is; the app reports life left."""
    cartridge = next(
        s for s in latex_reading.supplies if s.display_name == "Maintenance Cartridge"
    )
    assert cartridge.is_waste
    assert cartridge.fraction_used == pytest.approx(0.82)
    assert cartridge.remaining_percent == 18.0


def test_latex_colour_detection(latex_reading):
    by_name = {s.display_name: s for s in latex_reading.supplies}
    assert by_name["HP 831 Latex Cyan"].color == "Cyan"
    # "light cyan" must win over the substring "cyan".
    assert by_name["HP 831 Latex Light Cyan"].color == "Light Cyan"
    assert by_name["HP 831 Latex Light Magenta"].color == "Light Magenta"
    assert by_name["HP 831 Latex Optimizer"].color == "Optimizer"


def test_latex_substrate_roll(latex_reading):
    assert len(latex_reading.inputs) == 1
    roll = latex_reading.inputs[0]
    assert roll.display_name == "Roll 1"
    assert roll.media_name == "Cast Vinyl 54in"
    assert roll.level_text == "Loaded"
    assert not roll.is_empty


# ---------------------------------------------------------------------------
# HP LaserJet 4100
# ---------------------------------------------------------------------------


def test_laserjet_over_snmp_v1(laserjet_reading):
    assert laserjet_reading.online
    assert laserjet_reading.model == "HP LaserJet 4100 Series"
    assert laserjet_reading.page_count == 612_884


def test_laserjet_toner_and_maintenance_kit(laserjet_reading):
    by_name = {s.display_name: s for s in laserjet_reading.supplies}
    assert by_name["Black Cartridge HP C8061X"].remaining_percent == 7.0
    # 30k of 200k impressions left.
    kit = by_name["Maintenance Kit"]
    assert kit.remaining_percent == 15.0
    assert kit.capacity_text == "200,000 impressions"


def test_laserjet_detected_error_bits(laserjet_reading):
    assert "low toner" in laserjet_reading.detected_errors
    assert "input tray empty" in laserjet_reading.detected_errors
    assert laserjet_reading.has_error_state


def test_laserjet_trays(laserjet_reading):
    by_name = {i.display_name: i for i in laserjet_reading.inputs}
    assert by_name["Tray 1"].level_text == "Loaded"
    assert by_name["Tray 2"].remaining_percent == 50.0
    assert by_name["Tray 3"].is_empty
    assert by_name["Tray 3"].level_text == "Empty"


def test_laserjet_printer_alert_table(laserjet_reading):
    descriptions = [a.description for a in laserjet_reading.alerts]
    assert "Tray 3 empty" in descriptions
    assert "Black cartridge low" in descriptions
    critical = [a for a in laserjet_reading.alerts if a.is_critical]
    assert [a.description for a in critical] == ["Tray 3 empty"]
    assert critical[0].group == "input tray"


# ---------------------------------------------------------------------------
# Failure handling and diagnostics
# ---------------------------------------------------------------------------


def test_offline_printer_does_not_raise():
    printer = PrinterConfig(
        id="dead",
        name="Unplugged",
        host="127.0.0.1",
        snmp=SnmpSettings(port=9, timeout=0.2, retries=0),
    )
    reading = poll_printer(printer)
    assert not reading.online
    assert reading.error
    assert reading.supplies == []
    assert reading.status_text == "Offline"


def test_missing_host_is_reported_without_a_network_call():
    reading = poll_printer(PrinterConfig(id="x", name="No IP", host=""))
    assert not reading.online
    assert "No host" in (reading.error or "")


def test_test_connection_autodetects_v1():
    """Configured for v2c, but the printer only speaks v1 — detect and report."""
    with FakeAgent(LASERJET_4100, versions=("1",)) as agent:
        printer = printer_for(agent, "hp_laserjet", version="2c")
        result = probe_printer(printer)
        assert result["ok"]
        assert result["version"] == "1"
        assert "SNMPv1" in str(result["message"])


def test_test_connection_reports_unreachable():
    printer = PrinterConfig(
        id="x", name="Nope", host="127.0.0.1", snmp=SnmpSettings(port=9, timeout=0.2, retries=0)
    )
    result = probe_printer(printer)
    assert not result["ok"]
    assert "No SNMP reply" in str(result["message"])


def test_summary_text_lists_levels(latex_reading):
    text = summarize_readings([latex_reading])
    assert "HP 831 Latex Cyan: 70%" in text
    assert "775 ml" in text
    assert "Maintenance Cartridge: 18%" in text
