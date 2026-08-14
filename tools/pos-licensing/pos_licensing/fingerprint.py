"""Machine fingerprint.

A stable identifier for "this till, this box" so a single-seat license can
be bound to one machine. Built from OS-level machine IDs (with the network
MAC as a fallback) and hashed, so no raw hardware identifiers ever leave
the machine — only the hash is sent to the license server.
"""

from __future__ import annotations

import hashlib
import platform
import sys
import uuid


def _machine_id() -> str:
    if sys.platform.startswith("win"):
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as key:
                return str(winreg.QueryValueEx(key, "MachineGuid")[0])
        except OSError:
            pass
    else:
        for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                with open(path, "r", encoding="ascii") as fh:
                    value = fh.read().strip()
                if value:
                    return value
            except OSError:
                continue
    # Last resort: the primary MAC address. Less stable (USB adapters), but
    # better than nothing on stripped-down systems.
    return f"mac:{uuid.getnode():012x}"


def fingerprint() -> str:
    """Hex fingerprint for this machine (32 chars)."""
    raw = "|".join((_machine_id(), platform.system()))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def hostname() -> str:
    """Human-readable name shown in the vendor's admin list."""
    return platform.node() or "unknown"
