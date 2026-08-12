"""Configuration: JSON on disk, dataclasses in memory, sane defaults."""

from __future__ import annotations

import json
import os
import re
import stat
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

APP_NAME = "printer-monitor"
ENV_CONFIG_PATH = "PRINTER_MONITOR_CONFIG"
ENV_SMTP_PASSWORD = "PRINTER_MONITOR_SMTP_PASSWORD"


def default_data_dir() -> Path:
    """Per-user data directory, honouring the usual platform conventions."""
    override = os.environ.get("PRINTER_MONITOR_HOME")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
        return Path(base) / "PrinterMonitor"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PrinterMonitor"
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / APP_NAME


def default_config_path() -> Path:
    override = os.environ.get(ENV_CONFIG_PATH)
    if override:
        return Path(override).expanduser()
    return default_data_dir() / "config.json"


def default_db_path() -> Path:
    override = os.environ.get("PRINTER_MONITOR_DB")
    if override:
        return Path(override).expanduser()
    return default_data_dir() / "monitor.db"


# ---------------------------------------------------------------------------
# Config sections
# ---------------------------------------------------------------------------


@dataclass
class SnmpSettings:
    community: str = "public"
    version: str = "2c"
    port: int = 161
    timeout: float = 3.0
    retries: int = 2


@dataclass
class PrinterConfig:
    id: str = ""
    name: str = ""
    host: str = ""
    profile: str = "generic"  # generic | hp_latex | hp_laserjet
    enabled: bool = True
    snmp: SnmpSettings = field(default_factory=SnmpSettings)
    notes: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.snmp, dict):
            self.snmp = SnmpSettings(**_filter_keys(SnmpSettings, self.snmp))
        if not self.id:
            self.id = slugify(self.name or self.host or "printer")
        if not self.name:
            self.name = self.host or self.id


@dataclass
class Thresholds:
    """Percent-remaining trip points. ``per_supply`` overrides the defaults."""

    supply_warning: int = 20
    supply_critical: int = 8
    tray_warning: int = 10
    # "<printer_id>:<supply_key>" -> {"warning": int, "critical": int}
    per_supply: dict[str, dict[str, int]] = field(default_factory=dict)

    def for_supply(self, printer_id: str, supply_key: str) -> tuple[int, int]:
        override = self.per_supply.get(f"{printer_id}:{supply_key}") or self.per_supply.get(
            supply_key
        )
        if not override:
            return self.supply_warning, self.supply_critical
        warning = int(override.get("warning", self.supply_warning))
        critical = int(override.get("critical", self.supply_critical))
        return warning, critical

    @staticmethod
    def _override_key(printer_id: str, supply_key: str) -> str:
        # No printer means "this supply on every printer", stored bare — a
        # ":supply" key would never match the lookup above.
        return f"{printer_id}:{supply_key}" if printer_id else supply_key

    def set_supply_override(
        self, printer_id: str, supply_key: str, warning: int, critical: int
    ) -> None:
        self.per_supply[self._override_key(printer_id, supply_key)] = {
            "warning": int(warning),
            "critical": int(critical),
        }

    def clear_supply_override(self, printer_id: str, supply_key: str) -> None:
        self.per_supply.pop(self._override_key(printer_id, supply_key), None)


@dataclass
class AlertSettings:
    popup_enabled: bool = True
    email_enabled: bool = False
    # Don't re-nag about the same supply more often than this.
    repeat_hours: float = 12.0
    # Warn when a shelf item's on-hand count hits its reorder point.
    inventory_alerts: bool = True
    # Alert when a printer stops answering SNMP for this many consecutive polls.
    offline_after_failures: int = 3
    offline_alerts: bool = True
    # Forward the printer's own critical alerts (jams, door open, service).
    printer_error_alerts: bool = True
    # Hysteresis: a supply must climb this far above its threshold before it can
    # alert again, so a cartridge hovering at the trip point doesn't spam.
    clear_margin_percent: float = 5.0


@dataclass
class EmailSettings:
    smtp_host: str = ""
    smtp_port: int = 587
    encryption: str = "starttls"  # starttls | ssl | none
    username: str = ""
    password: str = ""  # prefer the env var; see password_or_env()
    from_addr: str = ""
    to_addrs: list[str] = field(default_factory=list)
    subject_prefix: str = "[Printer Monitor]"
    timeout: float = 20.0

    def password_or_env(self) -> str:
        """Env var wins over the config file, so the password can stay off disk."""
        return os.environ.get(ENV_SMTP_PASSWORD) or self.password

    def is_configured(self) -> bool:
        return bool(self.smtp_host and self.from_addr and self.to_addrs)


@dataclass
class AppConfig:
    poll_interval_seconds: int = 300
    printers: list[PrinterConfig] = field(default_factory=list)
    thresholds: Thresholds = field(default_factory=Thresholds)
    alerts: AlertSettings = field(default_factory=AlertSettings)
    email: EmailSettings = field(default_factory=EmailSettings)
    history_days: int = 180
    path: Optional[Path] = None

    # -- nested dict -> dataclass ------------------------------------------

    def __post_init__(self) -> None:
        if self.printers and isinstance(self.printers[0], dict):
            self.printers = [
                PrinterConfig(**_filter_keys(PrinterConfig, p)) for p in self.printers  # type: ignore[arg-type]
            ]
        if isinstance(self.thresholds, dict):
            self.thresholds = Thresholds(**_filter_keys(Thresholds, self.thresholds))
        if isinstance(self.alerts, dict):
            self.alerts = AlertSettings(**_filter_keys(AlertSettings, self.alerts))
        if isinstance(self.email, dict):
            self.email = EmailSettings(**_filter_keys(EmailSettings, self.email))
        self.poll_interval_seconds = max(30, int(self.poll_interval_seconds))

    # -- lookup ------------------------------------------------------------

    def printer(self, printer_id: str) -> Optional[PrinterConfig]:
        for printer in self.printers:
            if printer.id == printer_id:
                return printer
        return None

    def enabled_printers(self) -> list[PrinterConfig]:
        return [p for p in self.printers if p.enabled and p.host]

    # -- persistence -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("path", None)
        return data

    def save(self, path: Path | str | None = None) -> Path:
        target = Path(path or self.path or default_config_path())
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), indent=2, sort_keys=False)
        tmp = target.with_suffix(target.suffix + ".tmp")
        # Create the temp file owner-only *before* writing: it carries the SMTP
        # password, and chmod-after-rename would leave a readable window.
        try:
            handle = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        except OSError:
            tmp.write_text(payload + "\n", encoding="utf-8")
        else:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(payload + "\n")
        _restrict_permissions(tmp)
        tmp.replace(target)
        _restrict_permissions(target)
        self.path = target
        return target

    @classmethod
    def load(cls, path: Path | str | None = None) -> "AppConfig":
        target = Path(path or default_config_path())
        if not target.exists():
            config = default_config()
            config.path = target
            return config
        raw = json.loads(target.read_text(encoding="utf-8") or "{}")
        config = cls(**_filter_keys(cls, raw))
        config.path = target
        return config


def _filter_keys(cls, data: dict[str, Any]) -> dict[str, Any]:
    """Drop unknown keys so an older/newer config file still loads."""
    valid = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in valid}


def _restrict_permissions(path: Path) -> None:
    """0600 the config — it may hold an SMTP password."""
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # Windows / odd filesystems: best effort


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return slug or "printer"


# ---------------------------------------------------------------------------
# Defaults for this shop: the Latex 360 and the LaserJet 4100
# ---------------------------------------------------------------------------


def default_config() -> AppConfig:
    return AppConfig(
        poll_interval_seconds=300,
        printers=[
            PrinterConfig(
                id="latex360",
                name="HP Latex 360",
                host="",
                profile="hp_latex",
                snmp=SnmpSettings(community="public", version="2c"),
                notes="Wide-format. Set the host to the printer's IP, then Test.",
            ),
            PrinterConfig(
                id="lj4100",
                name="HP LaserJet 4100",
                host="",
                profile="hp_laserjet",
                # Older JetDirect cards only answer SNMPv1; the Test button
                # auto-detects and fixes this.
                snmp=SnmpSettings(community="public", version="1"),
                notes="Office laser. Set the host to the printer's IP, then Test.",
            ),
        ],
    )
