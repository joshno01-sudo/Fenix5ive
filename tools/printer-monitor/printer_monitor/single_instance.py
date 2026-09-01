"""Keep one copy of the monitor running at a time.

Once the program is installed with a desktop icon *and* a startup entry, it is
easy to launch a second copy on top of the one already running. Two monitors
means two lots of popups and two lots of email about the same cartridge, so the
second copy needs to bow out.

The lock is a listening socket on the loopback interface. A lock *file* would
outlive a power cut and lock the user out of their own program until they went
looking for a stale file; a socket is released by the operating system the
moment the process ends, however it ends.
"""

from __future__ import annotations

import errno
import logging
import socket
import sys
from typing import Optional

log = logging.getLogger(__name__)

# Name the Windows installer looks for (AppMutex in PrinterMonitor.iss) so it
# can say "close the program first" instead of failing to replace a file that
# is in use. Holding it is the only thing that makes that check work.
WINDOWS_MUTEX_NAME = "PrinterSupplyMonitorRunningMutex"

# Arbitrary, in the range set aside for private use, and not one of the ports
# anything common listens on. Only ever bound on the loopback interface.
#
# Two known limits, both acceptable for a shop PC that one person uses:
# something else already listening here reads as "already running", and two
# people signed in at once (fast user switching) share this one lock, so the
# second gets the notice rather than a monitor of their own.
DEFAULT_PORT = 49_517


class AlreadyRunning(RuntimeError):
    """Another copy of the program holds the lock."""


class SingleInstance:
    """Hold the lock for as long as this object is alive.

    Used as a context manager::

        try:
            with SingleInstance():
                run()
        except AlreadyRunning:
            ...
    """

    def __init__(self, port: int = DEFAULT_PORT, host: str = "127.0.0.1"):
        self.port = int(port)
        self.host = host
        self._sock: Optional[socket.socket] = None
        self._mutex = None

    def acquire(self) -> "SingleInstance":
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # Deliberately NOT SO_REUSEADDR: reusing the address is exactly
            # what would let a second copy bind alongside the first.
            sock.bind((self.host, self.port))
            sock.listen(1)
        except OSError as exc:
            sock.close()
            # Only "address in use" means another copy. Permission denied does
            # NOT: Hyper-V, WSL2 and Docker reserve blocks of ports, and a bind
            # into a reserved block returns WSAEACCES. Treating that as "already
            # running" would leave the program permanently refusing to start on
            # a machine that has never run it once.
            in_use = exc.errno == errno.EADDRINUSE or getattr(exc, "winerror", None) == 10048
            if in_use:
                raise AlreadyRunning(
                    "another copy of the monitor is already running"
                ) from exc
            # Anything else (a reserved port range, no loopback at all, a
            # locked-down host) is not worth refusing to start over — carry on
            # without the lock rather than leaving the user with no program.
            log.warning(
                "could not take the single-instance lock on port %d (%s); "
                "continuing without it",
                self.port,
                exc,
            )
            return self
        self._sock = sock
        self._claim_windows_mutex()
        return self

    def _claim_windows_mutex(self) -> None:
        """Also hold the named mutex the installer checks for, on Windows.

        Best effort: the socket above is what actually enforces one instance.
        This exists so the installer can tell the user to close the program
        rather than failing partway through replacing a file that is in use.
        """
        if sys.platform != "win32":
            return
        try:
            import ctypes

            handle = ctypes.windll.kernel32.CreateMutexW(None, False, WINDOWS_MUTEX_NAME)
            if handle:
                self._mutex = handle
        except Exception:  # noqa: BLE001 - never block startup over this
            log.debug("could not create the installer mutex", exc_info=True)

    def _release_windows_mutex(self) -> None:
        if self._mutex is None:
            return
        try:
            import ctypes

            ctypes.windll.kernel32.CloseHandle(self._mutex)
        except Exception:  # noqa: BLE001
            log.debug("could not release the installer mutex", exc_info=True)
        finally:
            self._mutex = None

    def release(self) -> None:
        self._release_windows_mutex()
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def __enter__(self) -> "SingleInstance":
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()

    @property
    def held(self) -> bool:
        return self._sock is not None
