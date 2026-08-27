"""Network discovery: range parsing, probing, and what counts as a printer."""

from __future__ import annotations

import time

import pytest

from printer_monitor import discovery
from printer_monitor.config import AppConfig, PrinterConfig

from .fake_agent import FakeAgent
from .mibs import BROTHER_COLOR_MFP, LASERJET_4100, LATEX_360, NETWORK_SWITCH


# ---------------------------------------------------------------------------
# Range parsing
# ---------------------------------------------------------------------------


def test_cidr_expands_to_usable_hosts():
    hosts = discovery.hosts_in("192.168.1.0/24")
    assert len(hosts) == 254
    assert hosts[0] == "192.168.1.1"
    assert hosts[-1] == "192.168.1.254"


def test_small_cidr():
    assert discovery.hosts_in("10.0.0.0/30") == ["10.0.0.1", "10.0.0.2"]


def test_single_address():
    assert discovery.hosts_in("192.168.1.50") == ["192.168.1.50"]


def test_short_range():
    hosts = discovery.hosts_in("10.0.0.5-8")
    assert hosts == ["10.0.0.5", "10.0.0.6", "10.0.0.7", "10.0.0.8"]


def test_full_range():
    assert discovery.hosts_in("10.0.0.5-10.0.0.7") == ["10.0.0.5", "10.0.0.6", "10.0.0.7"]


def test_a_single_host_cidr_still_yields_that_host():
    assert discovery.hosts_in("192.168.1.50/32") == ["192.168.1.50"]


def test_backwards_range_is_rejected():
    with pytest.raises(ValueError, match="before the start"):
        discovery.hosts_in("10.0.0.9-2")


def test_oversized_scan_is_refused():
    """A /16 is 65k hosts — refuse rather than hammer the network."""
    with pytest.raises(ValueError, match="too many"):
        discovery.hosts_in("10.0.0.0/16")


def test_oversized_scan_is_refused_without_expanding_it():
    """The size check must come before the expansion.

    A mistyped /8 is 16.7 million addresses: building the list first took ~28
    seconds and hundreds of megabytes before refusing, which looks like a hang.
    """
    started = time.monotonic()
    with pytest.raises(ValueError, match="too many"):
        discovery.hosts_in("10.0.0.0/8")
    assert time.monotonic() - started < 1.0

    started = time.monotonic()
    with pytest.raises(ValueError, match="too many"):
        discovery.hosts_in("10.0.0.1-10.255.255.254")
    assert time.monotonic() - started < 1.0


@pytest.mark.parametrize("bad", ["", "   ", "not-an-ip", "192.168.1.0/99", "999.1.1.1"])
def test_junk_is_rejected(bad):
    with pytest.raises(ValueError):
        discovery.hosts_in(bad)


# ---------------------------------------------------------------------------
# Probing one host
# ---------------------------------------------------------------------------


def test_probe_identifies_a_printer():
    with FakeAgent(LATEX_360) as agent:
        found = discovery.probe_host(agent.host, port=agent.port, timeout=1.0)

    assert found is not None
    assert found.host == agent.host
    assert found.model == "HP Latex 360"
    assert found.serial == "MY7BD1802X"
    assert found.supply_count == 12
    assert found.version == "2c"
    assert found.display_name == "HP Latex 360"
    assert "HP 831 Latex Cyan" in found.supply_names


def test_probe_falls_back_to_v1():
    with FakeAgent(LASERJET_4100, versions=("1",)) as agent:
        found = discovery.probe_host(agent.host, port=agent.port, timeout=1.0)
    assert found is not None
    assert found.version == "1"
    assert found.model == "HP LaserJet 4100 Series"


def test_probe_ignores_a_non_printer():
    """A switch answers SNMP happily — it must not be offered as a printer."""
    with FakeAgent(NETWORK_SWITCH) as agent:
        assert discovery.probe_host(agent.host, port=agent.port, timeout=1.0) is None


def test_probe_returns_none_for_silence():
    assert discovery.probe_host("127.0.0.1", port=9, timeout=0.2) is None


def test_probe_tries_each_community():
    with FakeAgent(BROTHER_COLOR_MFP, community="office") as agent:
        assert discovery.probe_host(agent.host, port=agent.port, timeout=0.6) is None
        found = discovery.probe_host(
            agent.host, communities=["public", "office"], port=agent.port, timeout=0.6
        )
    assert found is not None
    assert found.community == "office"


# ---------------------------------------------------------------------------
# Sweeping
# ---------------------------------------------------------------------------


def test_scan_finds_the_printer_and_skips_the_switch():
    """Scanning localhost's ports stands in for scanning a subnet."""
    with FakeAgent(BROTHER_COLOR_MFP) as printer, FakeAgent(NETWORK_SWITCH) as switch:
        printer_hit = discovery.scan("127.0.0.1", port=printer.port, timeout=1.0)
        switch_hit = discovery.scan("127.0.0.1", port=switch.port, timeout=1.0)

    assert len(printer_hit) == 1
    assert printer_hit[0].model == "Brother MFC-L8900CDW"
    assert switch_hit == []


def test_scan_reports_progress():
    seen: list[tuple[int, int]] = []
    discovery.scan(
        "10.255.255.0/30",
        timeout=0.15,
        on_progress=lambda done, total, found: seen.append((done, total)),
    )
    assert [d for d, _ in seen] == [1, 2]
    assert {t for _, t in seen} == {2}


def test_scan_can_be_stopped_early():
    calls = {"n": 0}

    def should_stop() -> bool:
        calls["n"] += 1
        return True  # stop after the very first result

    discovery.scan("10.255.255.0/28", timeout=0.15, should_stop=should_stop)
    assert calls["n"] >= 1


def test_scan_of_an_empty_range_finds_nothing():
    assert discovery.scan("10.255.255.1", timeout=0.15) == []


# ---------------------------------------------------------------------------
# Turning a find into config
# ---------------------------------------------------------------------------


def test_to_config_carries_the_discovered_settings():
    with FakeAgent(LATEX_360) as agent:
        found = discovery.probe_host(agent.host, port=agent.port, timeout=1.0)
    assert found is not None

    printer = found.to_config()
    assert printer.name == "HP Latex 360"
    assert printer.host == found.host
    assert printer.profile == "hp_latex"
    assert printer.snmp.version == "2c"
    assert printer.snmp.community == "public"
    # The port it was actually found on, not the default.
    assert printer.snmp.port == agent.port
    assert printer.enabled


def test_to_config_defaults_to_the_standard_port():
    found = discovery.DiscoveredPrinter(host="10.0.0.9", version="2c", community="public")
    assert found.to_config().snmp.port == 161


def test_to_config_avoids_clashing_ids():
    found = discovery.DiscoveredPrinter(host="10.0.0.9", version="2c", community="public")
    found.model = "HP LaserJet 4100"
    first = found.to_config(existing_ids=[])
    second = found.to_config(existing_ids=["hp-laserjet-4100"])
    third = found.to_config(existing_ids=["hp-laserjet-4100", "hp-laserjet-4100-2"])
    assert first.id == "hp-laserjet-4100"
    assert second.id == "hp-laserjet-4100-2"
    assert third.id == "hp-laserjet-4100-3"


def test_display_name_falls_back_through_the_options():
    bare = discovery.DiscoveredPrinter(host="10.0.0.9", version="2c", community="public")
    assert bare.display_name == "10.0.0.9"

    bare.sys_descr = "Some Printer Co. Model 5\nfirmware 1.2"
    assert bare.display_name == "Some Printer Co. Model 5"

    bare.sys_name = "OFFICE-MFP"
    assert bare.display_name == "OFFICE-MFP"

    bare.model = "Model 5 MFP"
    assert bare.display_name == "Model 5 MFP"


def test_new_printers_filters_out_the_known_ones():
    discovered = [
        discovery.DiscoveredPrinter(host="10.0.0.1", version="2c", community="public"),
        discovery.DiscoveredPrinter(host="10.0.0.2", version="2c", community="public"),
    ]
    existing = [PrinterConfig(id="a", name="A", host="10.0.0.1")]
    assert [p.host for p in discovery.new_printers(discovered, existing)] == ["10.0.0.2"]


def test_new_printers_ignores_configured_entries_with_no_host():
    discovered = [discovery.DiscoveredPrinter(host="10.0.0.1", version="2c", community="public")]
    existing = [PrinterConfig(id="blank", name="Not set up yet", host="")]
    assert len(list(discovery.new_printers(discovered, existing))) == 1


# ---------------------------------------------------------------------------
# Model identification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "description,expected",
    [
        ("HP Latex 360 Printer", "hp_latex"),
        ("HP DesignJet Z6", "hp_latex"),
        ("HP LaserJet 4100 Series; JETDIRECT", "hp_laserjet"),
        ("HP Color LaserJet MFP M480f", "hp_laserjet"),
        ("Brother MFC-L8900CDW series", "generic"),
        ("Kyocera ECOSYS M2540dn", "generic"),
        ("Xerox VersaLink C405", "generic"),
        ("", "generic"),
    ],
)
def test_profile_guessing(description, expected):
    assert discovery.guess_profile(description) == expected


@pytest.mark.parametrize(
    "description",
    [
        "Brother MFC-L8900CDW series",
        "Canon iR-ADV C3530",
        "EPSON WorkForce Pro",
        "RICOH Aficio MP C3003",
        "KONICA MINOLTA bizhub C258",
        "Xerox WorkCentre 6605",
        "Lexmark MX611de",
        "HP ETHERNET MULTI-ENVIRONMENT, JETDIRECT",
    ],
)
def test_vendor_names_are_recognised_without_a_printer_mib(description):
    assert discovery.looks_like_a_printer(description, has_printer_mib=False)


@pytest.mark.parametrize(
    "description",
    [
        "24-Port Gigabit Smart Managed Switch",
        "Linux server 5.15.0",
        "APC Smart-UPS 1500",
        "",
    ],
)
def test_other_kit_is_not_mistaken_for_a_printer(description):
    assert not discovery.looks_like_a_printer(description, has_printer_mib=False)


@pytest.mark.parametrize(
    "description",
    [
        "Nokia 7750 SR-7",  # contains "oki"
        "Ubuntu 22.04 (Canonical Ltd)",  # contains "canon"
        "Ricohshire County Council asset tag 12",  # "ricoh" mid-word
        "sharpening-service v2",  # "sharp" mid-word
    ],
)
def test_vendor_names_must_be_whole_words(description):
    """Substring matching would drag half the network into the printer list."""
    assert not discovery.looks_like_a_printer(description, has_printer_mib=False)


def test_vendor_names_still_match_next_to_punctuation():
    for description in ("OKI-B432dn", "printer/MFP, model 7", "brother_mfc"):
        assert discovery.looks_like_a_printer(description, has_printer_mib=False), description


def test_the_printer_mib_settles_it_regardless_of_the_description():
    assert discovery.looks_like_a_printer("Unlabelled device", has_printer_mib=True)


def test_local_subnet_guess_is_a_usable_network():
    guess = discovery.local_subnet_guess()
    if guess is None:  # no route out of the sandbox
        pytest.skip("no outbound interface to guess from")
    assert guess.endswith("/24")
    assert len(discovery.hosts_in(guess)) == 254


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_scan_command_lists_what_it_finds(tmp_path, capsys):
    from printer_monitor.cli import main

    with FakeAgent(BROTHER_COLOR_MFP) as agent:
        path = tmp_path / "config.json"
        AppConfig(printers=[]).save(path)
        code = main(
            [
                "--config",
                str(path),
                "--db",
                str(tmp_path / "d.db"),
                "scan",
                "127.0.0.1",
                "--port",
                str(agent.port),
            ]
        )

    out = capsys.readouterr().out
    assert code == 0
    assert "Found 1 printer(s)" in out
    assert "Brother MFC-L8900CDW" in out
    assert "7 supplies" in out
    assert "--add" in out  # tells the user how to actually add it
    assert AppConfig.load(path).printers == []  # nothing added without --add


def test_scan_add_writes_the_printers_and_seeds_their_supplies(tmp_path, capsys):
    from printer_monitor.cli import main
    from printer_monitor.storage import Storage

    db = tmp_path / "d.db"
    with FakeAgent(BROTHER_COLOR_MFP) as agent:
        path = tmp_path / "config.json"
        AppConfig(printers=[]).save(path)
        code = main(
            [
                "--config",
                str(path),
                "--db",
                str(db),
                "scan",
                "127.0.0.1",
                "--port",
                str(agent.port),
                "--add",
            ]
        )

    assert code == 0
    assert "Added Brother MFC-L8900CDW" in capsys.readouterr().out

    saved = AppConfig.load(path)
    assert len(saved.printers) == 1
    assert saved.printers[0].id == "brother-mfc-l8900cdw"
    assert saved.printers[0].host == "127.0.0.1"

    # The shelf list is built from the printer's real supply names.
    with Storage(db) as storage:
        names = {item.name for item in storage.list_items()}
    assert "Cyan Toner Cartridge" in names
    assert "Waste Toner Box" in names


def test_scan_add_skips_printers_already_configured(tmp_path, capsys):
    from printer_monitor.cli import main

    with FakeAgent(BROTHER_COLOR_MFP) as agent:
        path = tmp_path / "config.json"
        AppConfig(
            printers=[PrinterConfig(id="existing", name="Already there", host="127.0.0.1")]
        ).save(path)
        main(
            [
                "--config",
                str(path),
                "--db",
                str(tmp_path / "d.db"),
                "scan",
                "127.0.0.1",
                "--port",
                str(agent.port),
                "--add",
            ]
        )

    assert "already being monitored" in capsys.readouterr().out
    assert len(AppConfig.load(path).printers) == 1


def test_scan_command_reports_an_empty_sweep(tmp_path, capsys):
    from printer_monitor.cli import main

    path = tmp_path / "config.json"
    AppConfig(printers=[]).save(path)
    code = main(
        [
            "--config",
            str(path),
            "--db",
            str(tmp_path / "d.db"),
            "scan",
            "127.0.0.1",
            "--port",
            "9",
            "--timeout",
            "0.2",
        ]
    )
    assert code == 1
    assert "No printers answered" in capsys.readouterr().out


def test_scan_command_rejects_an_oversized_range(tmp_path, capsys):
    from printer_monitor.cli import main

    path = tmp_path / "config.json"
    AppConfig(printers=[]).save(path)
    assert (
        main(["--config", str(path), "--db", str(tmp_path / "d.db"), "scan", "10.0.0.0/8"]) == 2
    )
    assert "too many" in capsys.readouterr().err
