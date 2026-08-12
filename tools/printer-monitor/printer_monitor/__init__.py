"""Printer Supply Monitor — watch HP printer supply levels, track spares, alert when low.

Built for an HP Latex 360 and an HP LaserJet 4100, but any printer that
implements the standard Printer MIB (RFC 3805) over SNMP works the same way.

Stdlib only: no third-party packages to install.
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = [
    "__version__",
    "AppConfig",
    "MonitorService",
    "Storage",
    "poll_printer",
]


def __getattr__(name: str):
    # Lazy so `import printer_monitor` stays cheap and tkinter-free.
    if name == "AppConfig":
        from .config import AppConfig

        return AppConfig
    if name == "MonitorService":
        from .service import MonitorService

        return MonitorService
    if name == "Storage":
        from .storage import Storage

        return Storage
    if name == "poll_printer":
        from .poller import poll_printer

        return poll_printer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
