"""Version and product identity.

One source of truth: the package, the Windows version resource and the
installer all read from here. Bump VERSION and the .exe metadata follows —
build/PrinterMonitor.spec generates the Windows resource from it, and a test
pins pyproject.toml and the installer to the same number.
"""

APP_NAME = "Printer Supply Monitor"
APP_SLUG = "PrinterMonitor"
VERSION = "1.1.0"

PUBLISHER = "Fenix 5ive"
TAGLINE = "Know a cartridge is running out before the job stops."
