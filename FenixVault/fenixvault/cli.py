"""Command line entry point.

The GUI is the product; this exists so backups can be scripted or scheduled,
and so the engine can be exercised end to end without a display.
"""

from __future__ import annotations

import argparse
import os
import sys

from . import catalog
from .backup import BackupOptions, run_backup
from .manifest import default_backup_name, find_backup_root
from .platformutil import human_bytes, list_drives, personal_folders
from .restore import (CONFLICT_KEEP_BOTH, CONFLICT_OVERWRITE, CONFLICT_SKIP,
                      RestoreOptions, read_plan, run_restore,
                      suggest_drive_map, suggest_profile_remap)
from .scanner import scan
from .selection import ExcludeRules, FolderSelection
from .version import APP_NAME, VERSION


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="FenixVault",
        description=f"{APP_NAME} {VERSION} - back up personal and business files.")
    parser.add_argument("--version", action="version",
                        version=f"{APP_NAME} {VERSION}")
    parser.add_argument("--no-gui", action="store_true",
                        help="run on the command line instead of opening the window")

    parser.add_argument("--restore", metavar="BACKUP_FOLDER", nargs="?", const="",
                        help="open a backup folder to put files back")
    parser.add_argument("--backup", action="store_true",
                        help="run a backup without opening the window")

    parser.add_argument("--from", dest="sources", metavar="FOLDER", nargs="*",
                        help="folders to back up (default: your personal folders)")
    parser.add_argument("--to", dest="destination", metavar="FOLDER",
                        help="where the backup folder is created")
    parser.add_argument("--categories", metavar="KEY", nargs="*",
                        help="file-type categories to include "
                             "(default: the recommended set)")
    parser.add_argument("--all-types", action="store_true",
                        help="include every file type the catalog knows")
    parser.add_argument("--no-verify", action="store_true",
                        help="skip the integrity fingerprints (faster)")
    parser.add_argument("--include-system", action="store_true",
                        help="do not skip Windows and program folders")
    parser.add_argument("--no-snapshot", action="store_true",
                        help="do not record how this PC is set up")
    parser.add_argument("--no-screenshots", action="store_true",
                        help="record the settings but take no screenshots")

    parser.add_argument("--conflict", choices=[CONFLICT_SKIP, CONFLICT_OVERWRITE,
                                               CONFLICT_KEEP_BOTH],
                        default=CONFLICT_SKIP,
                        help="what to do when a file already exists (restore)")
    parser.add_argument("--into", metavar="FOLDER",
                        help="restore everything under one folder instead of "
                             "the original locations")

    parser.add_argument("--list-drives", action="store_true",
                        help="show the drives attached to this computer")
    parser.add_argument("--list-categories", action="store_true",
                        help="show the file-type categories and exit")
    return parser


def _print_drives() -> int:
    for drive in list_drives():
        print(f"{drive.path:<12} {drive.label or '(no label)':<20} "
              f"{drive.kind:<10} {human_bytes(drive.free_bytes)} free of "
              f"{human_bytes(drive.total_bytes)}"
              f"{'   [system]' if drive.is_system else ''}")
    return 0


def _print_categories() -> int:
    for cat in catalog.CATEGORIES:
        mark = "on " if cat.default_on else "off"
        print(f"[{mark}] {cat.key:<14} {cat.name}")
        print(f"       {', '.join(cat.extensions)}")
    return 0


def _resolve_extensions(args) -> set[str]:
    if args.all_types:
        return catalog.known_extensions()
    if args.categories:
        picked: set[str] = set()
        for key in args.categories:
            found = catalog.category_by_key(key)
            if found is None:
                raise SystemExit(f"Unknown category: {key} "
                                 f"(try --list-categories)")
            picked.update(found.extensions)
        return picked
    return catalog.default_extensions()


class _NullStream:
    """Swallows output when there is genuinely nowhere to write it."""

    def write(self, _text: str) -> int:
        return 0

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


def _stream_works(stream) -> bool:
    if stream is None:
        return False
    try:
        stream.write("")
        stream.flush()
    except Exception:
        return False
    return True


def ensure_output() -> None:
    """Make printing work whatever we were launched from.

    The packaged build is a GUI-subsystem exe so that double-clicking it does
    not flash a black console window. The cost is that it starts with no
    console at all, and ``sys.stdout`` can be missing -- which would turn the
    first ``print`` of a scheduled backup into a crash.

    Run from a terminal we attach to that terminal. Run with pipes (a task
    scheduler, CI) the inherited pipes already work and are left alone, because
    stealing them would send the output somewhere nobody is reading.
    """
    if _stream_works(getattr(sys, "stdout", None)):
        return
    if os.name == "nt":
        try:
            import ctypes
            ATTACH_PARENT_PROCESS = -1
            if ctypes.windll.kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
                sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
                sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
                return
        except Exception:
            pass
    sys.stdout = _NullStream()          # type: ignore[assignment]
    if not _stream_works(getattr(sys, "stderr", None)):
        sys.stderr = _NullStream()      # type: ignore[assignment]


def _progress_line(text: str) -> None:
    sys.stdout.write("\r" + text.ljust(78)[:78])
    sys.stdout.flush()


def run_cli_backup(args) -> int:
    sources = args.sources or list(personal_folders().values())
    if not sources:
        print("Nothing to back up: no folders given and no personal folders found.")
        return 2
    if not args.destination:
        print("Missing --to: say where the backup should be written.")
        return 2

    selection = FolderSelection()
    for source in sources:
        if not os.path.isdir(source):
            print(f"Skipping (not a folder): {source}")
            continue
        selection.set(source, True)
    if selection.is_empty():
        print("None of the folders given exist.")
        return 2

    excludes = ExcludeRules(skip_system=not args.include_system)
    extensions = _resolve_extensions(args)

    print(f"{APP_NAME} {VERSION}")
    print(f"Looking through {len(selection.roots())} folder(s)...")
    result = scan(selection, excludes,
                  progress=lambda p: _progress_line(
                      f"  {p.files_seen:,} files seen  ({human_bytes(p.bytes_seen)})"))
    print()
    count, size = result.files_for(extensions)
    print(f"Found {count:,} matching files ({human_bytes(size)}).")
    if count == 0:
        print("Nothing matched the chosen file types.")
        return 1

    backup_dir = os.path.join(args.destination, default_backup_name())
    print(f"Copying to {backup_dir}")
    options = BackupOptions(verify=not args.no_verify,
                            capture_snapshot=not args.no_snapshot,
                            snapshot_screenshots=not args.no_screenshots,
                            expected_files=count, expected_bytes=size)
    outcome = run_backup(selection, excludes, extensions, backup_dir, options,
                         progress=lambda p: _progress_line(
                             f"  {int(p.fraction * 100):3d}%  "
                             f"{p.files_done:,}/{p.files_total:,}  "
                             f"{os.path.basename(p.current_file)[:40]}"))
    print()
    print(outcome.summary())
    if outcome.snapshot_report:
        print(f"This PC's setup recorded in {outcome.snapshot_report}")
    if outcome.report_path:
        print(f"Some items were skipped - see {outcome.report_path}")
    return 0 if outcome.ok else 1


def run_cli_restore(args, backup_dir: str) -> int:
    plan = read_plan(backup_dir)
    print(f"{APP_NAME} {VERSION}")
    print(f"Backup from {plan.info.source_computer or 'unknown PC'} "
          f"({plan.info.created_utc or 'unknown date'})")
    print(f"{plan.total_files:,} files, {human_bytes(plan.total_bytes)}")

    options = RestoreOptions(conflict=args.conflict,
                             drive_map=suggest_drive_map(plan),
                             sandbox_root=args.into or "")
    profile_from, profile_to = suggest_profile_remap(plan.info)
    if profile_from and not args.into:
        print(f"User folder changed: sending {profile_from} -> {profile_to}")
        options.profile_from, options.profile_to = profile_from, profile_to

    missing = [b for b, target in options.drive_map.items()
               if not target and not args.into]
    if missing:
        print(f"No destination for drive(s): {', '.join(missing)}. "
              f"Use --into to restore everything into one folder instead.")
        return 2

    outcome = run_restore(backup_dir, options, plan=plan,
                          progress=lambda p: _progress_line(
                              f"  {int(p.fraction * 100):3d}%  "
                              f"{p.files_done:,}/{p.files_total:,}  "
                              f"{os.path.basename(p.current_file)[:40]}"))
    print()
    print(outcome.summary())
    for message in outcome.errors[:20]:
        print(f"  ! {message}")
    return 0 if outcome.ok else 1


def main(argv: list[str] | None = None) -> int:
    # Before parsing, because argparse prints --version and usage errors itself.
    ensure_output()
    args = build_parser().parse_args(argv)

    if args.list_drives:
        return _print_drives()
    if args.list_categories:
        return _print_categories()

    restore_dir = None
    if args.restore is not None:
        restore_dir = args.restore or find_backup_root() or ""
        if not restore_dir:
            print("No backup folder given, and this program is not sitting "
                  "inside one.")
            return 2

    if args.no_gui:
        if restore_dir:
            return run_cli_restore(args, restore_dir)
        if args.backup:
            return run_cli_backup(args)
        print("Nothing to do. Use --backup or --restore with --no-gui.")
        return 2

    from .ui.app import launch  # imported late so the CLI works without tkinter
    return launch(restore_dir=restore_dir)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
