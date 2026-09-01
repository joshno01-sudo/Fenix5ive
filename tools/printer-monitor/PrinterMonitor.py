#!/usr/bin/env python3
"""Printer Supply Monitor — window launcher.

This is what the installed PrinterMonitor.exe runs, and what you get by
double-clicking. It opens the window; everything else lives on the command
line, in printer-monitor.exe (same program, console build).

Run from a source checkout with:

    python PrinterMonitor.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from printer_monitor.cli import main  # noqa: E402

if __name__ == "__main__":
    # No arguments means "open the window", which is what a double-click wants.
    # Arguments are still honoured so a shortcut can pass, say, `monitor`.
    raise SystemExit(main(sys.argv[1:] or ["gui"]))
