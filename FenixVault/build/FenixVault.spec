# PyInstaller spec for Fenix Vault.  Build with:
#
#     pyinstaller build/FenixVault.spec --noconfirm
#
# Produces a single dist/FenixVault.exe with no dependencies at all -- the copy
# of it that ends up inside every backup has to run on a machine where nothing
# is installed, so one self-contained file is the whole point.

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))
BUILD = os.path.join(ROOT, "build")
ICON = os.path.join(BUILD, "fenixvault.ico")

analysis = Analysis(
    [os.path.join(ROOT, "FenixVault.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    # The UI modules are imported inside functions so the command line works
    # without a display; name them so they are packaged all the same.
    hiddenimports=[
        "fenixvault.ui",
        "fenixvault.ui.app",
        "fenixvault.ui.theme",
        "fenixvault.ui.widgets",
        "fenixvault.ui.help_window",
        "fenixvault.ui.restore_window",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Nothing here is used, and each one costs megabytes in an exe that
        # gets copied onto every backup drive. Kept to third-party packages
        # only -- excluding stdlib modules saves little and risks a bundle
        # that builds fine and then fails on someone else's PC.
        "numpy", "PIL", "matplotlib", "scipy", "pandas",
        "pytest", "setuptools", "pip",
    ],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="FenixVault",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX-packed exes trip antivirus heuristics
    runtime_tmpdir=None,
    console=False,      # a window, not a terminal
    disable_windowed_traceback=False,
    icon=ICON if os.path.isfile(ICON) else None,
    version=os.path.join(BUILD, "version_info.txt"),
)
