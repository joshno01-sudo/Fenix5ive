"""Command line entry points.

    printer-monitor              # open the window
    printer-monitor check        # poll once, print levels, exit
    printer-monitor monitor      # headless loop (for a service / Task Scheduler)
    printer-monitor discover IP  # dump every supply OID a printer reports
    printer-monitor stock        # show / adjust the supply list from a terminal
    printer-monitor test-email
"""

from __future__ import annotations

import argparse
import copy
import logging
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import inventory
from .config import AppConfig, PrinterConfig, SnmpSettings, default_config_path, default_db_path
from .notify import Notifier
from .poller import make_client, poll_printer, probe_printer
from .service import MonitorService, run_forever, summarize_readings
from .storage import Storage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="printer-monitor",
        description="Monitor HP printer supply levels, track spares, alert when low.",
    )
    parser.add_argument("--config", type=Path, help="path to config.json")
    parser.add_argument("--db", type=Path, help="path to the monitor database")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("gui", help="open the monitor window (default)")

    check = sub.add_parser("check", help="poll every printer once and print the levels")
    check.add_argument(
        "--notify",
        action="store_true",
        help="also send popup/email alerts for anything below threshold",
    )
    check.add_argument("--printer", help="only this printer id")

    sub.add_parser("monitor", help="run the polling loop in the foreground (headless)")

    discover = sub.add_parser(
        "discover", help="dump the supplies a printer reports (for troubleshooting)"
    )
    discover.add_argument("host", help="printer IP or hostname")
    discover.add_argument("--community", default="public")
    discover.add_argument("--version", default=None, choices=["1", "2c"])
    discover.add_argument("--port", type=int, default=161)
    discover.add_argument("--raw", action="store_true", help="also dump raw OIDs and values")

    stock = sub.add_parser("stock", help="view or adjust the on-hand supply list")
    stock.add_argument("--add", metavar="ITEM", help="item name to adjust")
    stock.add_argument("--printer", default="", help="printer id the item belongs to")
    stock.add_argument("--plus", type=int, default=0, help="increase on-hand count by N")
    stock.add_argument("--minus", type=int, default=0, help="decrease on-hand count by N")
    stock.add_argument("--seed", action="store_true", help="load the starter lists")
    stock.add_argument("--csv", action="store_true", help="print as CSV")

    sub.add_parser("test-email", help="send a test message with the configured SMTP settings")

    addp = sub.add_parser("add-printer", help="add a printer to the config from the terminal")
    addp.add_argument("name")
    addp.add_argument("host")
    addp.add_argument(
        "--profile", default="generic", choices=["hp_latex", "hp_laserjet", "generic"]
    )
    addp.add_argument("--community", default="public")
    addp.add_argument("--version", default="2c", choices=["1", "2c"])
    addp.add_argument("--port", type=int, default=161)

    sub.add_parser("paths", help="print where the config and database live")

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    command = args.command or "gui"

    if command == "paths":
        print(f"config:   {args.config or default_config_path()}")
        print(f"database: {args.db or default_db_path()}")
        return 0

    if command == "discover":
        return cmd_discover(args)

    config = AppConfig.load(args.config)
    db_path = args.db or default_db_path()

    if command == "gui":
        try:
            from .gui.app import run_gui
        except ImportError as exc:
            print(f"Cannot start the window: {exc}", file=sys.stderr)
            print("Install tkinter, or use 'printer-monitor check' instead.", file=sys.stderr)
            return 2
        return run_gui(config, db_path=db_path)

    with Storage(db_path) as storage:
        if command == "check":
            return cmd_check(config, storage, args)
        if command == "monitor":
            return cmd_monitor(config, storage)
        if command == "stock":
            return cmd_stock(config, storage, args)
        if command == "test-email":
            return cmd_test_email(config)
        if command == "add-printer":
            return cmd_add_printer(config, storage, args)

    parser.print_help()
    return 1


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_check(config: AppConfig, storage: Storage, args) -> int:
    printers = config.enabled_printers()
    if getattr(args, "printer", None):
        printers = [p for p in printers if p.id == args.printer]
    if not printers:
        print(
            "No printers configured. Add one with:\n"
            "  printer-monitor add-printer \"HP Latex 360\" 192.168.1.50 --profile hp_latex",
            file=sys.stderr,
        )
        return 2

    if args.notify:
        # Honour --printer here too: the service polls whatever the config says
        # is enabled, so narrow the in-memory copy (never saved to disk).
        scoped = copy.copy(config)
        scoped.printers = printers
        readings = MonitorService(scoped, storage).poll_once()
    else:
        readings = [poll_printer(printer) for printer in printers]
        for reading in readings:
            storage.record_reading(reading)

    print(summarize_readings(readings))

    low = []
    for reading in readings:
        for supply in reading.supplies:
            percent = supply.remaining_percent
            if percent is None:
                continue
            warning, _critical = config.thresholds.for_supply(reading.printer_id, supply.key)
            if percent <= warning:
                low.append(f"{reading.printer_name}: {supply.display_name} at {percent:.0f}%")
    if low:
        print("\nBelow threshold:")
        for line in low:
            print(f"  * {line}")

    return 0 if all(r.online for r in readings) else 1


def cmd_monitor(config: AppConfig, storage: Storage) -> int:
    if not config.enabled_printers():
        print("No printers configured.", file=sys.stderr)
        return 2
    print(
        f"Monitoring {len(config.enabled_printers())} printer(s) every "
        f"{config.poll_interval_seconds}s. Ctrl+C to stop."
    )
    run_forever(config, storage)
    return 0


def cmd_discover(args) -> int:
    """Poll a printer directly and show everything it reports."""
    version = args.version
    printer = PrinterConfig(
        id="discover",
        name=args.host,
        host=args.host,
        snmp=SnmpSettings(community=args.community, version=version or "2c", port=args.port),
    )
    result = probe_printer(printer)
    print(result["message"])
    if not result["ok"]:
        return 1

    reading = result["reading"]
    print()
    print(summarize_readings([reading]))

    if args.raw:
        from . import printer_mib as mib

        detected = str(result["version"])
        printer.snmp.version = detected
        client = make_client(printer)
        print("\nRaw supplies table:")
        for label, oid in (
            ("description", mib.PRT_SUPPLIES_DESCRIPTION),
            ("level", mib.PRT_SUPPLIES_LEVEL),
            ("max capacity", mib.PRT_SUPPLIES_MAX_CAPACITY),
            ("type", mib.PRT_SUPPLIES_TYPE),
            ("class", mib.PRT_SUPPLIES_CLASS),
            ("unit", mib.PRT_SUPPLIES_UNIT),
        ):
            print(f"\n  {label} ({oid})")
            for index, value in sorted(client.walk_column(oid).items()):
                dotted = ".".join(str(i) for i in index)
                print(f"    .{dotted} = {value!r}")
    return 0


def cmd_stock(config: AppConfig, storage: Storage, args) -> int:
    if args.seed:
        added = 0
        for printer in config.printers:
            added += inventory.seed_defaults(storage, printer.id, printer.profile)
        print(f"Added {added} starter item(s).")

    if args.add:
        item = storage.find_item(args.printer, args.add)
        if item is None:
            from .models import SupplyItem

            item = storage.upsert_item(SupplyItem(name=args.add, printer_id=args.printer))
            print(f"Created “{item.name}”.")
        delta = int(args.plus) - int(args.minus)
        if delta:
            assert item.id is not None
            updated = storage.adjust_quantity(item.id, delta, "cli")
            if updated:
                print(f"{updated.name}: {updated.quantity} on hand ({delta:+d}).")

    items = storage.list_items()
    if args.csv:
        print(inventory.to_csv(items), end="")
        return 0

    if not items:
        print("Supply list is empty. Run: printer-monitor stock --seed")
        return 0

    width = max(len(item.name) for item in items)
    print(f"\n{'ITEM'.ljust(width)}  ON HAND  REORDER  PRINTER")
    for item in items:
        flag = "  <-- ORDER" if item.needs_reorder else ""
        printer_label = item.printer_id or "shop"
        print(
            f"{item.name.ljust(width)}  {item.quantity:>7}  {item.reorder_at:>7}  "
            f"{printer_label}{flag}"
        )

    stats = inventory.summarize(items)
    print(
        f"\n{stats['total_rows']} items, {stats['total_units']} units on hand, "
        f"{stats['needs_reorder']} need reordering."
    )
    return 0


def cmd_test_email(config: AppConfig) -> int:
    if not config.email.is_configured():
        print(
            "Email is not configured. Set the SMTP server, From address and recipients "
            "in Settings, or edit config.json.",
            file=sys.stderr,
        )
        return 2
    try:
        Notifier(config.email, popup_enabled=False, email_enabled=True).send_test_email()
    except Exception as exc:  # noqa: BLE001 - report whatever SMTP said
        print(f"Failed: {exc}", file=sys.stderr)
        return 1
    print(f"Test email sent to {', '.join(config.email.to_addrs)}.")
    return 0


def cmd_add_printer(config: AppConfig, storage: Storage, args) -> int:
    from .config import slugify

    printer_id = slugify(args.name)
    existing = {p.id for p in config.printers}
    suffix = 2
    while printer_id in existing:
        printer_id = f"{slugify(args.name)}-{suffix}"
        suffix += 1

    printer = PrinterConfig(
        id=printer_id,
        name=args.name,
        host=args.host,
        profile=args.profile,
        snmp=SnmpSettings(
            community=args.community, version=args.version, port=getattr(args, "port", 161)
        ),
    )
    config.printers.append(printer)

    result = probe_printer(printer)
    print(result["message"])
    if result["ok"] and result["version"] != printer.snmp.version:
        printer.snmp.version = str(result["version"])
        print(f"Set SNMP version to {printer.snmp.version}.")

    path = config.save()
    print(f"Saved {printer.name} ({printer.host}) to {path}")

    added = inventory.seed_defaults(storage, printer.id, printer.profile)
    if added:
        print(f"Added {added} starter supply-list item(s).")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
