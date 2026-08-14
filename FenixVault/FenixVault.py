#!/usr/bin/env python3
"""Fenix Vault - launcher.

Double-clicked, this opens the window. Sitting inside a backup folder (which is
where the copy placed by ``payload.py`` lives), it opens straight into restore
mode instead.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fenixvault.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
