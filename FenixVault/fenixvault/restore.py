"""Putting a backup back.

The manifest records each file's original absolute path, so the default restore
is literally "every file goes back where it came from, folders created as
needed". Two things can make that impossible on a different PC, and both are
handled here:

* the drive letter may not exist (backup came off ``D:``, new PC has no ``D:``),
* the user profile may be named differently (``C:\\Users\\Josh`` vs ``C:\\Users\\Bob``).

Both are expressed as remaps applied to the archive-relative path, which keeps
the logic platform-neutral and testable.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from .backup import _Cancelled, _hash_and_copy, _remove_partial
from .manifest import (BackupInfo, ManifestEntry, data_dir, read_entries,
                       read_info)
from .platformutil import (IS_WINDOWS, POSIX_BUCKET, archive_relpath,
                           human_bytes, long_path, restore_abspath,
                           user_profile_dir)
from .version import BACKUP_FORMAT

CONFLICT_SKIP = "skip"
CONFLICT_OVERWRITE = "overwrite"
CONFLICT_KEEP_BOTH = "keep_both"

PHASE_READING = "reading"
PHASE_RESTORING = "restoring"
PHASE_FINISHING = "finishing"


@dataclass
class RestoreOptions:
    conflict: str = CONFLICT_SKIP
    verify: bool = True
    # archive bucket ("C", "_root") -> the root it should be written under
    drive_map: dict[str, str] = field(default_factory=dict)
    # rel-path prefix of the old user profile -> absolute path of the new one
    profile_from: str = ""
    profile_to: str = ""
    # When set, everything is written under this folder instead of the original
    # locations, preserving the tree inside it. The safe "look before you leap"
    # option.
    sandbox_root: str = ""


@dataclass
class RestorePlan:
    info: BackupInfo
    total_files: int = 0
    total_bytes: int = 0
    buckets: dict[str, tuple[int, int]] = field(default_factory=dict)
    by_extension: dict[str, tuple[int, int]] = field(default_factory=dict)
    format_too_new: bool = False

    def bucket_label(self, bucket: str) -> str:
        if bucket == POSIX_BUCKET:
            return "System root (/)"
        if bucket.startswith("_unc"):
            return "Network locations"
        return f"Drive {bucket}:"


@dataclass
class RestoreProgress:
    phase: str = PHASE_READING
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
class RestoreResult:
    files_restored: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    files_corrupt: int = 0
    bytes_restored: int = 0
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False
    duration_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.cancelled and self.files_failed == 0 and self.files_corrupt == 0

    def summary(self) -> str:
        parts = [f"{self.files_restored:,} files put back",
                 human_bytes(self.bytes_restored)]
        if self.files_skipped:
            parts.append(f"{self.files_skipped:,} already there")
        if self.files_failed:
            parts.append(f"{self.files_failed:,} failed")
        if self.files_corrupt:
            parts.append(f"{self.files_corrupt:,} failed the integrity check")
        if self.cancelled:
            parts.append("stopped early")
        return ", ".join(parts)


ProgressCallback = Callable[[RestoreProgress], None]


def read_plan(backup_dir: str) -> RestorePlan:
    """Summarise a backup without touching a single destination file."""
    info = read_info(backup_dir)
    plan = RestorePlan(info=info,
                       format_too_new=info.format > BACKUP_FORMAT)
    for entry in read_entries(backup_dir):
        plan.total_files += 1
        plan.total_bytes += entry.size
        bucket = entry.rel.split("/", 1)[0]
        count, size = plan.buckets.get(bucket, (0, 0))
        plan.buckets[bucket] = (count + 1, size + entry.size)
        ext = entry.ext or "(no extension)"
        count, size = plan.by_extension.get(ext, (0, 0))
        plan.by_extension[ext] = (count + 1, size + entry.size)
    return plan


def suggest_drive_map(plan: RestorePlan) -> dict[str, str]:
    """Sensible default targets: same letter when it exists, else leave blank.

    A blank entry means "the UI needs to ask"; nothing is ever written to a
    guessed location.
    """
    mapping: dict[str, str] = {}
    for bucket in plan.buckets:
        if bucket == POSIX_BUCKET:
            mapping[bucket] = "/" if not IS_WINDOWS else ""
            continue
        if bucket.startswith("_unc"):
            mapping[bucket] = ""
            continue
        root = f"{bucket}:\\" if IS_WINDOWS else f"/{bucket}"
        mapping[bucket] = root if os.path.isdir(root) else ""
    return mapping


def suggest_profile_remap(info: BackupInfo) -> tuple[str, str]:
    """(old rel prefix, new absolute profile) when the user folder has changed."""
    if not info.source_profile:
        return "", ""
    current = user_profile_dir()
    if os.path.normcase(os.path.abspath(current)) == \
            os.path.normcase(os.path.abspath(info.source_profile)):
        return "", ""
    return archive_relpath(info.source_profile), current


def target_path(entry: ManifestEntry, options: RestoreOptions) -> str:
    """Where *entry* should be written, after every remap is applied."""
    rel = entry.rel.replace("\\", "/")

    if options.sandbox_root:
        return os.path.join(options.sandbox_root, *rel.split("/"))

    if options.profile_from and options.profile_to:
        prefix = options.profile_from.replace("\\", "/").rstrip("/")
        lowered_rel = rel.lower() if IS_WINDOWS else rel
        lowered_prefix = prefix.lower() if IS_WINDOWS else prefix
        if lowered_rel == lowered_prefix:
            return options.profile_to
        if lowered_rel.startswith(lowered_prefix + "/"):
            tail = rel[len(prefix) + 1:]
            return os.path.join(options.profile_to, *tail.split("/"))

    return restore_abspath(rel, options.drive_map)


def _unique_name(path: str) -> str:
    """``logo.ai`` -> ``logo (restored).ai``, then ``(restored 2)`` and so on."""
    stem, ext = os.path.splitext(path)
    candidate = f"{stem} (restored){ext}"
    counter = 2
    while os.path.exists(long_path(candidate)):
        candidate = f"{stem} (restored {counter}){ext}"
        counter += 1
    return candidate


def run_restore(backup_dir: str,
                options: RestoreOptions | None = None,
                progress: ProgressCallback | None = None,
                cancel: threading.Event | None = None,
                plan: RestorePlan | None = None,
                progress_interval: float = 0.2) -> RestoreResult:
    """Write every file in the manifest back to its home."""
    options = options or RestoreOptions()
    started = time.monotonic()
    result = RestoreResult()
    plan = plan or read_plan(backup_dir)

    if plan.format_too_new:
        result.errors.append(
            "This backup was made by a newer version of the program. "
            "Update Fenix Vault and try again.")
        result.files_failed = 1
        return result

    root_data = data_dir(backup_dir)
    state = RestoreProgress(phase=PHASE_RESTORING,
                            files_total=plan.total_files,
                            bytes_total=plan.total_bytes,
                            message="Putting your files back...")
    last_ping = [0.0]

    def ping(force: bool = False) -> None:
        if progress is None:
            return
        now = time.monotonic()
        if force or now - last_ping[0] >= progress_interval:
            last_ping[0] = now
            progress(RestoreProgress(state.phase, state.files_done,
                                     state.files_total, state.bytes_done,
                                     state.bytes_total, state.current_file,
                                     state.message))

    def fail(message: str) -> None:
        result.files_failed += 1
        if len(result.errors) < 2000:
            result.errors.append(message)

    ping(force=True)
    made_dirs: set[str] = set()

    for entry in read_entries(backup_dir):
        if cancel is not None and cancel.is_set():
            result.cancelled = True
            break

        source = os.path.join(root_data, *entry.rel.split("/"))
        state.current_file = entry.src

        try:
            destination = target_path(entry, options)
        except ValueError as exc:
            fail(f"Bad manifest entry for {entry.src}: {exc}")
            state.files_done += 1
            continue

        bucket = entry.rel.split("/", 1)[0]
        if not options.sandbox_root and not _bucket_resolved(bucket, options):
            fail(f"No destination chosen for drive {bucket}: - skipped {entry.src}")
            state.files_done += 1
            state.bytes_done += entry.size
            continue

        if not os.path.isfile(long_path(source)):
            fail(f"Missing from the backup: {entry.rel}")
            state.files_done += 1
            state.bytes_done += entry.size
            continue

        if os.path.exists(long_path(destination)):
            if options.conflict == CONFLICT_SKIP:
                result.files_skipped += 1
                state.files_done += 1
                state.bytes_done += entry.size
                ping()
                continue
            if options.conflict == CONFLICT_KEEP_BOTH:
                destination = _unique_name(destination)

        parent = os.path.dirname(destination)
        if parent and parent not in made_dirs:
            try:
                os.makedirs(long_path(parent), exist_ok=True)
                made_dirs.add(parent)
            except OSError as exc:
                fail(f"Could not create folder {parent}: {exc}")
                state.files_done += 1
                state.bytes_done += entry.size
                continue

        try:
            digest = _hash_and_copy(source, destination, options.verify, cancel,
                                    lambda count: (_bump(state, count), ping()))
            os.utime(long_path(destination), (entry.mtime, entry.mtime))
        except _Cancelled:
            result.cancelled = True
            _remove_partial(destination)
            break
        except PermissionError:
            _remove_partial(destination)
            fail(f"Permission denied writing {destination} - "
                 f"try running as administrator.")
            state.files_done += 1
            continue
        except OSError as exc:
            _remove_partial(destination)
            fail(f"Could not write {destination}: {exc}")
            state.files_done += 1
            continue

        if options.verify and entry.sha256 and digest and digest != entry.sha256:
            result.files_corrupt += 1
            result.errors.append(
                f"Integrity check failed for {entry.src} - the copy in the "
                f"backup does not match what was recorded.")

        result.files_restored += 1
        result.bytes_restored += entry.size
        state.files_done += 1
        ping()

    state.phase = PHASE_FINISHING
    state.message = "Done."
    result.duration_seconds = time.monotonic() - started
    ping(force=True)
    return result


def _bucket_resolved(bucket: str, options: RestoreOptions) -> bool:
    """True when we know where this bucket's files should land."""
    if options.profile_from and options.profile_to:
        # The profile remap supplies its own absolute destination.
        if options.profile_from.split("/", 1)[0] == bucket:
            return True
    mapped = options.drive_map.get(bucket)
    if mapped:
        return True
    if bucket == POSIX_BUCKET:
        return not IS_WINDOWS
    if bucket.startswith("_unc"):
        return False
    root = f"{bucket}:\\" if IS_WINDOWS else f"/{bucket}"
    return os.path.isdir(root)


def _bump(state: RestoreProgress, count: int) -> None:
    state.bytes_done += count
