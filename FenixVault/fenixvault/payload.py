"""Make the backup folder able to restore itself.

This is the piece that turns a folder of copied files into something you can
drag onto a USB drive, carry to another PC, double-click, and get everything
back. The backup carries the program with it, so the second machine needs
nothing installed -- no Python, no Fenix Vault, nothing.

When running from a packaged ``.exe`` we simply copy that exe in beside the
data. When running from source we copy the source in and drop a ``.bat`` next
to it, so development builds behave the same way.
"""

from __future__ import annotations

import os
import shutil
import sys

from .manifest import BackupInfo, README_FILENAME
from .platformutil import human_bytes, long_path
from .version import APP_NAME, VERSION

RESTORE_EXE_NAME = "RESTORE.exe"
RESTORE_BAT_NAME = "RESTORE.bat"
RESTORE_SH_NAME = "restore.sh"
TOOL_DIR_NAME = "_RestoreTool"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def package_root() -> str:
    """The folder holding ``fenixvault/`` and the entry script."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def install_restore_tool(backup_dir: str, info: BackupInfo) -> list[str]:
    """Place the restore program and instructions inside *backup_dir*."""
    written: list[str] = []
    written.append(_write_readme(backup_dir, info))
    if is_frozen():
        copied = _copy_frozen_exe(backup_dir)
        if copied:
            written.append(copied)
    else:
        written.extend(_copy_source_tool(backup_dir))
    return written


def _copy_frozen_exe(backup_dir: str) -> str | None:
    source = sys.executable
    target = os.path.join(backup_dir, RESTORE_EXE_NAME)
    try:
        if os.path.isfile(long_path(target)) and \
                os.path.getsize(long_path(target)) == os.path.getsize(long_path(source)):
            return target
        shutil.copy2(long_path(source), long_path(target))
        return target
    except OSError:
        return None


def _ignore_junk(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names
            if name in ("__pycache__", ".git", "tests", "build", "dist")
            or name.endswith((".pyc", ".pyo", ".spec"))}


def _copy_source_tool(backup_dir: str) -> list[str]:
    """Development fallback: ship the source plus a launcher."""
    written: list[str] = []
    root = package_root()
    tool_dir = os.path.join(backup_dir, TOOL_DIR_NAME)
    package_src = os.path.join(root, "fenixvault")
    package_dst = os.path.join(tool_dir, "fenixvault")
    try:
        if os.path.isdir(package_dst):
            shutil.rmtree(package_dst, ignore_errors=True)
        os.makedirs(tool_dir, exist_ok=True)
        shutil.copytree(package_src, package_dst, ignore=_ignore_junk)
        written.append(package_dst)
        entry = os.path.join(root, "FenixVault.py")
        if os.path.isfile(entry):
            shutil.copy2(entry, os.path.join(tool_dir, "FenixVault.py"))
            written.append(os.path.join(tool_dir, "FenixVault.py"))
    except OSError:
        return written

    bat = os.path.join(backup_dir, RESTORE_BAT_NAME)
    with open(bat, "w", encoding="utf-8", newline="\r\n") as handle:
        handle.write(
            "@echo off\r\n"
            "REM Double-click this file to put the backup back.\r\n"
            f"title {APP_NAME} - Restore\r\n"
            "cd /d \"%~dp0\"\r\n"
            "where pythonw >nul 2>nul && (\r\n"
            f"  start \"\" pythonw \"{TOOL_DIR_NAME}\\FenixVault.py\" --restore \"%~dp0\"\r\n"
            "  exit /b 0\r\n"
            ")\r\n"
            "where python >nul 2>nul && (\r\n"
            f"  python \"{TOOL_DIR_NAME}\\FenixVault.py\" --restore \"%~dp0\"\r\n"
            "  exit /b 0\r\n"
            ")\r\n"
            "echo Python was not found on this PC.\r\n"
            "echo Install it free from https://www.python.org/downloads/ "
            "and run this file again.\r\n"
            "pause\r\n"
        )
    written.append(bat)

    shell = os.path.join(backup_dir, RESTORE_SH_NAME)
    with open(shell, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            "#!/bin/sh\n"
            "# Put the backup back (macOS / Linux).\n"
            'cd "$(dirname "$0")" || exit 1\n'
            f'exec python3 "{TOOL_DIR_NAME}/FenixVault.py" --restore "$(pwd)"\n'
        )
    try:
        os.chmod(shell, 0o755)
    except OSError:
        pass
    written.append(shell)
    return written


def _write_readme(backup_dir: str, info: BackupInfo) -> str:
    path = os.path.join(backup_dir, README_FILENAME)
    launcher = RESTORE_EXE_NAME if is_frozen() else RESTORE_BAT_NAME
    lines = [
        f"{APP_NAME} {VERSION} - HOW TO GET YOUR FILES BACK",
        "=" * 62,
        "",
        "WHAT THIS FOLDER IS",
        "-------------------",
        "A complete copy of the personal and business files from:",
        "",
        f"    Computer : {info.source_computer or 'unknown'}",
        f"    User     : {info.source_user or 'unknown'}",
        f"    System   : {info.source_os or 'unknown'}",
        f"    Made on  : {info.created_utc or 'unknown'} (UTC)",
        f"    Contains : {info.total_files:,} files, "
        f"{human_bytes(info.total_bytes)}",
        "",
        "The folders inside 'Data' are laid out exactly the way they were on",
        "the original computer, so you can also just open them and drag out",
        "any single file you need.",
        "",
        "TO PUT EVERYTHING BACK",
        "----------------------",
        "1. Plug this drive into the computer you want the files on.",
        "2. Open this folder.",
        f"3. Double-click  {launcher}",
        "4. Check the drive letters it shows you, then press 'Put My Files Back'.",
        "",
        "That is all. It rebuilds every folder and drops every file back into",
        "the same place it came from. Files already on the new computer are",
        "left alone unless you tell it otherwise.",
        "",
        "IF THE USER NAME IS DIFFERENT",
        "-----------------------------",
        "The program notices and offers to send everything to the new user's",
        "folders instead. Just accept the suggestion it shows.",
        "",
        "IF A DRIVE LETTER IS MISSING",
        "----------------------------",
        "If these files came off a drive the new computer does not have, the",
        "program asks you to pick a folder for them. Nothing is written until",
        "you choose.",
        "",
        "IF YOU WANT TO BE CAREFUL",
        "-------------------------",
        "Tick 'Restore into one folder instead' and pick an empty folder. The",
        "whole tree is rebuilt inside it and nothing on the computer is",
        "touched. Then move things across by hand.",
        "",
        "WHAT ELSE IS IN HERE",
        "--------------------",
        "  Data\\             your files, in their original folder structure",
        "  manifest.jsonl    the list of every file and its fingerprint",
        "  backup-info.json  where this backup came from",
        "  backup-report.txt only present if something could not be copied",
        "",
        "Every file was fingerprinted when it was copied, and the fingerprint",
        "is checked again when it is restored, so you will be told if anything",
        "was damaged in transit.",
        "",
    ]
    with open(path, "w", encoding="utf-8", newline="\r\n") as handle:
        handle.write("\n".join(lines))
    return path
