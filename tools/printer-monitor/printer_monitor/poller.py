"""Polls printers over SNMP and returns a full PrinterReading.

The supplies/input/alert tables are walked rather than fetched by fixed index,
so whatever a given printer reports is what gets monitored — 6 inks plus
optimizer, printheads and a maintenance cartridge on the Latex 360; toner,
fuser/maintenance kit and trays on the LaserJet 4100.
"""

from __future__ import annotations

import logging
from typing import Optional

from . import printer_mib as mib
from .config import PrinterConfig
from .models import MediaInput, PrinterAlert, PrinterReading, Supply
from .snmp import SnmpClient, SnmpError, is_missing, sniff_version

log = logging.getLogger(__name__)


def make_client(printer: PrinterConfig) -> SnmpClient:
    return SnmpClient(
        host=printer.host,
        community=printer.snmp.community,
        port=printer.snmp.port,
        version=printer.snmp.version,
        timeout=printer.snmp.timeout,
        retries=printer.snmp.retries,
    )


def poll_printer(printer: PrinterConfig, client: Optional[SnmpClient] = None) -> PrinterReading:
    """Poll one printer. Never raises — transport problems land in ``error``."""
    reading = PrinterReading(
        printer_id=printer.id, printer_name=printer.name, host=printer.host
    )
    if not printer.host:
        reading.error = "No host/IP configured"
        return reading

    try:
        # Inside the try: a bad version/port in the config would otherwise raise
        # out of here and abort the whole poll cycle.
        client = client or make_client(printer)
        _read_identity(client, reading)
        _read_status(client, reading)
        reading.supplies = read_supplies(client)
        reading.inputs = read_inputs(client)
        reading.alerts = read_alerts(client)
        reading.online = True
    except SnmpError as exc:
        reading.online = False
        reading.error = str(exc)
        log.info("poll failed for %s (%s): %s", printer.name, printer.host, exc)
    except Exception as exc:  # noqa: BLE001 - a malformed reply must not kill the loop
        reading.online = False
        reading.error = f"{type(exc).__name__}: {exc}"
        log.exception("unexpected error polling %s", printer.name)
    return reading


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def _read_identity(client: SnmpClient, reading: PrinterReading) -> None:
    # First GET doubles as the reachability check, so let its errors propagate.
    descr = client.get_one(mib.SYS_DESCR)
    reading.model = _clean(client.get_one(mib.PRT_GENERAL_PRINTER_NAME)) or _first_line(descr)
    reading.serial = _clean(client.get_one(mib.PRT_GENERAL_SERIAL_NUMBER))
    reading.system_name = _clean(client.get_one(mib.SYS_NAME))
    uptime = client.get_one(mib.SYS_UPTIME)
    reading.uptime_ticks = uptime if isinstance(uptime, int) else None


def _read_status(client: SnmpClient, reading: PrinterReading) -> None:
    status = _quiet_get(client, mib.HR_PRINTER_STATUS)
    reading.printer_status_code = status if isinstance(status, int) else None

    device = _quiet_get(client, mib.HR_DEVICE_STATUS)
    reading.device_status_code = device if isinstance(device, int) else None

    # Read the raw octets: this object is a bit field, and the text decoding
    # would trim the NUL/space bytes that carry the flags.
    try:
        errors = client.get_raw(mib.HR_PRINTER_DETECTED_ERROR_STATE)
    except SnmpError:
        errors = None
    reading.detected_errors = mib.decode_detected_errors(errors)

    # Front-panel text: handy context in an email ("Load substrate", "13.20 jam").
    console_lines: list[str] = []
    try:
        for value in client.walk_column(mib.PRT_CONSOLE_DISPLAY_BUFFER, limit=16).values():
            text = _clean(value)
            if text:
                console_lines.append(text)
    except SnmpError:
        pass
    reading.console_message = " | ".join(console_lines)

    page_counts = _quiet_walk(client, mib.PRT_MARKER_LIFE_COUNT)
    counts = [v for v in page_counts.values() if isinstance(v, int) and v >= 0]
    reading.page_count = max(counts) if counts else None


def read_supplies(client: SnmpClient) -> list[Supply]:
    """Walk prtMarkerSuppliesTable into Supply objects."""
    descriptions = _quiet_walk(client, mib.PRT_SUPPLIES_DESCRIPTION)
    levels = _quiet_walk(client, mib.PRT_SUPPLIES_LEVEL)
    capacities = _quiet_walk(client, mib.PRT_SUPPLIES_MAX_CAPACITY)
    types = _quiet_walk(client, mib.PRT_SUPPLIES_TYPE)
    classes = _quiet_walk(client, mib.PRT_SUPPLIES_CLASS)
    units = _quiet_walk(client, mib.PRT_SUPPLIES_UNIT)
    colorant_idx = _quiet_walk(client, mib.PRT_SUPPLIES_COLORANT_INDEX)
    colorants = _quiet_walk(client, mib.PRT_COLORANT_VALUE)

    # Index keys are (marker, supply); a level with no description still counts.
    keys = sorted(set(descriptions) | set(levels))
    supplies: list[Supply] = []
    for key in keys:
        supply = Supply(
            index=key[-1] if key else 0,
            description=_clean(descriptions.get(key)),
            type_code=_as_int(types.get(key), 2),
            class_code=_as_int(classes.get(key), 3),
            unit_code=_as_int(units.get(key), mib.UNIT_PERCENT),
            level_raw=_as_int(levels.get(key), mib.LEVEL_UNKNOWN),
            max_capacity_raw=_as_int(capacities.get(key), mib.LEVEL_UNKNOWN),
            colorant=_lookup_colorant(colorant_idx.get(key), colorants, key),
        )
        # A supplies row with no description and no readable level is padding.
        if not supply.description and supply.level_raw == mib.LEVEL_UNKNOWN:
            continue
        supplies.append(supply)
    return supplies


def _lookup_colorant(
    colorant_index: object, colorants: dict[tuple[int, ...], object], supply_key: tuple[int, ...]
) -> Optional[str]:
    """Resolve prtMarkerSuppliesColorantIndex against the colorant table."""
    if not isinstance(colorant_index, int) or colorant_index <= 0:
        return None
    marker = supply_key[0] if len(supply_key) > 1 else 1
    for candidate in ((marker, colorant_index), (colorant_index,)):
        value = colorants.get(candidate)
        if value is not None:
            return _clean(value) or None
    return None


def read_inputs(client: SnmpClient) -> list[MediaInput]:
    """Walk prtInputTable — paper trays, or the substrate roll on the Latex."""
    names = _quiet_walk(client, mib.PRT_INPUT_NAME)
    descriptions = _quiet_walk(client, mib.PRT_INPUT_DESCRIPTION)
    media = _quiet_walk(client, mib.PRT_INPUT_MEDIA_NAME)
    levels = _quiet_walk(client, mib.PRT_INPUT_CURRENT_LEVEL)
    capacities = _quiet_walk(client, mib.PRT_INPUT_MAX_CAPACITY)
    statuses = _quiet_walk(client, mib.PRT_INPUT_STATUS)
    units = _quiet_walk(client, mib.PRT_INPUT_DIM_UNIT)

    inputs: list[MediaInput] = []
    for key in sorted(set(levels) | set(names) | set(descriptions)):
        name = _clean(names.get(key))
        description = _clean(descriptions.get(key))
        if not name and not description and key not in levels:
            continue
        inputs.append(
            MediaInput(
                index=key[-1] if key else 0,
                name=name or description or f"Tray {key[-1] if key else 0}",
                description=description,
                media_name=_clean(media.get(key)),
                level_raw=_as_int(levels.get(key), mib.LEVEL_UNKNOWN),
                max_capacity_raw=_as_int(capacities.get(key), mib.LEVEL_UNKNOWN),
                status_code=_as_int(statuses.get(key), 0),
                unit_code=_as_int(units.get(key), 8),
            )
        )
    return inputs


def read_alerts(client: SnmpClient, limit: int = 40) -> list[PrinterAlert]:
    """Walk prtAlertTable — the printer's own active warnings/errors."""
    descriptions = _quiet_walk(client, mib.PRT_ALERT_DESCRIPTION, limit=limit)
    severities = _quiet_walk(client, mib.PRT_ALERT_SEVERITY, limit=limit)
    groups = _quiet_walk(client, mib.PRT_ALERT_GROUP, limit=limit)
    codes = _quiet_walk(client, mib.PRT_ALERT_CODE, limit=limit)

    alerts: list[PrinterAlert] = []
    for key in sorted(set(descriptions) | set(severities)):
        description = _clean(descriptions.get(key))
        code = _as_int(codes.get(key), 0)
        if not description and not code:
            continue
        alerts.append(
            PrinterAlert(
                index=key[-1] if key else 0,
                severity_code=_as_int(severities.get(key), 1),
                group_code=_as_int(groups.get(key), 1),
                code=code,
                description=description or f"Alert code {code}",
            )
        )
    return alerts


# ---------------------------------------------------------------------------
# Discovery / diagnostics
# ---------------------------------------------------------------------------


def probe_printer(printer: PrinterConfig) -> dict[str, object]:
    """Try to reach a printer, auto-detecting the SNMP version.

    Returns ``{"ok", "version", "message", "reading"}``. The GUI's Test button
    uses ``version`` to fix up a mis-set config (the 4100's JetDirect card is
    frequently SNMPv1-only).
    """
    if not printer.host:
        return {"ok": False, "version": None, "message": "No host/IP set", "reading": None}

    try:
        client = make_client(printer)
    except ValueError as exc:
        # e.g. an unsupported SNMP version typed into the config file.
        return {"ok": False, "version": None, "message": f"Bad SNMP settings: {exc}", "reading": None}

    if not client.probe():
        detected = sniff_version(
            printer.host, community=printer.snmp.community, port=printer.snmp.port, timeout=2.0
        )
        if detected is None:
            return {
                "ok": False,
                "version": None,
                "message": (
                    f"No SNMP reply from {printer.host}:{printer.snmp.port}. Check the IP, "
                    "that SNMP is enabled in the printer's web page, and the community string."
                ),
                "reading": None,
            }
        client = SnmpClient(
            host=printer.host,
            community=printer.snmp.community,
            port=printer.snmp.port,
            version=detected,
            timeout=printer.snmp.timeout,
            retries=printer.snmp.retries,
        )
    else:
        detected = client.version_label

    reading = poll_printer(printer, client=client)
    if not reading.online:
        return {
            "ok": False,
            "version": detected,
            "message": reading.error or "Poll failed",
            "reading": reading,
        }

    supply_count = len(reading.supplies)
    readable = sum(1 for s in reading.supplies if s.remaining_percent is not None)
    message = (
        f"Connected to {reading.model or printer.host} over SNMPv{detected}. "
        f"Found {supply_count} supplies ({readable} reporting a percentage) "
        f"and {len(reading.inputs)} media inputs."
    )
    return {"ok": True, "version": detected, "message": message, "reading": reading}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _quiet_get(client: SnmpClient, oid: str):
    """GET that returns None instead of raising when an object is absent."""
    try:
        return client.get_one(oid)
    except SnmpError:
        return None


def _quiet_walk(client: SnmpClient, base: str, limit: int = 200) -> dict[tuple[int, ...], object]:
    try:
        return client.walk_column(base, limit=limit)
    except SnmpError as exc:
        log.debug("walk of %s failed: %s", base, exc)
        return {}


def _as_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _clean(value: object) -> str:
    if value is None or is_missing(value):
        return ""
    if isinstance(value, bytes):
        return value.decode("latin-1", errors="replace").replace("\x00", "").strip()
    return str(value).replace("\x00", "").strip()


def _first_line(value: object) -> str:
    text = _clean(value)
    return text.splitlines()[0].strip() if text else ""
