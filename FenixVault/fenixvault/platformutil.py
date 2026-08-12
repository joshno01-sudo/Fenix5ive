"""Platform plumbing: drives, known folders, long paths, archive path mapping.

Everything Windows-specific is behind ``IS_WINDOWS`` with a POSIX fallback so the
engine can be developed and unit-tested on any machine.
"""

from __future__ import annotations

import ctypes
import getpass
import os
import platform
import shutil
import socket
import string
from dataclasses import dataclass
from typing import Iterable

IS_WINDOWS = os.name == "nt"

# Root folder inside a backup that holds the mirrored tree.
DATA_DIR_NAME = "Data"

# Bucket name used for POSIX absolute paths, which have no drive letter.
POSIX_BUCKET = "_root"

# Bucket prefix used for UNC network paths (\\server\share\...).
UNC_BUCKET = "_unc"


# --------------------------------------------------------------------------
# Long paths
# --------------------------------------------------------------------------

def long_path(path: str) -> str:
    """Return *path* in a form the OS file APIs will accept for any length.

    On Windows the classic 260-character ``MAX_PATH`` limit still applies to
    most APIs unless the path carries the extended-length prefix. Backups nest
    the original tree one level deeper, so paths that were fine on the source
    machine can easily cross the limit inside the backup folder.
    """
    if not IS_WINDOWS:
        return path
    if path.startswith("\\\\?\\"):
        return path
    abspath = os.path.abspath(path)
    if abspath.startswith("\\\\"):
        # \\server\share -> \\?\UNC\server\share
        return "\\\\?\\UNC\\" + abspath.lstrip("\\")
    return "\\\\?\\" + abspath


def short_path(path: str) -> str:
    """Strip the extended-length prefix so a path is fit to show a human."""
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[8:]
    if path.startswith("\\\\?\\"):
        return path[4:]
    return path


def norm(path: str) -> str:
    """Normalise a path for comparison and for use as a selection-model key.

    Windows paths are case-folded because the filesystem is case-insensitive;
    POSIX paths are left alone because they are not.
    """
    path = os.path.abspath(short_path(path))
    if IS_WINDOWS:
        path = path.replace("/", "\\").rstrip("\\") or path
        # Preserve the trailing separator for a bare drive root (``C:\``).
        if len(path) == 2 and path[1] == ":":
            path += "\\"
        return path.lower()
    return path.rstrip("/") or "/"


def is_ancestor(parent: str, child: str) -> bool:
    """True when *child* sits strictly underneath *parent* (both normalised)."""
    if parent == child:
        return False
    sep = "\\" if IS_WINDOWS else "/"
    if not parent.endswith(sep):
        parent += sep
    return child.startswith(parent)


def ancestors_of(path: str) -> list[str]:
    """Every ancestor of *path*, nearest first, ending with its root."""
    out: list[str] = []
    current = path
    while True:
        parent = os.path.dirname(current)
        if not parent or parent == current:
            break
        out.append(norm(parent))
        current = parent
    return out


# --------------------------------------------------------------------------
# Drives
# --------------------------------------------------------------------------

DRIVE_UNKNOWN = "unknown"
DRIVE_REMOVABLE = "removable"
DRIVE_FIXED = "fixed"
DRIVE_NETWORK = "network"
DRIVE_CDROM = "cdrom"
DRIVE_RAMDISK = "ramdisk"

_WIN_DRIVE_TYPES = {
    0: DRIVE_UNKNOWN,
    1: DRIVE_UNKNOWN,   # DRIVE_NO_ROOT_DIR
    2: DRIVE_REMOVABLE,
    3: DRIVE_FIXED,
    4: DRIVE_NETWORK,
    5: DRIVE_CDROM,
    6: DRIVE_RAMDISK,
}


@dataclass
class DriveInfo:
    path: str            # "C:\\" on Windows, "/" or "/media/usb" on POSIX
    label: str           # volume label, may be empty
    kind: str            # one of the DRIVE_* constants
    total_bytes: int
    free_bytes: int
    is_system: bool      # holds the running OS / user profile

    @property
    def display(self) -> str:
        name = self.label or ("Local Disk" if self.kind == DRIVE_FIXED else "Drive")
        return f"{self.path}  ({name})"

    @property
    def used_bytes(self) -> int:
        return max(0, self.total_bytes - self.free_bytes)


def _windows_volume_label(root: str) -> str:
    buf = ctypes.create_unicode_buffer(261)
    fs_buf = ctypes.create_unicode_buffer(261)
    serial = ctypes.c_ulong()
    max_comp = ctypes.c_ulong()
    flags = ctypes.c_ulong()
    ok = ctypes.windll.kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(root), buf, ctypes.sizeof(buf) // 2,
        ctypes.byref(serial), ctypes.byref(max_comp), ctypes.byref(flags),
        fs_buf, ctypes.sizeof(fs_buf) // 2,
    )
    return buf.value if ok else ""


def list_drives() -> list[DriveInfo]:
    """Every volume currently attached, newest mount points included."""
    return _list_drives_windows() if IS_WINDOWS else _list_drives_posix()


def _list_drives_windows() -> list[DriveInfo]:
    drives: list[DriveInfo] = []
    system_root = os.environ.get("SystemDrive", "C:").rstrip("\\").upper()
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    for index, letter in enumerate(string.ascii_uppercase):
        if not bitmask & (1 << index):
            continue
        root = f"{letter}:\\"
        kind = _WIN_DRIVE_TYPES.get(
            ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)),
            DRIVE_UNKNOWN,
        )
        if kind in (DRIVE_CDROM, DRIVE_UNKNOWN):
            # Optical and unmounted letters have nothing worth backing up and
            # querying them can spin up or block on empty drives.
            continue
        if kind == DRIVE_NETWORK:
            # A mapped drive whose server is unreachable makes disk_usage block
            # for the full SMB timeout, and there is no way to bound it. Office
            # PCs are full of stale mappings, so the drive is listed without
            # its size rather than freezing the window on startup.
            drives.append(DriveInfo(path=root, label="Network drive",
                                    kind=kind, total_bytes=0, free_bytes=0,
                                    is_system=False))
            continue
        try:
            usage = shutil.disk_usage(root)
            total, free = usage.total, usage.free
        except OSError:
            # Card readers with no card report a letter but cannot be queried.
            continue
        drives.append(DriveInfo(
            path=root,
            label=_windows_volume_label(root),
            kind=kind,
            total_bytes=total,
            free_bytes=free,
            is_system=(f"{letter}:" == system_root),
        ))
    return drives


def _posix_mount_points() -> list[str]:
    points = ["/"]
    for base in ("/media", "/mnt", "/run/media", "/Volumes"):
        if not os.path.isdir(base):
            continue
        try:
            for name in sorted(os.listdir(base)):
                candidate = os.path.join(base, name)
                if not os.path.isdir(candidate):
                    continue
                if os.path.ismount(candidate):
                    points.append(candidate)
                    continue
                # /run/media/<user>/<label> nests one level deeper.
                try:
                    for sub in sorted(os.listdir(candidate)):
                        nested = os.path.join(candidate, sub)
                        if os.path.ismount(nested):
                            points.append(nested)
                except OSError:
                    pass
        except OSError:
            pass
    seen: set[str] = set()
    unique = []
    for point in points:
        if point not in seen:
            seen.add(point)
            unique.append(point)
    return unique


def _list_drives_posix() -> list[DriveInfo]:
    drives = []
    for point in _posix_mount_points():
        try:
            usage = shutil.disk_usage(point)
        except OSError:
            continue
        drives.append(DriveInfo(
            path=point,
            label=os.path.basename(point.rstrip("/")) or "System",
            kind=DRIVE_FIXED if point == "/" else DRIVE_REMOVABLE,
            total_bytes=usage.total,
            free_bytes=usage.free,
            is_system=(point == "/"),
        ))
    return drives


def free_space(path: str) -> int:
    """Free bytes on the volume holding *path*, walking up to a folder that exists."""
    probe = os.path.abspath(path)
    while probe and not os.path.isdir(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    try:
        return shutil.disk_usage(probe).free
    except OSError:
        return 0


# --------------------------------------------------------------------------
# Known folders
# --------------------------------------------------------------------------

# GUIDs for SHGetKnownFolderPath. Reading these rather than joining names onto
# %USERPROFILE% is what makes redirected folders (OneDrive, roaming profiles,
# a Documents folder moved to D:) resolve correctly.
_KNOWN_FOLDER_GUIDS = {
    "Desktop":   "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "Documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "Downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "Pictures":  "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
    "Music":     "{4BD8D571-6D19-48D3-BE97-422220080E43}",
    "Videos":    "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
    "Favorites": "{1777F761-68AD-4D8A-87BD-30B759FA33DD}",
    "Contacts":  "{56784854-C6CB-462B-8169-88E350ACB882}",
}


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _known_folder(guid_str: str) -> str | None:
    guid = _GUID()
    if ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(guid_str),
                                           ctypes.byref(guid)) != 0:
        return None
    out = ctypes.c_wchar_p()
    result = ctypes.windll.shell32.SHGetKnownFolderPath(
        ctypes.byref(guid), 0, None, ctypes.byref(out))
    if result != 0:
        return None
    try:
        return out.value
    finally:
        ctypes.windll.ole32.CoTaskMemFree(out)


def user_profile_dir() -> str:
    if IS_WINDOWS:
        return os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return os.path.expanduser("~")


def personal_folders() -> dict[str, str]:
    """The user's personal folders, keyed by friendly name.

    These are what get pre-selected on launch so the common case needs no
    clicking in the tree at all.
    """
    found: dict[str, str] = {}
    if IS_WINDOWS:
        for name, guid in _KNOWN_FOLDER_GUIDS.items():
            try:
                path = _known_folder(guid)
            except Exception:
                path = None
            if not path:
                path = os.path.join(user_profile_dir(), name)
            if os.path.isdir(path):
                found[name] = path
        # Cloud-synced folders live beside the profile and hold real work.
        home = user_profile_dir()
        try:
            for entry in os.listdir(home):
                lowered = entry.lower()
                if lowered.startswith(("onedrive", "dropbox", "google drive", "box")):
                    candidate = os.path.join(home, entry)
                    if os.path.isdir(candidate):
                        found[entry] = candidate
        except OSError:
            pass
    else:
        home = user_profile_dir()
        for name in ("Desktop", "Documents", "Downloads", "Pictures",
                     "Music", "Videos"):
            path = os.path.join(home, name)
            if os.path.isdir(path):
                found[name] = path
        if not found and os.path.isdir(home):
            found["Home"] = home
    return found


def machine_description() -> dict[str, str]:
    """Identity of the machine a backup was taken from, recorded in the manifest."""
    try:
        computer = socket.gethostname()
    except OSError:
        computer = "unknown"
    try:
        user = getpass.getuser()
    except Exception:
        user = "unknown"
    return {
        "computer": computer,
        "user": user,
        "os": f"{platform.system()} {platform.release()}",
        "profile": user_profile_dir(),
    }


# --------------------------------------------------------------------------
# Archive path mapping
# --------------------------------------------------------------------------

def _looks_absolute(path: str) -> bool:
    return (path.startswith("\\\\") or path.startswith("/")
            or (len(path) > 1 and path[1] == ":"))


def archive_relpath(abs_path: str) -> str:
    """Map an absolute source path to its slot inside the backup's Data folder.

    ``C:\\Users\\Josh\\art.ai``      -> ``C/Users/Josh/art.ai``
    ``\\\\nas\\share\\art.ai``       -> ``_unc/nas/share/art.ai``
    ``/home/josh/art.ai``            -> ``_root/home/josh/art.ai``

    Forward slashes are used throughout so a backup taken on Windows can still
    be inspected (and restored from) anywhere else. The shape of the path
    decides how it is read, not the platform we happen to be running on -- so a
    Windows backup stays readable on any machine.
    """
    raw = short_path(abs_path)
    if not _looks_absolute(raw):
        raw = short_path(os.path.abspath(raw))
    if raw.startswith("\\\\"):
        return "/".join([UNC_BUCKET] + [p for p in raw.split("\\") if p])
    if len(raw) > 1 and raw[1] == ":":
        bucket = raw[0].upper()
        parts = [p for p in raw[2:].replace("/", "\\").split("\\") if p]
        return "/".join([bucket] + parts)
    parts = [p for p in raw.replace("\\", "/").split("/") if p]
    return "/".join([POSIX_BUCKET] + parts)


def restore_abspath(relpath: str, drive_map: dict[str, str] | None = None) -> str:
    """Inverse of :func:`archive_relpath`, honouring a bucket -> root remap.

    *drive_map* keys are buckets as they appear in the archive (``"C"``,
    ``"_root"``); values are the root the caller wants them restored under.
    """
    parts = [p for p in relpath.replace("\\", "/").split("/") if p]
    if not parts:
        raise ValueError("empty archive path")
    bucket, rest = parts[0], parts[1:]

    override = (drive_map or {}).get(bucket)
    if override:
        return os.path.join(override, *rest) if rest else override

    if bucket == POSIX_BUCKET:
        return "/" + "/".join(rest)
    if bucket == UNC_BUCKET:
        return "\\\\" + "\\".join(rest)
    root = f"{bucket}:\\" if IS_WINDOWS else f"/{bucket}"
    return os.path.join(root, *rest) if rest else root


def buckets_in(relpaths: Iterable[str]) -> list[str]:
    """Distinct top-level buckets present in a set of archive paths."""
    seen: list[str] = []
    for rel in relpaths:
        head = rel.replace("\\", "/").split("/", 1)[0]
        if head and head not in seen:
            seen.append(head)
    return seen


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------

def human_bytes(count: float) -> str:
    """Bytes as a short human string: 1536 -> '1.5 KB'."""
    if count is None:
        return "-"
    step = 1024.0
    value = float(count)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < step or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:,.1f} {unit}"
        value /= step
    return f"{value:,.1f} TB"


def human_count(count: int) -> str:
    return f"{count:,}"
