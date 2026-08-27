"""Find printers on the office network.

Sweeps a subnet with a one-packet SNMP GET and reports which hosts answer as
printers. Saves hunting for IP addresses when there are more than a couple of
machines to add.

Only read-only SNMP GETs are sent, to the range the user asks for.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator, Optional

from . import printer_mib as mib
from .config import PrinterConfig, SnmpSettings, slugify
from .snmp import SnmpClient, SnmpError

log = logging.getLogger(__name__)

# Sweeping is one packet per host per version, so a short timeout is fine on a
# LAN. Anything slower than this is unlikely to be a printer worth polling.
SWEEP_TIMEOUT = 1.0
MAX_WORKERS = 64
# Guard rail: /22 is 1022 hosts, already a big office. Bigger is a mistake.
MAX_HOSTS = 1024


@dataclass
class DiscoveredPrinter:
    host: str
    version: str
    community: str
    # Carried through to the saved config: a printer found on a non-standard
    # port must not be written back with the default 161.
    port: int = 161
    sys_descr: str = ""
    sys_name: str = ""
    model: str = ""
    serial: str = ""
    supply_count: int = 0
    supply_names: list[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        """Best human name available, in preference order."""
        for candidate in (self.model, self.sys_name, _first_line(self.sys_descr)):
            if candidate:
                return candidate
        return self.host

    @property
    def profile(self) -> str:
        return guess_profile(f"{self.model} {self.sys_descr} {self.sys_name}")

    @property
    def summary(self) -> str:
        bits = [self.host, self.display_name]
        if self.supply_count:
            bits.append(f"{self.supply_count} supplies")
        else:
            bits.append("no supply data")
        bits.append(f"SNMPv{self.version}")
        return "  ·  ".join(bits)

    def to_config(self, existing_ids: Iterable[str] = ()) -> PrinterConfig:
        """Build a PrinterConfig, avoiding an id that is already taken."""
        taken = set(existing_ids)
        base = slugify(self.display_name)
        printer_id = base
        suffix = 2
        while printer_id in taken:
            printer_id = f"{base}-{suffix}"
            suffix += 1
        return PrinterConfig(
            id=printer_id,
            name=self.display_name,
            host=self.host,
            profile=self.profile,
            snmp=SnmpSettings(
                community=self.community, version=self.version, port=self.port
            ),
            notes=f"Found by network scan. {self.sys_descr}"[:200],
        )


# ---------------------------------------------------------------------------
# Model identification
# ---------------------------------------------------------------------------

# Matched against sysDescr / printer name, lowercased. Order matters: the more
# specific patterns come first.
_PROFILE_PATTERNS: list[tuple[str, str]] = [
    (r"\blatex\b|\bdesignjet\b|\bscitex\b|\bpagewide xl\b", "hp_latex"),
    (r"\blaserjet\b|\bcolor laserjet\b", "hp_laserjet"),
]


def guess_profile(text: str) -> str:
    """Pick a starting profile from the printer's own description.

    Only used for the starter supply list and the label in Settings — level
    reading is identical for every profile, because it all comes from the
    standard Printer MIB.
    """
    haystack = (text or "").lower()
    for pattern, profile in _PROFILE_PATTERNS:
        if re.search(pattern, haystack):
            return profile
    return "generic"


# Vendor names as they appear in sysDescr, for the "looks like a printer" test
# on devices that answer SNMP but expose no Printer MIB.
_PRINTER_KEYWORDS = (
    "printer",
    "laserjet",
    "officejet",
    "deskjet",
    "designjet",
    "pagewide",
    "latex",
    "brother",
    "kyocera",
    "lexmark",
    "ricoh",
    "xerox",
    "canon",
    "epson",
    "sharp",
    "konica",
    "minolta",
    "toshiba",
    "oki",
    "samsung",
    "jetdirect",
    "mfp",
    "imagerunner",
    "workcentre",
    "versalink",
    "altalink",
    "aficio",
    "bizhub",
    "ecosys",
    "taskalfa",
    "workforce",
)


# Whole words only. Bare substring matching would drag in anything containing a
# vendor name by accident — "oki" inside "Nokia", "canon" inside "Canonical".
# The boundary is letters/digits rather than \b, so an underscore still counts
# as a separator: device names like "brother_mfc" are common.
_PRINTER_KEYWORD_RE = re.compile(
    r"(?<![a-z0-9])(" + "|".join(re.escape(word) for word in _PRINTER_KEYWORDS) + r")(?![a-z0-9])"
)


def looks_like_a_printer(sys_descr: str, has_printer_mib: bool) -> bool:
    """A device counts as a printer if it serves the Printer MIB or says so."""
    if has_printer_mib:
        return True
    return bool(_PRINTER_KEYWORD_RE.search((sys_descr or "").lower()))


# ---------------------------------------------------------------------------
# Sweeping
# ---------------------------------------------------------------------------


def hosts_in(target: str) -> list[str]:
    """Expand ``192.168.1.0/24``, ``10.0.0.5-40`` or a single address.

    Raises ValueError for anything unparseable or larger than MAX_HOSTS.
    """
    target = (target or "").strip()
    if not target:
        raise ValueError("no network given")

    if "/" in target:
        network = ipaddress.ip_network(target, strict=False)
        hosts = [str(ip) for ip in network.hosts()] or [str(network.network_address)]
    elif "-" in target:
        start_text, _, end_text = target.partition("-")
        start = ipaddress.ip_address(start_text.strip())
        end_text = end_text.strip()
        # Accept both "10.0.0.5-40" and "10.0.0.5-10.0.0.40".
        if "." not in end_text:
            prefix = start_text.strip().rsplit(".", 1)[0]
            end_text = f"{prefix}.{end_text}"
        end = ipaddress.ip_address(end_text)
        if int(end) < int(start):
            raise ValueError("the end of the range is before the start")
        hosts = [
            str(ipaddress.ip_address(value)) for value in range(int(start), int(end) + 1)
        ]
    else:
        hosts = [str(ipaddress.ip_address(target))]

    if len(hosts) > MAX_HOSTS:
        raise ValueError(
            f"{len(hosts)} addresses is too many to scan at once (limit {MAX_HOSTS}). "
            "Use a smaller range, such as a /24."
        )
    return hosts


def local_subnet_guess() -> Optional[str]:
    """Best guess at this machine's own /24, to pre-fill the scan box."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No packet is actually sent; this just picks the outbound interface.
        sock.connect(("192.0.2.1", 9))  # TEST-NET-1, guaranteed unroutable
        address = sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()
    try:
        interface = ipaddress.ip_interface(f"{address}/24")
    except ValueError:
        return None
    return str(interface.network)


def probe_host(
    host: str,
    communities: Iterable[str] = ("public",),
    port: int = 161,
    timeout: float = SWEEP_TIMEOUT,
    deep: bool = True,
) -> Optional[DiscoveredPrinter]:
    """Check one address. Returns None when it isn't a reachable printer."""
    for community in communities:
        for version in ("2c", "1"):
            client = SnmpClient(
                host,
                community=community,
                port=port,
                version=version,
                timeout=timeout,
                retries=0,
            )
            try:
                sys_descr = client.get_one(mib.SYS_DESCR)
            except SnmpError:
                continue
            if sys_descr is None:
                continue

            found = DiscoveredPrinter(
                host=host,
                version=version,
                community=community,
                port=port,
                sys_descr=str(sys_descr),
            )
            if deep:
                _fill_details(client, found)
            has_mib = bool(found.model or found.supply_count)
            if not looks_like_a_printer(found.sys_descr, has_mib):
                return None
            return found
    return None


def _fill_details(client: SnmpClient, found: DiscoveredPrinter) -> None:
    """Second pass: the Printer MIB bits that confirm it really is a printer."""
    try:
        found.model = _text(client.get_one(mib.PRT_GENERAL_PRINTER_NAME))
        found.serial = _text(client.get_one(mib.PRT_GENERAL_SERIAL_NUMBER))
        found.sys_name = _text(client.get_one(mib.SYS_NAME))
    except SnmpError:
        pass
    try:
        descriptions = client.walk_column(mib.PRT_SUPPLIES_DESCRIPTION, limit=40)
        levels = client.walk_column(mib.PRT_SUPPLIES_LEVEL, limit=40)
        found.supply_count = len(set(descriptions) | set(levels))
        found.supply_names = [_text(v) for v in descriptions.values() if _text(v)]
    except SnmpError:
        pass
    # Deliberately no page-count walk here: a sweep touches every address on
    # the subnet, and the full picture is gathered by the first real poll once
    # the printer is actually added.


def scan(
    target: str,
    communities: Iterable[str] = ("public",),
    port: int = 161,
    timeout: float = SWEEP_TIMEOUT,
    on_progress: Optional[Callable[[int, int, Optional[DiscoveredPrinter]], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> list[DiscoveredPrinter]:
    """Scan ``target`` and return the printers found, in address order.

    ``on_progress`` is called as ``(done, total, found_or_none)`` after each
    host, so a UI can show a progress bar. ``should_stop`` lets it be cancelled.
    """
    hosts = hosts_in(target)
    communities = list(communities) or ["public"]
    found: list[DiscoveredPrinter] = []
    done = 0

    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, max(1, len(hosts)))) as pool:
        futures = {
            pool.submit(probe_host, host, communities, port, timeout): host for host in hosts
        }
        try:
            for future in as_completed(futures):
                done += 1
                try:
                    printer = future.result()
                except Exception:  # noqa: BLE001 - one bad host must not stop the sweep
                    log.debug("probe failed for %s", futures[future], exc_info=True)
                    printer = None
                if printer is not None:
                    found.append(printer)
                if on_progress is not None:
                    on_progress(done, len(hosts), printer)
                if should_stop is not None and should_stop():
                    break
        finally:
            if should_stop is not None and should_stop():
                for future in futures:
                    future.cancel()

    found.sort(key=lambda p: _sort_key(p.host))
    return found


def new_printers(
    discovered: Iterable[DiscoveredPrinter], existing: Iterable[PrinterConfig]
) -> Iterator[DiscoveredPrinter]:
    """Filter out anything already in the config, matched by host."""
    known = {p.host for p in existing if p.host}
    for printer in discovered:
        if printer.host not in known:
            yield printer


def _sort_key(host: str):
    try:
        return (0, int(ipaddress.ip_address(host)))
    except ValueError:
        return (1, host)


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("latin-1", errors="replace").replace("\x00", "").strip()
    return str(value).replace("\x00", "").strip()


def _first_line(text: str) -> str:
    text = _text(text)
    return text.splitlines()[0].strip() if text else ""
