"""The record of what a backup contains.

Layout of a finished backup folder::

    FenixVault-Backup-2026-08-12_1432\\
        HOW-TO-RESTORE.txt      plain-English instructions
        RESTORE.exe             the program itself, ready to put it all back
        backup-info.json        header: where it came from, totals, settings
        manifest.jsonl          one line per file
        backup-report.txt       anything that could not be copied
        Data\\
            C\\Users\\Josh\\Documents\\Logos\\logo.ai      <- the mirrored tree

The manifest is JSON Lines rather than one big JSON document so it can be
appended as the copy runs. A backup interrupted by a power cut still leaves a
readable manifest describing every file that made it, and the restore side can
stream it without loading the whole thing into memory.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Iterator

from .platformutil import DATA_DIR_NAME
from .version import APP_NAME, BACKUP_FORMAT, VERSION

INFO_FILENAME = "backup-info.json"
MANIFEST_FILENAME = "manifest.jsonl"
REPORT_FILENAME = "backup-report.txt"
README_FILENAME = "HOW-TO-RESTORE.txt"


@dataclass
class ManifestEntry:
    src: str        # original absolute path on the source PC
    rel: str        # path inside the backup's Data folder, forward slashes
    size: int
    mtime: float
    sha256: str = ""
    ext: str = ""

    @classmethod
    def from_json(cls, raw: dict) -> "ManifestEntry":
        return cls(
            src=raw.get("src", ""),
            rel=raw.get("rel", ""),
            size=int(raw.get("size", 0)),
            mtime=float(raw.get("mtime", 0.0)),
            sha256=raw.get("sha256", ""),
            ext=raw.get("ext", ""),
        )


@dataclass
class BackupInfo:
    tool: str = APP_NAME
    tool_version: str = VERSION
    format: int = BACKUP_FORMAT
    created_utc: str = ""
    source_computer: str = ""
    source_user: str = ""
    source_os: str = ""
    source_profile: str = ""
    total_files: int = 0
    total_bytes: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    verified: bool = False
    selected_extensions: list[str] = field(default_factory=list)
    selected_roots: list[str] = field(default_factory=list)
    complete: bool = False
    has_snapshot: bool = False
    snapshot_has_secrets: bool = False

    @classmethod
    def from_json(cls, raw: dict) -> "BackupInfo":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in raw.items() if k in known})


def data_dir(backup_dir: str) -> str:
    return os.path.join(backup_dir, DATA_DIR_NAME)


def is_backup_folder(path: str) -> bool:
    """True when *path* looks like a Fenix Vault backup."""
    return os.path.isfile(os.path.join(path, INFO_FILENAME))


def find_backup_root(start: str | None = None, max_up: int = 3) -> str | None:
    """Locate a backup folder at or above *start*.

    This is what lets RESTORE.exe, sitting inside the backup on a USB drive,
    open straight into restore mode when it is double-clicked.
    """
    current = os.path.abspath(start or os.getcwd())
    for _ in range(max_up + 1):
        if is_backup_folder(current):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


def default_backup_name(now: datetime | None = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H%M")
    return f"FenixVault-Backup-{stamp}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ManifestWriter:
    """Appends manifest lines as files are copied, then seals the header."""

    def __init__(self, backup_dir: str, info: BackupInfo) -> None:
        self.backup_dir = backup_dir
        self.info = info
        self._path = os.path.join(backup_dir, MANIFEST_FILENAME)
        self._handle = None

    def __enter__(self) -> "ManifestWriter":
        os.makedirs(self.backup_dir, exist_ok=True)
        self._handle = open(self._path, "w", encoding="utf-8", newline="\n")
        self.info.created_utc = self.info.created_utc or utc_now_iso()
        self.write_info()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def add(self, entry: ManifestEntry) -> None:
        assert self._handle is not None, "ManifestWriter used outside its context"
        self._handle.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

    def flush(self) -> None:
        if self._handle is not None:
            self._handle.flush()

    def write_info(self) -> None:
        """(Re)write the header file. Called at start and again at the end."""
        path = os.path.join(self.backup_dir, INFO_FILENAME)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(asdict(self.info), handle, indent=2, ensure_ascii=False)

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None


def read_info(backup_dir: str) -> BackupInfo:
    with open(os.path.join(backup_dir, INFO_FILENAME), encoding="utf-8") as handle:
        return BackupInfo.from_json(json.load(handle))


def read_entries(backup_dir: str) -> Iterator[ManifestEntry]:
    """Stream the manifest, tolerating a truncated final line."""
    path = os.path.join(backup_dir, MANIFEST_FILENAME)
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield ManifestEntry.from_json(json.loads(line))
            except (ValueError, TypeError):
                # An interrupted backup can leave a half-written last line.
                continue


def count_entries(backup_dir: str) -> tuple[int, int]:
    """(files, bytes) recorded in the manifest."""
    files = 0
    total = 0
    for entry in read_entries(backup_dir):
        files += 1
        total += entry.size
    return files, total


def write_report(backup_dir: str, lines: list[str]) -> str | None:
    """Write the list of problems, if there were any. Returns the path."""
    if not lines:
        return None
    path = os.path.join(backup_dir, REPORT_FILENAME)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{APP_NAME} {VERSION} - items that could not be copied\n")
        handle.write(f"Written {utc_now_iso()}\n")
        handle.write("=" * 70 + "\n\n")
        handle.write("Files listed here were skipped. The rest of the backup is\n"
                     "complete and safe to use.\n\n")
        for line in lines:
            handle.write(line + "\n")
    return path
