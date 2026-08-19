"""Everything about how this PC is set up, gathered before it gets wiped.

Files are the easy half of a rebuild. The hard half is all the configuration
that lives nowhere you can copy: which printers point at which IP, the Wi-Fi
password nobody has written down since 2019, the BitLocker recovery key that
turns the old drive into a brick without it.

Each probe is isolated. A machine missing a PowerShell module, or an account
without the rights to read something, loses that one section and nothing else.
Every probe is read-only.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Callable

from . import appdetect, screengrab
from .platformutil import IS_WINDOWS, human_bytes

# Stops a console window flashing up for every probe; we are a windowed app.
CREATE_NO_WINDOW = 0x08000000

# Deliberately short. Every probe here answers in a second or two on a
# healthy machine; a longer wait means something is wedged, and the
# whole point is to record what we can and move on rather than leave
# someone watching a progress bar before a reinstall.
DEFAULT_TIMEOUT = 30


@dataclass
class Section:
    key: str
    title: str
    body: str = ""
    error: str = ""
    sensitive: bool = False
    note: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and bool(self.body.strip())


@dataclass
class SysSnapshot:
    sections: list[Section] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    monitors: list[str] = field(default_factory=list)
    holds_secrets: bool = False

    def add(self, section: Section) -> None:
        self.sections.append(section)
        if section.sensitive and section.ok:
            self.holds_secrets = True

    def section(self, key: str) -> Section | None:
        for entry in self.sections:
            if entry.key == key:
                return entry
        return None

    @property
    def failed(self) -> list[Section]:
        return [s for s in self.sections if s.error]


ProgressCallback = Callable[[str], None]


# --------------------------------------------------------------------------
# Running things
# --------------------------------------------------------------------------

def _run(command: list[str], timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str]:
    """Run a command, returning (output, error). Never raises."""
    if not IS_WINDOWS:
        return "", "only available on Windows"
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW, errors="replace")
    except FileNotFoundError:
        return "", f"{command[0]} is not available on this PC"
    except subprocess.TimeoutExpired:
        return "", f"timed out after {timeout} seconds"
    except OSError as exc:
        return "", str(exc)
    output = (completed.stdout or "").strip()
    if completed.returncode != 0 and not output:
        return "", (completed.stderr or "").strip() or \
            f"exited with code {completed.returncode}"
    return output, ""


def _powershell(script: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str]:
    """Run a PowerShell snippet.

    PowerShell rather than wmic: wmic is deprecated and no longer present on
    current Windows 11 builds, so anything built on it silently returns
    nothing on exactly the machines this needs to work on.
    """
    return _run(["powershell", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-Command", script], timeout)


# --------------------------------------------------------------------------
# Probes
# --------------------------------------------------------------------------

@dataclass
class Probe:
    key: str
    title: str
    script: str
    sensitive: bool = False
    note: str = ""
    timeout: int = DEFAULT_TIMEOUT


PROBES: list[Probe] = [
    Probe("computer", "This computer",
          "Get-CimInstance Win32_ComputerSystem | "
          "Select-Object Name,Manufacturer,Model,SystemType,"
          "TotalPhysicalMemory,Domain,Workgroup,UserName | Format-List"),

    Probe("windows", "Windows version",
          "Get-CimInstance Win32_OperatingSystem | "
          "Select-Object Caption,Version,BuildNumber,OSArchitecture,"
          "InstallDate,LastBootUpTime,SystemDrive,RegisteredUser | Format-List"),

    Probe("product_key", "Windows product key (from the BIOS)",
          "(Get-CimInstance -ClassName SoftwareLicensingService)."
          "OA3xOriginalProductKey",
          sensitive=True,
          note="The key embedded in this machine's firmware. A clean install "
               "of the same Windows edition usually activates on its own, but "
               "keep this in case it does not."),

    Probe("bitlocker", "Drive encryption and recovery keys",
          "Get-BitLockerVolume | ForEach-Object {\n"
          "  'Drive ' + $_.MountPoint + '  status=' + $_.VolumeStatus +\n"
          "    '  protection=' + $_.ProtectionStatus +\n"
          "    '  method=' + $_.EncryptionMethod\n"
          "  $_.KeyProtector | ForEach-Object {\n"
          "    '    ' + $_.KeyProtectorType + '  ' + $_.RecoveryPassword\n"
          "  }\n"
          "}",
          sensitive=True,
          note="If any drive shows as encrypted, you CANNOT read it after a "
               "reset without the recovery password printed here. This is the "
               "single most important thing on this page."),

    Probe("cpu", "Processor",
          "Get-CimInstance Win32_Processor | Select-Object Name,"
          "NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed | Format-List"),

    Probe("memory", "Memory sticks fitted",
          "Get-CimInstance Win32_PhysicalMemory | Select-Object BankLabel,"
          "Capacity,Speed,Manufacturer,PartNumber | Format-Table -AutoSize"),

    Probe("graphics", "Graphics and displays",
          "Get-CimInstance Win32_VideoController | Select-Object Name,"
          "DriverVersion,DriverDate,CurrentHorizontalResolution,"
          "CurrentVerticalResolution,CurrentRefreshRate | Format-List"),

    Probe("disks", "Drives fitted",
          "Get-CimInstance Win32_DiskDrive | Select-Object Model,InterfaceType,"
          "Size,SerialNumber | Format-Table -AutoSize; "
          "Get-Volume | Select-Object DriveLetter,FileSystemLabel,FileSystem,"
          "Size,SizeRemaining | Format-Table -AutoSize"),

    Probe("printers", "Printers and cutters",
          "Get-Printer | Select-Object Name,DriverName,PortName,Shared,"
          "Location,Comment | Format-List; "
          "'--- ports ---'; "
          "Get-PrinterPort | Select-Object Name,Description,PrinterHostAddress,"
          "PortNumber | Format-Table -AutoSize; "
          "'--- drivers ---'; "
          "Get-PrinterDriver | Select-Object Name,Manufacturer,DriverVersion | "
          "Format-Table -AutoSize",
          note="Note the port addresses. Network printers and RIPs have to be "
               "pointed at the same IP again after a rebuild."),

    Probe("network", "Network adapters",
          "Get-NetAdapter | Select-Object Name,InterfaceDescription,Status,"
          "MacAddress,LinkSpeed | Format-Table -AutoSize; "
          "'--- addresses ---'; "
          "Get-NetIPConfiguration | Format-List"),

    Probe("mapped_drives", "Mapped network drives",
          "net use",
          note="Shared folders that were mapped to a drive letter."),

    Probe("users", "Accounts on this PC",
          "Get-LocalUser | Select-Object Name,Enabled,LastLogon,Description | "
          "Format-Table -AutoSize"),

    Probe("startup", "Programs that start with Windows",
          "Get-CimInstance Win32_StartupCommand | Select-Object Name,Command,"
          "Location,User | Format-List"),

    Probe("services", "Services set to run",
          "Get-Service | Where-Object {$_.StartType -ne 'Disabled'} | "
          "Select-Object Name,DisplayName,Status,StartType | "
          "Sort-Object DisplayName | Format-Table -AutoSize"),

    Probe("tasks", "Scheduled tasks you added",
          "Get-ScheduledTask | Where-Object {$_.State -ne 'Disabled' -and "
          "$_.TaskPath -notlike '\\Microsoft\\*'} | Select-Object TaskName,"
          "TaskPath,State | Format-Table -AutoSize"),

    Probe("regional", "Time zone, language and keyboard",
          "Get-TimeZone | Select-Object Id,DisplayName | Format-List; "
          "Get-Culture | Select-Object Name,DisplayName | Format-List; "
          "Get-WinUserLanguageList | Select-Object LanguageTag,Autonym,"
          "InputMethodTips | Format-List"),

    Probe("power", "Power plan", "powercfg /list"),
]


# --------------------------------------------------------------------------
# Collection
# --------------------------------------------------------------------------

def _installed_programs_section(detection: appdetect.Detection) -> Section:
    if not detection.programs:
        return Section("programs", "Installed programs",
                       error="could not read the installed-program list")
    lines = [f"{len(detection.programs)} programs installed", ""]
    width = max(len(p.name) for p in detection.programs)
    width = min(width, 60)
    for program in detection.programs:
        publisher = f"  ({program.publisher})" if program.publisher else ""
        lines.append(f"{program.name[:60].ljust(width)}{publisher}")
    return Section("programs", "Installed programs", body="\n".join(lines),
                   note="Reinstall these from their own installers or your "
                        "licence portal. This list is a checklist, not a "
                        "backup of the programs themselves.")


def _associations_section(detection: appdetect.Detection) -> Section:
    if not detection.registered:
        return Section("associations", "What opens which file type",
                       error="no file associations could be read")
    lines = [f"{ext}   {description}"
             for ext, description in sorted(detection.registered.items())]
    return Section("associations", "What opens which file type",
                   body="\n".join(lines))


def _fonts_section() -> Section:
    folders = []
    if IS_WINDOWS:
        folders.append(os.path.join(os.environ.get("WINDIR", "C:\\Windows"),
                                    "Fonts"))
        local = os.environ.get("LOCALAPPDATA")
        if local:
            folders.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
    names: list[str] = []
    for folder in folders:
        try:
            names.extend(sorted(os.listdir(folder)))
        except OSError:
            continue
    if not names:
        return Section("fonts", "Fonts installed",
                       error="the font folders could not be listed")
    return Section("fonts", "Fonts installed",
                   body=f"{len(names)} font files\n\n" + "\n".join(names),
                   note="Fonts bought for a job are rarely re-downloadable. "
                        "The files themselves are backed up too if the Fonts "
                        "category was ticked.")


def _monitors_section() -> tuple[Section, list[str]]:
    monitors = screengrab.list_monitors()
    if not monitors:
        return (Section("monitors", "Screen layout",
                        error="the display layout could not be read"), [])
    described = [monitor.describe() for monitor in monitors]
    return (Section("monitors", "Screen layout", body="\n".join(described),
                    note="Which screen sat where, so the arrangement can be "
                         "set up the same way again."),
            described)


def _export_wifi(folder: str) -> Section:
    """Export every saved wireless profile, passwords included."""
    if not IS_WINDOWS:
        return Section("wifi", "Wi-Fi networks and passwords",
                       error="only available on Windows", sensitive=True)
    os.makedirs(folder, exist_ok=True)
    listing, error = _run(["netsh", "wlan", "show", "profiles"])
    if error and not listing:
        return Section("wifi", "Wi-Fi networks and passwords", error=error,
                       sensitive=True)
    _run(["netsh", "wlan", "export", "profile", "key=clear",
          f"folder={folder}"])
    exported = []
    try:
        exported = sorted(name for name in os.listdir(folder)
                          if name.lower().endswith(".xml"))
    except OSError:
        pass
    body = listing
    if exported:
        body += ("\n\nExported profiles (each XML holds the password in "
                 "plain text):\n" + "\n".join(f"  {name}" for name in exported))
    return Section("wifi", "Wi-Fi networks and passwords", body=body,
                   sensitive=True,
                   note="The XML files in SystemSnapshot\\WiFi can be imported "
                        "on the rebuilt PC with:  netsh wlan add profile "
                        "filename=\"<file>\"")


REGISTRY_EXPORTS = [
    ("explorer-settings",
     r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"),
    ("desktop-preferences", r"HKCU\Control Panel\Desktop"),
    ("mouse-and-keyboard", r"HKCU\Control Panel\Mouse"),
    ("regional-settings", r"HKCU\Control Panel\International"),
    ("installed-apps-list",
     r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("run-at-startup",
     r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"),
    ("run-at-startup-all-users",
     r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
]


def _export_registry(folder: str) -> tuple[Section, list[str]]:
    if not IS_WINDOWS:
        return (Section("registry", "Windows preference keys",
                        error="only available on Windows"), [])
    os.makedirs(folder, exist_ok=True)
    written: list[str] = []
    problems: list[str] = []
    for name, key in REGISTRY_EXPORTS:
        path = os.path.join(folder, f"{name}.reg")
        _output, error = _run(["reg", "export", key, path, "/y"], timeout=45)
        if error:
            problems.append(f"{key}: {error}")
        elif os.path.isfile(path):
            written.append(path)
    body = "\n".join(f"{os.path.basename(p)}" for p in written)
    if not written:
        return (Section("registry", "Windows preference keys",
                        error="; ".join(problems) or "nothing exported"), [])
    if problems:
        body += "\n\nCould not export:\n" + "\n".join(problems)
    return (Section("registry", "Windows preference keys", body=body,
                    note="Double-clicking a .reg file on the rebuilt PC puts "
                         "those settings back. Import only the ones you want; "
                         "they are plain text and can be read first."),
            written)


def _wallpaper(folder: str) -> tuple[Section, list[str]]:
    if not IS_WINDOWS:
        return (Section("wallpaper", "Desktop wallpaper",
                        error="only available on Windows"), [])
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Control Panel\Desktop") as key:
            source, _ = winreg.QueryValueEx(key, "WallPaper")
    except (ImportError, OSError):
        return (Section("wallpaper", "Desktop wallpaper",
                        error="the wallpaper setting could not be read"), [])
    if not source or not os.path.isfile(source):
        return (Section("wallpaper", "Desktop wallpaper",
                        body=str(source or "(none set)")), [])
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, os.path.basename(source))
    try:
        shutil.copy2(source, target)
    except OSError as exc:
        return (Section("wallpaper", "Desktop wallpaper",
                        body=source, error=str(exc)), [])
    return (Section("wallpaper", "Desktop wallpaper",
                    body=f"{source}\n\nCopied to SystemSnapshot\\Wallpaper\\"
                         f"{os.path.basename(source)}"),
            [target])


def _desktop_listing() -> Section:
    from .platformutil import personal_folders
    desktop = personal_folders().get("Desktop")
    if not desktop or not os.path.isdir(desktop):
        return Section("desktop", "What was on the Desktop",
                       error="the Desktop folder could not be found")
    rows: list[str] = []
    try:
        for name in sorted(os.listdir(desktop)):
            full = os.path.join(desktop, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            kind = "folder" if os.path.isdir(full) else human_bytes(size)
            rows.append(f"{name}   ({kind})")
    except OSError as exc:
        return Section("desktop", "What was on the Desktop", error=str(exc))
    return Section("desktop", "What was on the Desktop",
                   body="\n".join(rows) or "(empty)")


def collect(folder: str, progress: ProgressCallback | None = None,
            cancel: threading.Event | None = None,
            include_screenshots: bool = True,
            detection: appdetect.Detection | None = None) -> SysSnapshot:
    """Gather everything into *folder* and return it for the report."""
    snapshot = SysSnapshot()
    os.makedirs(folder, exist_ok=True)

    def say(message: str) -> None:
        if progress is not None:
            progress(message)

    def stopped() -> bool:
        return cancel is not None and cancel.is_set()

    if include_screenshots:
        say("Taking pictures of the desktop...")
        try:
            shots = screengrab.capture_all()
            snapshot.screenshots = screengrab.save_shots(
                shots, os.path.join(folder, "Screenshots"))
            snapshot.files.extend(snapshot.screenshots)
        except Exception as exc:            # never let a grab kill the run
            snapshot.add(Section("screenshots", "Pictures of the desktop",
                                 error=str(exc)))

    monitors_section, described = _monitors_section()
    snapshot.add(monitors_section)
    snapshot.monitors = described

    for probe in PROBES:
        if stopped():
            return snapshot
        say(f"Recording {probe.title.lower()}...")
        output, error = _powershell(probe.script, probe.timeout)
        snapshot.add(Section(probe.key, probe.title, body=output, error=error,
                             sensitive=probe.sensitive, note=probe.note))

    if stopped():
        return snapshot

    say("Listing installed programs...")
    found = detection if detection is not None else appdetect.detect()
    snapshot.add(_installed_programs_section(found))
    snapshot.add(_associations_section(found))

    say("Listing fonts...")
    snapshot.add(_fonts_section())
    snapshot.add(_desktop_listing())

    if stopped():
        return snapshot

    say("Saving Wi-Fi profiles...")
    snapshot.add(_export_wifi(os.path.join(folder, "WiFi")))

    say("Exporting Windows preferences...")
    registry_section, registry_files = _export_registry(
        os.path.join(folder, "Registry"))
    snapshot.add(registry_section)
    snapshot.files.extend(registry_files)

    wallpaper_section, wallpaper_files = _wallpaper(
        os.path.join(folder, "Wallpaper"))
    snapshot.add(wallpaper_section)
    snapshot.files.extend(wallpaper_files)

    return snapshot
