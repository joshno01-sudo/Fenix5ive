"""Work out what is actually installed on this PC.

The middle panel is far more useful when it reflects the machine in front of
you rather than a generic list, so on Windows we read two things from the
registry:

* the installed-program list behind Add/Remove Programs, and
* every file extension that has a registered "open with" handler.

Both are read-only, both degrade to an empty result on any other platform or if
a key is missing, and neither is required for the program to work.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import catalog
from .platformutil import IS_WINDOWS

try:  # pragma: no cover - import guard exercised only off Windows
    import winreg  # type: ignore
except ImportError:  # pragma: no cover
    winreg = None  # type: ignore


@dataclass
class InstalledProgram:
    name: str
    publisher: str = ""
    install_location: str = ""


@dataclass
class Detection:
    programs: list[InstalledProgram] = field(default_factory=list)
    # extension -> friendly description taken from its registered handler
    registered: dict[str, str] = field(default_factory=dict)
    suggested_categories: set[str] = field(default_factory=set)

    @property
    def program_names(self) -> list[str]:
        return [p.name for p in self.programs]

    def matched_program_names(self) -> list[str]:
        """Installed programs that the catalog recognises, for display."""
        out = []
        for program in self.programs:
            lowered = program.name.lower()
            if any(needle in lowered for needle, _ in catalog.PROGRAM_HINTS):
                out.append(program.name)
        # Collapse "Adobe Illustrator 2024" / "...2025" style duplicates.
        deduped: list[str] = []
        for name in sorted(out, key=str.lower):
            if not any(name.lower().startswith(seen.lower()[:18]) for seen in deduped):
                deduped.append(name)
        return deduped


_UNINSTALL_KEYS = [
    ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKCU", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
]


def _hive(name: str):
    return winreg.HKEY_LOCAL_MACHINE if name == "HKLM" else winreg.HKEY_CURRENT_USER


def _read_value(key, name: str) -> str:
    try:
        value, _ = winreg.QueryValueEx(key, name)
        return str(value) if value is not None else ""
    except OSError:
        return ""


def installed_programs() -> list[InstalledProgram]:
    """Programs listed in Add/Remove Programs, deduplicated by name."""
    if not IS_WINDOWS or winreg is None:
        return []
    found: dict[str, InstalledProgram] = {}
    for hive_name, subkey in _UNINSTALL_KEYS:
        try:
            root = winreg.OpenKey(_hive(hive_name), subkey)
        except OSError:
            continue
        with root:
            index = 0
            while True:
                try:
                    child_name = winreg.EnumKey(root, index)
                except OSError:
                    break
                index += 1
                try:
                    child = winreg.OpenKey(root, child_name)
                except OSError:
                    continue
                with child:
                    display = _read_value(child, "DisplayName")
                    if not display:
                        continue
                    # Hidden entries are updates and runtime components, not apps.
                    if _read_value(child, "SystemComponent") == "1":
                        continue
                    found.setdefault(display, InstalledProgram(
                        name=display,
                        publisher=_read_value(child, "Publisher"),
                        install_location=_read_value(child, "InstallLocation"),
                    ))
    return sorted(found.values(), key=lambda p: p.name.lower())


def registered_extensions() -> dict[str, str]:
    """Every extension with an "open with" handler, mapped to a description.

    This is how file types belonging to software we have never heard of still
    show up in the picker with a name a human recognises.
    """
    if not IS_WINDOWS or winreg is None:
        return {}
    result: dict[str, str] = {}
    try:
        root = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "")
    except OSError:
        return {}
    with root:
        index = 0
        while True:
            try:
                name = winreg.EnumKey(root, index)
            except OSError:
                break
            index += 1
            if not name.startswith(".") or len(name) < 2:
                continue
            ext = name.lower()
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, name) as ext_key:
                    prog_id = _read_value(ext_key, "")
            except OSError:
                continue
            description = ""
            if prog_id:
                try:
                    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id) as prog_key:
                        description = _read_value(prog_key, "FriendlyTypeName") \
                            or _read_value(prog_key, "")
                except OSError:
                    description = ""
            # FriendlyTypeName is often an indirect string ("@C:\...,-101").
            if description.startswith("@"):
                description = ""
            if description:
                result[ext] = description
    return result


def detect() -> Detection:
    """Full probe. Safe to call on any platform; never raises."""
    detection = Detection()
    try:
        detection.programs = installed_programs()
    except Exception:
        detection.programs = []
    try:
        detection.registered = registered_extensions()
    except Exception:
        detection.registered = {}
    try:
        detection.suggested_categories = catalog.categories_for_programs(
            detection.program_names)
    except Exception:
        detection.suggested_categories = set()
    return detection


def describe_environment() -> str:
    """One-line summary shown in the UI header."""
    if IS_WINDOWS:
        return f"Windows - {os.environ.get('COMPUTERNAME', 'this PC')}"
    return "Development mode (not Windows)"
