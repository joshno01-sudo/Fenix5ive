#!/usr/bin/env python3
"""Printer Supply Monitor — command line launcher.

Built as printer-monitor.exe: a console program, so `check`, `scan`, `stock`
and `monitor` print where you can see them and return a usable exit code for
Task Scheduler. The windowed build is PrinterMonitor.exe.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from printer_monitor.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
