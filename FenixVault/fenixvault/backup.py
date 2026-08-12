"""The copy engine.

Rules it follows, in order of importance:

1. Never lose the shape of the tree. Every file lands at
   ``Data/<drive>/<exactly its original path>``.
2. Never abort the whole job for one bad file. A locked Outlook mailbox or a
   permission-denied folder is recorded and the run carries on.
3. Never silently corrupt. Each file is hashed as it is copied, so the restore
   side can prove the bytes survived the trip.
4. Never copy the backup into itself.
"""

from __future__ import annotations

import errno
import hashlib
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from . import payload
from .manifest import (BackupInfo, ManifestEntry, ManifestWriter, data_dir,
                       read_entries, read_info, write_report)
from .platformutil import (archive_relpath, free_space, human_bytes,
                           is_ancestor, long_path, machine_description, norm)
from .scanner import iter_files
from .selection import ExcludeRules, FolderSelection

COPY_CHUNK = 1024 * 1024

# Above this many previously-recorded files we stop trying to reuse old hashes,
# to keep the lookup table off the wrong side of a few hundred megabytes.
REUSE_LIMIT = 2_000_000

PHASE_PREPARING = "preparing"
PHASE_COPYING = "copying"
PHASE_FINISHING = "finishing"


@dataclass
class BackupOptions:
    verify: bool = True             # hash every file as it is copied
    incremental: bool = True        # leave already-copied files alone
    include_restore_tool: bool = True
    expected_files: int = 0         # from the scan, for the progress bar
    expected_bytes: int = 0


@dataclass
class BackupProgress:
    phase: str = PHASE_PREPARING
    files_done: int = 0
    files_total: int = 0
    bytes_done: int = 0
    bytes_total: int = 0
    current_file: str = ""
    message: str = ""

    @property
    def fraction(self) -> float:
        if self.bytes_total > 0:
            return min(1.0, self.bytes_done / self.bytes_total)
        if self.files_total > 0:
            return min(1.0, self.files_done / self.files_total)
        return 0.0


@dataclass
class BackupResult:
    backup_dir: str = ""
    files_copied: int = 0
    files_reused: int = 0
    files_failed: int = 0
    bytes_copied: int = 0
    bytes_total: int = 0
    errors: list[str] = field(default_factory=list)
    report_path: str | None = None
    cancelled: bool = False
    duration_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.cancelled and self.files_failed == 0

    def summary(self) -> str:
        parts = [f"{self.files_copied + self.files_reused:,} files",
                 human_bytes(self.bytes_total)]
        if self.files_reused:
            parts.append(f"{self.files_reused:,} already up to date")
        if self.files_failed:
            parts.append(f"{self.files_failed:,} could not be copied")
        if self.cancelled:
            parts.append("stopped early")
        return ", ".join(parts)


ProgressCallback = Callable[[BackupProgress], None]


def _hash_and_copy(src: str, dst: str, want_hash: bool,
                   cancel: threading.Event | None,
                   on_bytes: Callable[[int], None]) -> str:
    """Stream *src* to *dst*, hashing on the way through. Returns hex or ''."""
    digest = hashlib.sha256() if want_hash else None
    with open(long_path(src), "rb") as reader, \
            open(long_path(dst), "wb") as writer:
        while True:
            if cancel is not None and cancel.is_set():
                raise _Cancelled()
            chunk = reader.read(COPY_CHUNK)
            if not chunk:
                break
            writer.write(chunk)
            if digest is not None:
                digest.update(chunk)
            on_bytes(len(chunk))
    return digest.hexdigest() if digest is not None else ""


def hash_file(path: str, cancel: threading.Event | None = None) -> str:
    digest = hashlib.sha256()
    with open(long_path(path), "rb") as handle:
        while True:
            if cancel is not None and cancel.is_set():
                raise _Cancelled()
            chunk = handle.read(COPY_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


class _Cancelled(Exception):
    """Raised internally when the user presses Stop mid-file."""


def _same_file(dst: str, size: int, mtime: float) -> bool:
    """Treat a destination as already-current when size and mtime line up.

    Two seconds of slack covers filesystems that store mtime at coarser
    resolution than the source (FAT32 on a USB stick rounds to 2 seconds).
    """
    try:
        stat = os.stat(long_path(dst))
    except OSError:
        return False
    return stat.st_size == size and abs(stat.st_mtime - mtime) <= 2.0


def _load_previous(backup_dir: str) -> dict[str, tuple[int, float, str]]:
    """Previous manifest as ``rel -> (size, mtime, sha256)`` for reuse."""
    table: dict[str, tuple[int, float, str]] = {}
    try:
        read_info(backup_dir)
    except (OSError, ValueError):
        return table
    for entry in read_entries(backup_dir):
        table[entry.rel] = (entry.size, entry.mtime, entry.sha256)
        if len(table) > REUSE_LIMIT:
            return {}
    return table


def estimate(result_files: int, result_bytes: int, dest_dir: str) -> tuple[bool, str]:
    """Pre-flight space check. Returns (fits, human-readable explanation)."""
    available = free_space(dest_dir)
    if result_bytes <= 0:
        return True, "Nothing selected yet."
    if result_bytes < available:
        return True, (f"{result_files:,} files, {human_bytes(result_bytes)} - "
                      f"{human_bytes(available)} free on the destination.")
    return False, (f"Not enough room: this needs {human_bytes(result_bytes)} but "
                   f"only {human_bytes(available)} is free on the destination.")


def run_backup(selection: FolderSelection,
               excludes: ExcludeRules,
               extensions: set[str],
               backup_dir: str,
               options: BackupOptions | None = None,
               progress: ProgressCallback | None = None,
               cancel: threading.Event | None = None,
               progress_interval: float = 0.2) -> BackupResult:
    """Copy every selected file into *backup_dir*, mirroring the source tree."""
    options = options or BackupOptions()
    started = time.monotonic()
    result = BackupResult(backup_dir=backup_dir)
    wanted = {ext.lower() for ext in extensions}

    state = BackupProgress(phase=PHASE_PREPARING,
                           files_total=options.expected_files,
                           bytes_total=options.expected_bytes,
                           message="Getting ready...")
    last_ping = [0.0]

    def ping(force: bool = False) -> None:
        if progress is None:
            return
        now = time.monotonic()
        if force or now - last_ping[0] >= progress_interval:
            last_ping[0] = now
            progress(BackupProgress(state.phase, state.files_done,
                                    state.files_total, state.bytes_done,
                                    state.bytes_total, state.current_file,
                                    state.message))

    def fail(message: str) -> None:
        result.files_failed += 1
        if len(result.errors) < 2000:
            result.errors.append(message)

    ping(force=True)

    os.makedirs(long_path(backup_dir), exist_ok=True)
    root_data = data_dir(backup_dir)
    os.makedirs(long_path(root_data), exist_ok=True)

    previous = _load_previous(backup_dir) if options.incremental else {}

    machine = machine_description()
    info = BackupInfo(
        source_computer=machine["computer"],
        source_user=machine["user"],
        source_os=machine["os"],
        source_profile=machine["profile"],
        verified=options.verify,
        selected_extensions=sorted(wanted),
        selected_roots=selection.roots(),
    )

    backup_key = norm(backup_dir)
    made_dirs: set[str] = set()

    state.phase = PHASE_COPYING
    state.message = "Copying files..."

    try:
        with ManifestWriter(backup_dir, info) as manifest:
            for src, size, mtime, ext in iter_files(
                    selection, excludes, cancel,
                    on_error=lambda message: result.errors.append(message)):
                if cancel is not None and cancel.is_set():
                    result.cancelled = True
                    break
                if ext not in wanted:
                    continue
                # Backing up a drive to a folder on that same drive would
                # otherwise feed the backup its own output forever.
                src_key = norm(src)
                if src_key == backup_key or is_ancestor(backup_key, src_key):
                    continue

                rel = archive_relpath(src)
                dst = os.path.join(root_data, rel.replace("/", os.sep))
                state.current_file = src

                parent = os.path.dirname(dst)
                if parent not in made_dirs:
                    try:
                        os.makedirs(long_path(parent), exist_ok=True)
                        made_dirs.add(parent)
                    except OSError as exc:
                        fail(f"Could not create folder for {src}: {exc}")
                        continue

                reused = previous.get(rel)
                if (options.incremental and reused
                        and reused[0] == size and abs(reused[1] - mtime) <= 2.0
                        and _same_file(dst, size, mtime)):
                    manifest.add(ManifestEntry(src=src, rel=rel, size=size,
                                               mtime=mtime, sha256=reused[2],
                                               ext=ext))
                    result.files_reused += 1
                    result.bytes_total += size
                    state.files_done += 1
                    state.bytes_done += size
                    ping()
                    continue

                if options.incremental and not reused and _same_file(dst, size, mtime):
                    # Destination matches but we have no recorded hash for it.
                    try:
                        digest = hash_file(dst, cancel) if options.verify else ""
                    except _Cancelled:
                        result.cancelled = True
                        break
                    except OSError:
                        digest = ""
                    else:
                        manifest.add(ManifestEntry(src=src, rel=rel, size=size,
                                                   mtime=mtime, sha256=digest,
                                                   ext=ext))
                        result.files_reused += 1
                        result.bytes_total += size
                        state.files_done += 1
                        state.bytes_done += size
                        ping()
                        continue

                try:
                    digest = _hash_and_copy(
                        src, dst, options.verify, cancel,
                        lambda count: (_bump(state, count), ping()))
                    os.utime(long_path(dst), (mtime, mtime))
                except _Cancelled:
                    result.cancelled = True
                    _remove_partial(dst)
                    break
                except PermissionError:
                    _remove_partial(dst)
                    fail(f"Permission denied: {src}")
                    state.files_done += 1
                    continue
                except OSError as exc:
                    _remove_partial(dst)
                    if exc.errno == errno.ENOSPC:
                        result.errors.append(
                            "The destination drive ran out of space. "
                            "Everything copied so far is intact.")
                        result.cancelled = True
                        break
                    fail(f"Could not copy {src}: {exc}")
                    state.files_done += 1
                    continue

                manifest.add(ManifestEntry(src=src, rel=rel, size=size,
                                           mtime=mtime, sha256=digest, ext=ext))
                result.files_copied += 1
                result.bytes_total += size
                state.files_done += 1
                ping()

            # Cancelling before the first file means the loop body never ran,
            # so check the flag once more rather than sealing the header as
            # complete on a run that never really started.
            if cancel is not None and cancel.is_set():
                result.cancelled = True

            state.phase = PHASE_FINISHING
            state.message = "Writing the file list..."
            ping(force=True)

            info.total_files = result.files_copied + result.files_reused
            info.total_bytes = result.bytes_total
            info.failed_files = result.files_failed
            info.complete = not result.cancelled
            manifest.info = info
            manifest.flush()
            manifest.write_info()
    except OSError as exc:
        result.errors.append(f"Could not write to {backup_dir}: {exc}")
        result.files_failed += 1

    if options.include_restore_tool:
        state.message = "Adding the restore program..."
        ping(force=True)
        try:
            payload.install_restore_tool(backup_dir, info)
        except OSError as exc:
            result.errors.append(f"Could not add the restore program: {exc}")

    result.report_path = write_report(backup_dir, result.errors)
    result.duration_seconds = time.monotonic() - started
    state.phase = PHASE_FINISHING
    state.message = "Done."
    ping(force=True)
    return result


def _bump(state: BackupProgress, count: int) -> None:
    state.bytes_done += count


def _remove_partial(path: str) -> None:
    try:
        os.remove(long_path(path))
    except OSError:
        pass
