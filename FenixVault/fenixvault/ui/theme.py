"""Colours, fonts and ttk styling.

A light, high-contrast workspace with a dark header band and a single fire
accent, so there is never any doubt about which control is the one that starts
the job. Type is deliberately a size larger than a typical utility: this gets
used at a workbench, not at a desk.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# -- palette ---------------------------------------------------------------

BG = "#eef0f4"          # window behind the panels
PANEL = "#ffffff"       # panel surfaces
PANEL_ALT = "#f7f8fa"   # panel headers, striping
HEADER_BG = "#15171c"   # top band
HEADER_FG = "#ffffff"
HEADER_MUTED = "#9aa2b1"

TEXT = "#1b1e25"
MUTED = "#6b7280"
FAINT = "#9aa1ac"
BORDER = "#d7dae1"

ACCENT = "#e2521a"      # fire orange
ACCENT_DARK = "#b8400f"
ACCENT_LIGHT = "#fdeee7"
GOLD = "#f2a03d"

OK = "#127a44"
OK_LIGHT = "#e8f5ed"
WARN = "#a35c06"
WARN_LIGHT = "#fdf3e3"
DANGER = "#b4231c"
DANGER_LIGHT = "#fdecea"

SELECT_BG = "#fbe3d7"
SELECT_FG = TEXT

# -- fonts -----------------------------------------------------------------

_PREFERRED = ["Segoe UI", "Segoe UI Variable", "Inter", "Helvetica Neue",
              "DejaVu Sans", "Liberation Sans", "Arial"]


class Fonts:
    """Resolved font tuples, created once the root window exists."""

    def __init__(self, root: tk.Misc) -> None:
        available = set(tkfont.families(root))
        family = next((name for name in _PREFERRED if name in available), None)
        if family is None:
            family = tkfont.nametofont("TkDefaultFont").cget("family")
        self.family = family
        self.title = (family, 19, "bold")
        self.subtitle = (family, 11)
        self.step = (family, 10, "bold")
        self.panel_title = (family, 12, "bold")
        self.body = (family, 10)
        self.body_bold = (family, 10, "bold")
        self.small = (family, 9)
        self.small_bold = (family, 9, "bold")
        self.mono = ("Consolas" if "Consolas" in available else "TkFixedFont", 9)
        self.huge = (family, 30, "bold")
        self.big = (family, 15, "bold")
        self.button = (family, 10, "bold")
        self.cta = (family, 13, "bold")


def apply(root: tk.Misc) -> Fonts:
    """Install the styles on *root* and return the resolved fonts."""
    fonts = Fonts(root)
    style = ttk.Style(root)
    # 'clam' is the only stock theme that honours background colours on every
    # platform, which is what makes a consistent look possible at all.
    try:
        style.theme_use("clam")
    except tk.TclError:  # pragma: no cover - only on exotic Tk builds
        pass

    style.configure(".", font=fonts.body, background=BG, foreground=TEXT)

    style.configure("App.TFrame", background=BG)
    style.configure("Header.TFrame", background=HEADER_BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("PanelHead.TFrame", background=PANEL_ALT)
    style.configure("Status.TFrame", background=PANEL_ALT)

    style.configure("Header.TLabel", background=HEADER_BG, foreground=HEADER_FG)
    style.configure("HeaderTitle.TLabel", background=HEADER_BG,
                    foreground=HEADER_FG, font=fonts.title)
    style.configure("HeaderSub.TLabel", background=HEADER_BG,
                    foreground=HEADER_MUTED, font=fonts.subtitle)
    style.configure("HeaderAccent.TLabel", background=HEADER_BG,
                    foreground=GOLD, font=fonts.step)

    style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
    style.configure("PanelHead.TLabel", background=PANEL_ALT, foreground=TEXT,
                    font=fonts.panel_title)
    style.configure("PanelHint.TLabel", background=PANEL_ALT, foreground=MUTED,
                    font=fonts.small)
    style.configure("Muted.TLabel", background=PANEL, foreground=MUTED,
                    font=fonts.small)
    style.configure("Body.TLabel", background=PANEL, foreground=TEXT,
                    font=fonts.body)
    style.configure("Big.TLabel", background=PANEL, foreground=TEXT,
                    font=fonts.big)
    style.configure("Huge.TLabel", background=PANEL, foreground=ACCENT,
                    font=fonts.huge)
    style.configure("Ok.TLabel", background=PANEL, foreground=OK,
                    font=fonts.small_bold)
    style.configure("Warn.TLabel", background=PANEL, foreground=WARN,
                    font=fonts.small_bold)
    style.configure("Danger.TLabel", background=PANEL, foreground=DANGER,
                    font=fonts.small_bold)
    style.configure("Step.TLabel", background=PANEL_ALT, foreground=PANEL,
                    font=fonts.step)

    style.configure("TButton", font=fonts.button, padding=(12, 6),
                    background="#e6e8ec", foreground=TEXT,
                    borderwidth=1, relief="flat")
    style.map("TButton",
              background=[("active", "#d9dce2"), ("disabled", "#eef0f3")],
              foreground=[("disabled", FAINT)])

    style.configure("Primary.TButton", font=fonts.cta, padding=(16, 12),
                    background=ACCENT, foreground="#ffffff",
                    borderwidth=0, relief="flat")
    style.map("Primary.TButton",
              background=[("active", ACCENT_DARK), ("disabled", "#e3c8bc")],
              foreground=[("disabled", "#ffffff")])

    style.configure("Ghost.TButton", font=fonts.small_bold, padding=(9, 4),
                    background=PANEL, foreground=MUTED, borderwidth=1,
                    relief="flat")
    style.map("Ghost.TButton",
              background=[("active", PANEL_ALT)],
              foreground=[("active", ACCENT)])

    style.configure("HeaderGhost.TButton", font=fonts.small_bold, padding=(10, 5),
                    background="#272a32", foreground="#e6e8ee",
                    borderwidth=0, relief="flat")
    style.map("HeaderGhost.TButton", background=[("active", "#343843")])

    style.configure("Danger.TButton", font=fonts.small_bold, padding=(10, 5),
                    background=DANGER_LIGHT, foreground=DANGER, borderwidth=0)
    style.map("Danger.TButton", background=[("active", "#f8d7d4")])

    style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                    foreground=TEXT, rowheight=23, borderwidth=0,
                    font=fonts.body)
    style.map("Treeview",
              background=[("selected", SELECT_BG)],
              foreground=[("selected", SELECT_FG)])
    style.configure("Treeview.Heading", background=PANEL_ALT, foreground=MUTED,
                    font=fonts.small_bold, relief="flat", padding=(6, 5))
    style.map("Treeview.Heading", background=[("active", "#eceef2")])
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    style.configure("TCheckbutton", background=PANEL, foreground=TEXT,
                    font=fonts.small)
    style.map("TCheckbutton",
              background=[("active", PANEL)],
              indicatorcolor=[("selected", ACCENT), ("!selected", "#ffffff")])

    style.configure("TEntry", fieldbackground="#ffffff", borderwidth=1,
                    relief="solid", padding=5)
    style.configure("TCombobox", fieldbackground="#ffffff", padding=4)

    style.configure("TProgressbar", background=ACCENT, troughcolor="#dfe2e8",
                    borderwidth=0, thickness=10)
    style.configure("Done.TProgressbar", background=OK, troughcolor="#dfe2e8",
                    borderwidth=0, thickness=10)

    style.configure("TPanedwindow", background=BG)
    style.configure("Sash", sashthickness=8, gripcount=0)

    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", padding=(14, 7), font=fonts.small_bold,
                    background=PANEL_ALT)
    style.map("TNotebook.Tab",
              background=[("selected", PANEL)],
              foreground=[("selected", ACCENT)])

    style.configure("TSeparator", background=BORDER)
    style.configure("Vertical.TScrollbar", background="#c9ced7",
                    troughcolor=PANEL_ALT, borderwidth=0, arrowsize=12)
    style.configure("Horizontal.TScrollbar", background="#c9ced7",
                    troughcolor=PANEL_ALT, borderwidth=0, arrowsize=12)

    return fonts


# -- checkbox artwork ------------------------------------------------------

_BOX = 16      # drawn box size
_WIDTH = 20    # image width, leaving a gap before the label


def _blank(width: int, height: int) -> tk.PhotoImage:
    return tk.PhotoImage(width=width, height=height)


def _fill(image: tk.PhotoImage, colour: str, box: tuple[int, int, int, int]) -> None:
    x1, y1, x2, y2 = box
    image.put(colour, to=(x1, y1, x2 + 1, y2 + 1))


def _make_checkbox(state: str) -> tk.PhotoImage:
    """Draw one 20x16 checkbox image for ``on`` / ``off`` / ``partial``."""
    image = _blank(_WIDTH, _BOX)

    if state == "on":
        border, inner, mark = ACCENT, ACCENT, "#ffffff"
    elif state == "partial":
        border, inner, mark = ACCENT, "#ffffff", ACCENT
    else:
        border, inner, mark = "#a8afba", "#ffffff", None

    # Everything starts transparent; only the box is painted.
    _fill(image, border, (1, 1, _BOX - 2, _BOX - 2))
    _fill(image, inner, (2, 2, _BOX - 3, _BOX - 3))

    if state == "on" and mark:
        stroke = [(4, 8), (5, 9), (6, 10), (7, 9), (8, 8), (9, 7), (10, 6), (11, 5)]
        for x, y in stroke:
            _fill(image, mark, (x, y, x, y + 1))
    elif state == "partial" and mark:
        _fill(image, mark, (4, 7, 11, 8))

    for x in range(_BOX, _WIDTH):
        for y in range(_BOX):
            image.transparency_set(x, y, True)
    for x in range(_BOX):
        image.transparency_set(x, 0, True)
        image.transparency_set(x, _BOX - 1, True)
    for y in range(_BOX):
        image.transparency_set(0, y, True)
        image.transparency_set(_BOX - 1, y, True)
    return image


class Icons:
    """Images must outlive the widgets that show them, so they live here."""

    def __init__(self) -> None:
        self.check_on = _make_checkbox("on")
        self.check_off = _make_checkbox("off")
        self.check_partial = _make_checkbox("partial")

    def checkbox(self, state: str) -> tk.PhotoImage:
        if state == "on":
            return self.check_on
        if state == "partial":
            return self.check_partial
        return self.check_off
