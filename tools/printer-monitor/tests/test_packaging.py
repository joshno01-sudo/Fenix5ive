"""The installable build: version consistency, single instance, entry points.

The .exe and the installer themselves can only be built on Windows, and CI
does that. These are the parts that can be checked anywhere — and the ones
most likely to rot quietly, because a wrong version number in the installer
still builds and still installs.
"""

from __future__ import annotations

import re
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from printer_monitor import version as version_module
from printer_monitor.single_instance import (
    WINDOWS_MUTEX_NAME,
    AlreadyRunning,
    SingleInstance,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def lock_port() -> int:
    """A free port, so the suite never fights a monitor running on this machine."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]

ISS = ROOT / "installer" / "PrinterMonitor.iss"
SPEC = ROOT / "build" / "PrinterMonitor.spec"
ICON = ROOT / "build" / "printermonitor.ico"


# ---------------------------------------------------------------------------
# Version, in three files that must agree
# ---------------------------------------------------------------------------


def _iss_define(name: str) -> str:
    match = re.search(rf'^#define\s+{name}\s+"(.*)"', ISS.read_text(), re.MULTILINE)
    assert match, f"{name} is not defined in {ISS.name}"
    return match.group(1)


def test_the_installer_version_matches_the_package():
    """A stale number here ships an installer that lies about what it holds."""
    assert _iss_define("AppVersion") == version_module.VERSION


def test_the_installer_names_match_the_package():
    assert _iss_define("AppName") == version_module.APP_NAME
    assert _iss_define("AppPublisher") == version_module.PUBLISHER


def test_pyproject_version_matches_the_package():
    text = (ROOT / "pyproject.toml").read_text()
    match = re.search(r'^version\s*=\s*"(.*)"', text, re.MULTILINE)
    assert match, "pyproject.toml has no version"
    assert match.group(1) == version_module.VERSION


def test_version_is_a_sensible_number():
    assert re.fullmatch(r"\d+\.\d+\.\d+", version_module.VERSION), version_module.VERSION


def test_cli_reports_the_version():
    from printer_monitor.cli import main

    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0


# ---------------------------------------------------------------------------
# The two executables the installer ships
# ---------------------------------------------------------------------------


def test_both_launchers_exist():
    assert (ROOT / "PrinterMonitor.py").is_file(), "the windowed launcher is missing"
    assert (ROOT / "printer-monitor.py").is_file(), "the console launcher is missing"


def test_the_spec_builds_both_executables():
    spec = SPEC.read_text()
    assert 'name="PrinterMonitor"' in spec
    assert 'name="printer-monitor"' in spec
    # The windowed one must not have a console, and the CLI one must.
    assert "console=False" in spec
    assert "console=True" in spec


def test_the_spec_packages_the_lazily_imported_gui():
    """The GUI is imported inside functions, so PyInstaller cannot see it."""
    spec = SPEC.read_text()
    for module in (
        "printer_monitor.gui.app",
        "printer_monitor.gui.dashboard",
        "printer_monitor.gui.settings",
        "printer_monitor.gui.supplies",
        "printer_monitor.gui.popup",
        "tkinter",
    ):
        assert module in spec, f"{module} would be missing from the build"


def test_the_installer_ships_the_whole_folder_not_one_exe():
    """Both programs share one _internal folder; shipping one file loses it."""
    iss = ISS.read_text()
    assert r"..\dist\PrinterMonitor\*" in iss
    assert "recursesubdirs" in iss


def test_the_startup_shortcut_starts_minimised():
    # Read directives, not the raw file: an earlier version of this test
    # asserted "{userstartup}" was present — the very thing that put the
    # shortcut in the administrator's profile — and went on passing after the
    # fix only because the word survives in the comment explaining it.
    directives = _iss_directives()
    assert 'Parameters: "gui --minimized"' in directives
    assert "{autostartup}" in directives


def test_the_windowed_launcher_defaults_to_the_gui():
    source = (ROOT / "PrinterMonitor.py").read_text()
    assert '["gui"]' in source, "a double-click must open the window"


def test_the_icon_is_a_valid_multi_size_ico():
    import struct

    assert ICON.is_file(), "the icon the spec and installer both point at is missing"
    data = ICON.read_bytes()
    reserved, image_type, count = struct.unpack("<HHH", data[:6])
    assert (reserved, image_type) == (0, 1), "not an .ico file"
    assert count >= 5, "too few sizes; Windows picks badly when it has to scale"

    sizes = []
    for index in range(count):
        entry = data[6 + 16 * index : 22 + 16 * index]
        width, _h, _c, _r, _planes, bpp, length, offset = struct.unpack("<BBBBHHII", entry)
        sizes.append(width or 256)
        assert bpp == 32, "32-bit gives the alpha channel the rounded corners need"
        assert offset + length <= len(data), "image data runs past the end of the file"
    assert 16 in sizes, "no 16x16: the taskbar and title bar would scale a big one"
    assert 256 in sizes, "no 256x256: large icons in Explorer would be blurry"


# ---------------------------------------------------------------------------
# One instance at a time
# ---------------------------------------------------------------------------


def test_a_second_instance_is_refused(lock_port):
    with SingleInstance(port=lock_port) as first:
        assert first.held
        with pytest.raises(AlreadyRunning):
            SingleInstance(port=lock_port).acquire()


def test_the_lock_is_released_on_exit(lock_port):
    with SingleInstance(port=lock_port):
        pass
    second = SingleInstance(port=lock_port)
    try:
        second.acquire()
        assert second.held
    finally:
        second.release()


def test_releasing_twice_is_harmless(lock_port):
    lock = SingleInstance(port=lock_port).acquire()
    lock.release()
    lock.release()
    assert not lock.held


def test_the_lock_does_not_survive_the_process(lock_port):
    """A crash must not lock the user out of their own program.

    A lock file would; a socket is closed by the OS however the process ends.
    """
    code = (
        "import sys; sys.path.insert(0, %r);"
        "from printer_monitor.single_instance import SingleInstance;"
        "SingleInstance(port=%d).acquire(); print('locked', flush=True);"
        "import os; os._exit(1)" % (str(ROOT), lock_port)
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert "locked" in result.stdout

    # The killed process held it; this one must still be able to take it.
    survivor = SingleInstance(port=lock_port)
    try:
        survivor.acquire()
        assert survivor.held
    finally:
        survivor.release()


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(("EACCES", None), id="reserved-port-range"),
        pytest.param(("EPERM", None), id="blocked-by-policy"),
        pytest.param(("EACCES", 10013), id="windows-WSAEACCES"),
    ],
)
def test_only_address_in_use_means_another_copy(monkeypatch, error):
    """Hyper-V, WSL2 and Docker reserve port blocks, and a bind into one fails
    with "permission denied". Reading that as "already running" would leave the
    program permanently refusing to start on a PC that never ran it once."""
    import errno as errno_module

    name, winerror = error
    code = getattr(errno_module, name)

    class Refusing(socket.socket):
        def bind(self, *args, **kwargs):
            exc = OSError(code, "reserved or blocked")
            if winerror is not None:
                exc.winerror = winerror
            raise exc

    monkeypatch.setattr(socket, "socket", Refusing)
    lock = SingleInstance().acquire()  # must not raise
    assert not lock.held  # ran without the lock rather than refusing to start


def test_address_in_use_still_means_another_copy(monkeypatch):
    import errno as errno_module

    class InUse(socket.socket):
        def bind(self, *args, **kwargs):
            raise OSError(errno_module.EADDRINUSE, "address already in use")

    monkeypatch.setattr(socket, "socket", InUse)
    with pytest.raises(AlreadyRunning):
        SingleInstance().acquire()


def test_the_monitor_command_takes_the_lock_too(tmp_path, capsys):
    """`monitor` is the scheduled-task path; running it beside the open window
    would poll and alert twice over."""
    from printer_monitor.cli import main
    from printer_monitor.config import AppConfig, PrinterConfig, SnmpSettings

    config = tmp_path / "config.json"
    AppConfig(
        printers=[
            PrinterConfig(
                id="p", name="P", host="127.0.0.1",
                snmp=SnmpSettings(port=9, timeout=0.2, retries=0),
            )
        ]
    ).save(config)

    with SingleInstance():  # stand in for an already-open window
        code = main(
            ["--config", str(config), "--db", str(tmp_path / "d.db"), "monitor"]
        )
    assert code == 2
    assert "already running" in capsys.readouterr().err


def _iss_directives(section: str = "") -> str:
    """The .iss with comment lines stripped, optionally just one section.

    Two ways an assertion here can pass while the installer is wrong, both of
    which have happened: the string survives in a comment explaining why it is
    no longer used, or it appears in a different section. Stripping comments
    handles the first; naming a section handles the second.
    """
    lines = [
        line for line in ISS.read_text().splitlines() if not line.lstrip().startswith(";")
    ]
    if not section:
        return "\n".join(lines)

    wanted = f"[{section}]".lower()
    out: list[str] = []
    inside = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            inside = stripped.lower() == wanted
            continue
        if inside:
            out.append(line)
    assert out, f"the .iss has no [{section}] section"
    return "\n".join(out)


def test_the_installer_startup_shortcut_is_not_user_scoped():
    """An elevated install writing to {userstartup} puts the shortcut in the
    admin's profile, where the everyday account never runs it."""
    directives = _iss_directives()
    assert "{autostartup}" in directives
    assert "{userstartup}" not in directives


def test_the_path_task_writes_the_key_windows_actually_reads():
    """HKLM\\Environment looks right and changes nothing; the machine PATH
    lives under Session Manager."""
    session_manager = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"

    # The [Registry] entry specifically — the same string also appears in the
    # [Code] block, so checking the whole file would pass with the wrong key here.
    registry = _iss_directives("Registry")
    assert session_manager in registry, "the PATH entry writes a key Windows does not read"
    assert "ChangesEnvironment=yes" in _iss_directives("Setup")

    # ...and the check must read the same key it writes, or an upgrade appends
    # the folder to PATH all over again.
    code = _iss_directives("Code")
    assert "HKEY_LOCAL_MACHINE" in code
    assert session_manager in code
    assert "HKEY_CURRENT_USER" not in code


def test_each_executable_gets_its_own_version_resource():
    spec = SPEC.read_text()
    assert 'GUI_VERSION_INFO = _write_version_info("PrinterMonitor")' in spec
    assert 'CLI_VERSION_INFO = _write_version_info("printer-monitor")' in spec
    assert "version=GUI_VERSION_INFO" in spec
    assert "version=CLI_VERSION_INFO" in spec


def test_the_mutex_name_matches_the_installer():
    """Inno's AppMutex only works if the program actually holds that name."""
    iss = ISS.read_text()
    assert f"AppMutex={WINDOWS_MUTEX_NAME}" in iss


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only mutex")
def test_the_windows_mutex_is_held(lock_port):  # pragma: no cover - Windows CI only
    with SingleInstance(port=lock_port) as lock:
        assert lock._mutex, "the installer's AppMutex check would never fire"


def test_the_already_running_notice_closes_itself():
    """An unattended startup must not leave a dialog nobody can dismiss.

    The startup shortcut fires whether or not somebody already has the monitor
    open, so a modal box here would sit on the desktop until someone clicked it.
    """
    source = (ROOT / "printer_monitor" / "gui" / "app.py").read_text()
    notice = source.split("def _warn_already_running")[1].split("\ndef ")[0]
    assert "messagebox" not in notice, "a modal box would block an unattended start"
    assert "root.after(" in notice and "root.destroy" in notice

    assert re.search(
        r"ALREADY_RUNNING_NOTICE_SECONDS\s*=\s*(\d+)", source
    ), "the auto-close delay is gone"
    seconds = int(re.search(r"ALREADY_RUNNING_NOTICE_SECONDS\s*=\s*(\d+)", source).group(1))
    assert 0 < seconds <= 30, f"{seconds}s is not a sensible time to leave it up"
