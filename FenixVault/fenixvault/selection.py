"""Which folders are in, which are out.

The left-hand tree lets a folder be ticked, then a subfolder inside it
un-ticked. Storing one boolean per visible node would not survive lazy loading
(most nodes have never been expanded, so they have no stored state), so instead
we keep a sparse set of *rules*: an explicit include or exclude on a handful of
paths. Any path's state is resolved by walking up to the nearest rule. That
scales to a whole drive and makes "tick C:\\ then untick one folder" a two-entry
model rather than a million-entry one.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .platformutil import IS_WINDOWS, ancestors_of, is_ancestor, norm

ON = "on"
OFF = "off"
PARTIAL = "partial"


class FolderSelection:
    """Sparse include/exclude rules over the filesystem tree."""

    def __init__(self) -> None:
        # normalised path -> True (include this subtree) / False (exclude it)
        self._rules: dict[str, bool] = {}

    # -- mutation ---------------------------------------------------------

    def set(self, path: str, included: bool) -> None:
        """Include or exclude *path* and everything beneath it.

        Rules on descendants are dropped, because ticking a folder means "all
        of this" and any finer-grained decision inside it is now moot.
        """
        key = norm(path)
        for existing in [p for p in self._rules if is_ancestor(key, p)]:
            del self._rules[existing]
        # A rule that merely restates what the parent already says is noise.
        if self._effective_of_parent(key) == included:
            self._rules.pop(key, None)
        else:
            self._rules[key] = included

    def toggle(self, path: str) -> bool:
        """Flip *path* between fully-in and fully-out. Returns the new state."""
        new_state = self.state(path) != ON
        self.set(path, new_state)
        return new_state

    def clear(self) -> None:
        self._rules.clear()

    # -- queries ----------------------------------------------------------

    def _effective_of_parent(self, key: str) -> bool:
        for ancestor in ancestors_of(key):
            if ancestor in self._rules:
                return self._rules[ancestor]
        return False

    def effective(self, path: str) -> bool:
        """True when *path* would be backed up, ignoring finer rules below it."""
        key = norm(path)
        if key in self._rules:
            return self._rules[key]
        return self._effective_of_parent(key)

    def state(self, path: str) -> str:
        """Checkbox state for *path*: fully on, fully off, or mixed."""
        key = norm(path)
        effective = self.effective(key)
        for rule_path, _ in self._rules.items():
            if is_ancestor(key, rule_path) and self.effective(rule_path) != effective:
                return PARTIAL
        return ON if effective else OFF

    def roots(self) -> list[str]:
        """Minimal set of included subtree roots, for walking."""
        out = [p for p, included in self._rules.items()
               if included and not self._effective_of_parent(p)]
        return sorted(out)

    def excluded_under(self, root: str) -> list[str]:
        """Explicit exclusions carved out of *root*."""
        key = norm(root)
        return sorted(p for p, included in self._rules.items()
                      if not included and is_ancestor(key, p))

    def rules(self) -> dict[str, bool]:
        return dict(self._rules)

    def load(self, rules: dict[str, bool]) -> None:
        self._rules = {norm(p): bool(v) for p, v in rules.items()}

    def is_empty(self) -> bool:
        return not any(self._rules.values())

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"FolderSelection({self._rules!r})"


# --------------------------------------------------------------------------
# Folders that are never worth copying
# --------------------------------------------------------------------------

# Skipped no matter what: unreadable, or actively harmful to copy.
ALWAYS_SKIP_NAMES = {
    "$recycle.bin",
    "recycler",
    "system volume information",
    "$windows.~ws",
    "$windows.~bt",
    "$winreagent",
    "$sysreset",
    "config.msi",
}

# Program and OS folders. Skipped while "Skip Windows and program folders" is
# on, which is the default -- these hold installed software, not your work.
SYSTEM_DIR_NAMES = {
    "windows",
    "winnt",
    "program files",
    "program files (x86)",
    "programdata",
    "perflogs",
    "recovery",
    "windows.old",
    "msocache",
    "boot",
    "efi",
    "system32",
    "drivers",
}

# Caches and build output. Never personal data, frequently enormous.
JUNK_DIR_NAMES = {
    "temp", "tmp", "temporary internet files",
    "cache", "caches", "cache2", "cachestorage", "code cache", "gpucache",
    "shadercache", "inetcache", "webcache", "crashdumps", "crashpad",
    "package cache", "packages", "servicing",
    "node_modules", "__pycache__", ".git", ".svn", ".hg", ".venv", "venv",
    "site-packages", "dist-packages",
    ".gradle", ".nuget", ".cargo", ".m2", ".npm", ".yarn", ".pub-cache",
    "obj", "bin\\debug", "spotify", "steamapps",
    "microsoftedgebackups", "onedrivetemp",
}

# Files that are never user data even when their extension matches.
SKIP_FILE_NAMES = {
    "pagefile.sys", "swapfile.sys", "hiberfil.sys", "dumpstack.log",
    "dumpstack.log.tmp", "ntuser.dat", "usrclass.dat", "desktop.ini",
    "thumbs.db", "ehthumbs.db", ".ds_store",
}

# Inside AppData\Local almost everything is a cache, but a few folders hold real
# irreplaceable data -- an Outlook mailbox above all. So AppData\Local is
# skipped by default with these carved back in.
APPDATA_LOCAL_KEEP = (
    os.path.join("microsoft", "outlook"),
    os.path.join("microsoft", "windows", "sticky notes"),
    os.path.join("microsoft", "onenote"),
    os.path.join("thunderbird", "profiles"),
    os.path.join("mozilla", "firefox", "profiles"),
)


@dataclass
class ExcludeRules:
    """Policy for folders the user has not explicitly ruled on."""

    skip_system: bool = True
    skip_junk: bool = True
    skip_appdata_local: bool = True
    skip_hidden: bool = True
    # Extra folder names the caller wants ignored, lowercase.
    extra_names: set[str] = field(default_factory=set)

    def should_skip_dir(self, dirpath: str, dirname: str) -> bool:
        """True when the walker should not descend into *dirpath*/*dirname*."""
        lowered = dirname.lower()
        if lowered in ALWAYS_SKIP_NAMES:
            return True
        if lowered in self.extra_names:
            return True
        if self.skip_junk and lowered in JUNK_DIR_NAMES:
            return True
        if self.skip_system and lowered in SYSTEM_DIR_NAMES:
            # Only treat these as system folders at a drive root; a user folder
            # innocently named "Recovery" deep in Documents is fair game.
            if _is_drive_root(dirpath):
                return True
            if lowered in ("windows", "program files", "program files (x86)",
                           "programdata", "windows.old"):
                return True
        if self.skip_appdata_local and _is_skipped_appdata(dirpath, dirname):
            return True
        if self.skip_hidden and _is_hidden(os.path.join(dirpath, dirname)):
            return True
        return False

    def should_skip_file(self, filename: str) -> bool:
        return filename.lower() in SKIP_FILE_NAMES


def _is_drive_root(path: str) -> bool:
    normalised = norm(path)
    if IS_WINDOWS:
        return len(normalised) <= 3 and normalised.endswith("\\")
    return normalised == "/"


def _is_skipped_appdata(dirpath: str, dirname: str) -> bool:
    """True for AppData\\Local subfolders outside the keep-list."""
    # Lowercased here rather than leaning on norm(), which only case-folds on
    # Windows -- this comparison has to be case-insensitive wherever it runs.
    full = norm(os.path.join(dirpath, dirname)).lower()
    marker = "\\appdata\\local\\" if IS_WINDOWS else "/appdata/local/"
    index = full.find(marker)
    if index == -1:
        return False
    tail = full[index + len(marker):]
    sep = "\\" if IS_WINDOWS else "/"
    for keep in APPDATA_LOCAL_KEEP:
        keep_normalised = keep.replace("\\", sep).replace("/", sep).lower()
        # Keep the folder itself and everything under it, plus every parent on
        # the way down so the walker can actually reach it.
        if tail.startswith(keep_normalised) or keep_normalised.startswith(tail + sep):
            return False
    return True


def _is_hidden(path: str) -> bool:
    name = os.path.basename(path.rstrip("\\/"))
    if not IS_WINDOWS:
        return name.startswith(".")
    if name.startswith("."):
        return True
    try:
        import ctypes
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attrs == -1:
            return False
        FILE_ATTRIBUTE_HIDDEN = 0x2
        FILE_ATTRIBUTE_SYSTEM = 0x4
        return bool(attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))
    except Exception:
        return False
