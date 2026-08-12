"""Fenix Vault - a plain-English backup program for Windows.

The package is split so the engine never imports the interface:

    platformutil  drives, known folders, long paths, archive path mapping
    catalog       the file types offered in the picker
    appdetect     what is actually installed on this PC (Windows registry)
    selection     which folders are in or out
    scanner       walking the tree and counting what is there
    manifest      the on-disk record of a backup
    backup        the copy engine
    restore       the put-it-all-back engine
    payload       makes a backup folder able to restore itself
    ui            the three-panel window

That split is what lets the whole engine be tested without a display.
"""

from .version import APP_NAME, APP_SLUG, TAGLINE, VERSION

__all__ = ["APP_NAME", "APP_SLUG", "TAGLINE", "VERSION"]
