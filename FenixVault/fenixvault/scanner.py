"""Walking the tree: counting what is there, and listing folders for the UI.

The scan deliberately aggregates rather than accumulating a list of every file.
A busy shop PC can hold a million files; one small object each would cost
hundreds of megabytes for no benefit, because the backup re-walks the tree
anyway (which is also what keeps the copy honest -- it copies what is on disk
at copy time, not what was there when you started clicking).
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterator

from .platformutil import (file_attributes, is_cloud_placeholder,
                           long_path, norm)
from .selection import ExcludeRules, FolderSelection


@dataclass
class SubFolder:
    name: str
    path: str
    has_children: bool
    accessible: bool = True


@dataclass
class ScanProgress:
    dirs_scanned: int = 0
    files_seen: int = 0
    bytes_seen: int = 0
    current_dir: str = ""


@dataclass
class ScanResult:
    ext_counts: dict[str, int] = field(default_factory=dict)
    ext_bytes: dict[str, int] = field(default_factory=dict)
    total_files: int = 0
    total_bytes: int = 0
    dirs_scanned: int = 0
    placeholders_skipped: int = 0
    placeholder_bytes: int = 0
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False
    duration_seconds: float = 0.0

    def extensions(self) -> list[str]:
        return sorted(self.ext_counts)

    def files_for(self, extensions: set[str]) -> tuple[int, int]:
        """(count, bytes) for the subset of extensions given."""
        count = sum(self.ext_counts.get(ext, 0) for ext in extensions)
        size = sum(self.ext_bytes.get(ext, 0) for ext in extensions)
        return count, size

    def top_extensions(self, extensions: set[str], limit: int = 8
                       ) -> list[tuple[str, int, int]]:
        """Largest selected extensions by size: (ext, count, bytes)."""
        rows = [(ext, self.ext_counts.get(ext, 0), self.ext_bytes.get(ext, 0))
                for ext in extensions if self.ext_counts.get(ext)]
        rows.sort(key=lambda row: row[2], reverse=True)
        return rows[:limit]


ProgressCallback = Callable[[ScanProgress], None]


def split_ext(filename: str) -> str:
    """Lowercase extension including the dot, or '' when there is none.

    Dotfiles such as ``.gitignore`` are treated as having no extension, which
    keeps them out of the type picker where they would only be noise.
    """
    base = os.path.basename(filename)
    dot = base.rfind(".")
    if dot <= 0 or dot == len(base) - 1:
        return ""
    return base[dot:].lower()


def list_subfolders(path: str, excludes: ExcludeRules | None = None,
                    include_skipped: bool = False) -> list[SubFolder]:
    """Immediate subfolders of *path*, for lazily filling the tree.

    Folders the exclude policy would skip are omitted unless *include_skipped*,
    so the tree shows the user what will genuinely be considered.
    """
    excludes = excludes or ExcludeRules()
    out: list[SubFolder] = []
    try:
        with os.scandir(long_path(path)) as entries:
            for entry in entries:
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                if not include_skipped and excludes.should_skip_dir(path, entry.name):
                    continue
                child_path = os.path.join(path, entry.name)
                out.append(SubFolder(
                    name=entry.name,
                    path=child_path,
                    has_children=_has_subfolder(child_path),
                ))
    except PermissionError:
        return []
    except OSError:
        return []
    out.sort(key=lambda folder: folder.name.lower())
    return out


def _has_subfolder(path: str) -> bool:
    """Cheap probe so the tree only draws an expand arrow when there is one."""
    try:
        with os.scandir(long_path(path)) as entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        return True
                except OSError:
                    continue
    except OSError:
        return False
    return False


def iter_files(selection: FolderSelection, excludes: ExcludeRules,
               cancel: threading.Event | None = None,
               on_dir: Callable[[str], None] | None = None,
               on_error: Callable[[str], None] | None = None,
               on_placeholder: Callable[[str, int], None] | None = None
               ) -> Iterator[tuple[str, int, float, str]]:
    """Yield ``(path, size, mtime, ext)`` for every file inside the selection.

    Shared by the scan and the copy so the two can never disagree about which
    files are in scope -- including the cloud-placeholder policy, which is
    applied here rather than in each caller so a scan can never promise files
    the copy will then skip.

    *on_placeholder* is told about each online-only file left behind, so the
    caller can report what was not taken instead of quietly omitting it.
    """
    visited: set[str] = set()
    for root in selection.roots():
        if cancel is not None and cancel.is_set():
            return
        stack = [root]
        while stack:
            if cancel is not None and cancel.is_set():
                return
            current = stack.pop()
            key = norm(current)
            if key in visited:
                continue
            visited.add(key)
            if on_dir is not None:
                on_dir(current)
            try:
                with os.scandir(long_path(current)) as entries:
                    for entry in entries:
                        try:
                            is_dir = entry.is_dir(follow_symlinks=False)
                        except OSError:
                            continue
                        if is_dir:
                            child = os.path.join(current, entry.name)
                            # An explicit untick in the tree always wins over
                            # the folder being inside a ticked parent.
                            if not selection.effective(child):
                                continue
                            if excludes.should_skip_dir(current, entry.name, root):
                                continue
                            stack.append(child)
                            continue
                        if excludes.should_skip_file(entry.name):
                            continue
                        try:
                            if entry.is_symlink():
                                continue
                            stat = entry.stat(follow_symlinks=False)
                        except OSError:
                            continue
                        full = os.path.join(current, entry.name)
                        # The attribute bits come free with the stat we already
                        # did, so noticing a placeholder costs nothing.
                        if excludes.skip_cloud_placeholders and is_cloud_placeholder(
                                file_attributes(stat)):
                            if on_placeholder is not None:
                                on_placeholder(full, stat.st_size)
                            continue
                        yield (full, stat.st_size, stat.st_mtime,
                               split_ext(entry.name))
            except PermissionError:
                if on_error is not None:
                    on_error(f"No permission to read: {current}")
            except OSError as exc:
                if on_error is not None:
                    on_error(f"Could not read {current}: {exc}")


def scan(selection: FolderSelection, excludes: ExcludeRules,
         progress: ProgressCallback | None = None,
         cancel: threading.Event | None = None,
         progress_interval: float = 0.15) -> ScanResult:
    """Count every file under the selection, grouped by extension."""
    result = ScanResult()
    state = ScanProgress()
    started = time.monotonic()
    last_ping = 0.0

    def ping(force: bool = False) -> None:
        nonlocal last_ping
        if progress is None:
            return
        now = time.monotonic()
        if force or now - last_ping >= progress_interval:
            last_ping = now
            progress(ScanProgress(state.dirs_scanned, state.files_seen,
                                  state.bytes_seen, state.current_dir))

    def note_dir(path: str) -> None:
        state.dirs_scanned += 1
        state.current_dir = path
        ping()

    def note_error(message: str) -> None:
        if len(result.errors) < 500:
            result.errors.append(message)

    def note_placeholder(_path: str, size: int) -> None:
        result.placeholders_skipped += 1
        result.placeholder_bytes += size

    for _path, size, _mtime, ext in iter_files(selection, excludes, cancel,
                                               on_dir=note_dir,
                                               on_error=note_error,
                                               on_placeholder=note_placeholder):
        state.files_seen += 1
        state.bytes_seen += size
        if ext:
            result.ext_counts[ext] = result.ext_counts.get(ext, 0) + 1
            result.ext_bytes[ext] = result.ext_bytes.get(ext, 0) + size
        if state.files_seen % 256 == 0:
            ping()

    result.total_files = state.files_seen
    result.total_bytes = state.bytes_seen
    result.dirs_scanned = state.dirs_scanned
    result.cancelled = bool(cancel is not None and cancel.is_set())
    result.duration_seconds = time.monotonic() - started
    ping(force=True)
    return result
