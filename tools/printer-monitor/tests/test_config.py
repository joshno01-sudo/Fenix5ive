"""Config loading, saving, defaults and CLI wiring."""

from __future__ import annotations

import json
import os
import stat

import pytest

from printer_monitor.cli import main
from printer_monitor.config import (
    AppConfig,
    EmailSettings,
    PrinterConfig,
    SnmpSettings,
    Thresholds,
    default_config,
    slugify,
)

from .fake_agent import FakeAgent
from .mibs import LATEX_360


# ---------------------------------------------------------------------------
# Round-tripping
# ---------------------------------------------------------------------------


def test_missing_file_gives_the_shop_defaults(tmp_path):
    config = AppConfig.load(tmp_path / "nope.json")
    ids = [p.id for p in config.printers]
    assert ids == ["latex360", "lj4100"]
    assert config.printer("latex360").profile == "hp_latex"
    # The 4100's JetDirect card is usually v1-only, so that's the default.
    assert config.printer("lj4100").snmp.version == "1"
    assert config.enabled_printers() == []  # no IPs set yet


def test_save_and_reload(tmp_path):
    path = tmp_path / "config.json"
    config = default_config()
    config.printer("latex360").host = "10.0.0.50"
    config.thresholds.supply_warning = 25
    config.thresholds.set_supply_override("latex360", "cyan", 40, 15)
    config.email.to_addrs = ["a@b.c", "d@e.f"]
    config.save(path)

    reloaded = AppConfig.load(path)
    assert reloaded.printer("latex360").host == "10.0.0.50"
    assert reloaded.thresholds.supply_warning == 25
    assert reloaded.thresholds.for_supply("latex360", "cyan") == (40, 15)
    assert reloaded.email.to_addrs == ["a@b.c", "d@e.f"]
    assert isinstance(reloaded.printers[0], PrinterConfig)
    assert isinstance(reloaded.printers[0].snmp, SnmpSettings)


def test_saved_file_is_owner_only(tmp_path):
    """It can hold an SMTP password, so it must not be world-readable."""
    path = tmp_path / "config.json"
    default_config().save(path)
    if os.name != "nt":
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600


def test_unknown_keys_are_ignored(tmp_path):
    """A config from a newer version must still load."""
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "poll_interval_seconds": 60,
                "future_option": "whatever",
                "printers": [{"id": "p", "name": "P", "host": "1.2.3.4", "mystery": 1}],
            }
        )
    )
    config = AppConfig.load(path)
    assert config.poll_interval_seconds == 60
    assert config.printers[0].host == "1.2.3.4"


def test_empty_file_loads(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{}")
    config = AppConfig.load(path)
    assert config.printers == []
    assert config.poll_interval_seconds == 300


def test_poll_interval_has_a_floor():
    assert AppConfig(poll_interval_seconds=1).poll_interval_seconds == 30


def test_printer_id_is_derived_from_the_name():
    printer = PrinterConfig(name="HP Latex 360", host="1.2.3.4")
    assert printer.id == "hp-latex-360"


def test_printer_name_falls_back_to_the_host():
    assert PrinterConfig(host="10.0.0.9").name == "10.0.0.9"


def test_slugify():
    assert slugify("HP LaserJet 4100!") == "hp-laserjet-4100"
    assert slugify("  ") == "printer"


def test_enabled_printers_needs_a_host():
    config = AppConfig(
        printers=[
            PrinterConfig(id="a", name="A", host="1.2.3.4", enabled=True),
            PrinterConfig(id="b", name="B", host="", enabled=True),
            PrinterConfig(id="c", name="C", host="1.2.3.5", enabled=False),
        ]
    )
    assert [p.id for p in config.enabled_printers()] == ["a"]


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------


def test_threshold_defaults_and_overrides():
    thresholds = Thresholds(supply_warning=20, supply_critical=8)
    assert thresholds.for_supply("p", "cyan") == (20, 8)

    thresholds.set_supply_override("p", "cyan", 50, 25)
    assert thresholds.for_supply("p", "cyan") == (50, 25)
    assert thresholds.for_supply("other", "cyan") == (20, 8)

    thresholds.clear_supply_override("p", "cyan")
    assert thresholds.for_supply("p", "cyan") == (20, 8)


def test_partial_override_falls_back_per_field():
    thresholds = Thresholds(supply_warning=20, supply_critical=8)
    thresholds.per_supply["p:cyan"] = {"warning": 45}
    assert thresholds.for_supply("p", "cyan") == (45, 8)


def test_global_override_without_a_printer_id():
    thresholds = Thresholds()
    thresholds.per_supply["maintenance-cartridge"] = {"warning": 30, "critical": 10}
    assert thresholds.for_supply("any-printer", "maintenance-cartridge") == (30, 10)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_paths_command(capsys, tmp_path):
    assert main(["--config", str(tmp_path / "c.json"), "--db", str(tmp_path / "d.db"), "paths"]) == 0
    out = capsys.readouterr().out
    assert "c.json" in out
    assert "d.db" in out


def test_check_command_prints_levels(capsys, tmp_path):
    with FakeAgent(LATEX_360) as agent:
        config = AppConfig(
            printers=[
                PrinterConfig(
                    id="latex360",
                    name="HP Latex 360",
                    host=agent.host,
                    snmp=SnmpSettings(port=agent.port, timeout=1.0, retries=1),
                )
            ]
        )
        path = tmp_path / "config.json"
        config.save(path)

        code = main(["--config", str(path), "--db", str(tmp_path / "d.db"), "check"])

    out = capsys.readouterr().out
    assert code == 0
    assert "HP 831 Latex Cyan: 70%" in out
    assert "Below threshold:" in out
    assert "HP 831 Latex Black at 6%" in out


def test_check_command_with_no_printers_explains_itself(capsys, tmp_path):
    path = tmp_path / "config.json"
    AppConfig(printers=[]).save(path)
    code = main(["--config", str(path), "--db", str(tmp_path / "d.db"), "check"])
    assert code == 2
    assert "No printers configured" in capsys.readouterr().err


def test_check_command_returns_1_when_a_printer_is_offline(tmp_path, capsys):
    path = tmp_path / "config.json"
    AppConfig(
        printers=[
            PrinterConfig(
                id="dead",
                name="Dead",
                host="127.0.0.1",
                snmp=SnmpSettings(port=9, timeout=0.2, retries=0),
            )
        ]
    ).save(path)
    assert main(["--config", str(path), "--db", str(tmp_path / "d.db"), "check"]) == 1
    assert "OFFLINE" in capsys.readouterr().out


def test_add_printer_command(tmp_path, capsys):
    with FakeAgent(LATEX_360) as agent:
        path = tmp_path / "config.json"
        AppConfig(printers=[]).save(path)
        code = main(
            [
                "--config",
                str(path),
                "--db",
                str(tmp_path / "d.db"),
                "add-printer",
                "HP Latex 360",
                agent.host,
                "--profile",
                "hp_latex",
                "--port",
                str(agent.port),
            ]
        )

    out = capsys.readouterr().out
    assert code == 0
    assert "Connected to HP Latex 360" in out
    reloaded = AppConfig.load(path)
    assert reloaded.printers[0].id == "hp-latex-360"
    assert reloaded.printers[0].profile == "hp_latex"


def test_stock_commands(tmp_path, capsys):
    path = tmp_path / "config.json"
    db = tmp_path / "d.db"
    default_config().save(path)

    assert main(["--config", str(path), "--db", str(db), "stock", "--seed"]) == 0
    assert "starter item" in capsys.readouterr().out

    main(
        [
            "--config",
            str(path),
            "--db",
            str(db),
            "stock",
            "--add",
            "Cyan ink cartridge (HP 831, 775 ml)",
            "--printer",
            "latex360",
            "--plus",
            "3",
        ]
    )
    assert "3 on hand" in capsys.readouterr().out

    main(
        [
            "--config",
            str(path),
            "--db",
            str(db),
            "stock",
            "--add",
            "Cyan ink cartridge (HP 831, 775 ml)",
            "--printer",
            "latex360",
            "--minus",
            "1",
        ]
    )
    assert "2 on hand" in capsys.readouterr().out

    main(["--config", str(path), "--db", str(db), "stock", "--csv"])
    assert "Part number" in capsys.readouterr().out


def test_test_email_command_without_configuration(tmp_path, capsys):
    path = tmp_path / "config.json"
    AppConfig(email=EmailSettings()).save(path)
    assert main(["--config", str(path), "--db", str(tmp_path / "d.db"), "test-email"]) == 2
    assert "not configured" in capsys.readouterr().err


def test_discover_command(capsys):
    with FakeAgent(LATEX_360) as agent:
        code = main(["discover", agent.host, "--port", str(agent.port)])
    out = capsys.readouterr().out
    assert code == 0
    assert "Found 12 supplies" in out
    assert "Maintenance Cartridge: 18%" in out


def test_discover_unreachable_returns_1(capsys):
    assert main(["discover", "127.0.0.1", "--port", "9"]) == 1
    assert "No SNMP reply" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["check", "monitor", "stock", "paths"])
def test_every_subcommand_parses(command):
    from printer_monitor.cli import build_parser

    args = build_parser().parse_args([command])
    assert args.command == command
