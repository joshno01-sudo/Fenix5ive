#!/usr/bin/env python3
"""Test runner with a watchdog.

A hanging test tells you nothing: the job sits there until the runner kills it
and the logs never arrive. This arms faulthandler first, so if the suite stops
making progress every thread's stack is printed and the process exits non-zero.
A hang becomes a stack trace naming the exact line.

    python tests/run_tests.py [-v] [--timeout SECONDS]
"""

from __future__ import annotations

import argparse
import faulthandler
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

DEFAULT_TIMEOUT = 180


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help="seconds before dumping stacks and giving up")
    args = parser.parse_args(argv)

    # Stacks go to stderr; unittest's own output goes there too, so the dump
    # lands right after the last test that started.
    faulthandler.enable()
    if args.timeout > 0:
        faulthandler.dump_traceback_later(args.timeout, exit=True)

    # top_level_dir stays at the tests folder, matching "unittest discover -s
    # tests". Pointing it at the project root would demand tests/ be an
    # importable package, which it deliberately is not.
    suite = unittest.defaultTestLoader.discover(HERE)
    runner = unittest.TextTestRunner(verbosity=2 if args.verbose else 1,
                                     buffer=False)
    result = runner.run(suite)

    faulthandler.cancel_dump_traceback_later()
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
