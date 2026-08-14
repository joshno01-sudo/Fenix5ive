"""Small building blocks shared by the main window and the restore window."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from . import theme


def autowrap(label: tk.Label, source: tk.Misc, pad: int = 26) -> None:
    """Keep *label*'s wrap width tied to *source*'s width.

    Three resizable panels side by side means no fixed ``wraplength`` is ever
    right; without this, guidance text is the first thing to get clipped.
    """
    def on_configure(event: tk.Event) -> None:
        label.configure(wraplength=max(140, event.width - pad))
    source.bind("<Configure>", on_configure, add="+")


class Card(tk.Frame):
    """A white panel with a 1px border and an optional numbered header.

    Built from plain ``tk.Frame`` rather than ``ttk`` because a hairline border
    in a chosen colour is the one thing ttk frames will not reliably give you.
    """

    def __init__(self, master: tk.Misc, fonts: theme.Fonts, *,
                 step: str | None = None, title: str = "",
                 hint: str = "", **kwargs) -> None:
        super().__init__(master, bg=theme.BORDER, **kwargs)
        self.fonts = fonts
        inner = tk.Frame(self, bg=theme.PANEL)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        if title:
            head = tk.Frame(inner, bg=theme.PANEL_ALT)
            head.pack(fill="x", side="top")
            row = tk.Frame(head, bg=theme.PANEL_ALT)
            row.pack(fill="x", padx=12, pady=(10, 0))
            if step:
                badge = tk.Label(row, text=step, bg=theme.ACCENT, fg="#ffffff",
                                 font=fonts.step, width=3, pady=2)
                badge.pack(side="left", padx=(0, 8))
            tk.Label(row, text=title, bg=theme.PANEL_ALT, fg=theme.TEXT,
                     font=fonts.panel_title, anchor="w").pack(side="left")
            self.head_right = tk.Frame(row, bg=theme.PANEL_ALT)
            self.head_right.pack(side="right")
            if hint:
                hint_label = tk.Label(head, text=hint, bg=theme.PANEL_ALT,
                                      fg=theme.MUTED, font=fonts.small,
                                      anchor="w", justify="left", wraplength=280)
                hint_label.pack(fill="x", padx=12, pady=(3, 9))
                autowrap(hint_label, head)
            else:
                tk.Frame(head, bg=theme.PANEL_ALT, height=9).pack(fill="x")
            tk.Frame(head, bg=theme.BORDER, height=1).pack(fill="x")

        self.body = tk.Frame(inner, bg=theme.PANEL)
        self.body.pack(fill="both", expand=True)


class ButtonRow(tk.Frame):
    """A strip of small secondary buttons along the bottom of a panel."""

    def __init__(self, master: tk.Misc, fonts: theme.Fonts,
                 buttons: list[tuple[str, Callable[[], None]]],
                 **kwargs) -> None:
        super().__init__(master, bg=theme.PANEL, **kwargs)
        self.buttons: dict[str, ttk.Button] = {}
        for label, command in buttons:
            button = ttk.Button(self, text=label, style="Ghost.TButton",
                                command=command, takefocus=False)
            button.pack(side="left", padx=(0, 6))
            self.buttons[label] = button


class CheckTree(ttk.Treeview):
    """A Treeview whose items carry a tri-state checkbox in column #0.

    Tk has no checkbox tree, and the usual workaround -- a canvas full of hand
    placed widgets -- loses keyboard navigation, scrolling and column headings.
    Putting the checkbox in the item's image keeps all of that and costs three
    generated images.
    """

    def __init__(self, master: tk.Misc, icons: theme.Icons,
                 on_toggle: Callable[[str], None], **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.icons = icons
        self._on_toggle = on_toggle
        self.bind("<Button-1>", self._clicked, add="+")
        self.bind("<space>", self._space, add="+")
        self.bind("<Return>", self._space, add="+")

    def set_check(self, item: str, state: str) -> None:
        self.item(item, image=self.icons.checkbox(state))

    def _clicked(self, event: tk.Event) -> str | None:
        item = self.identify_row(event.y)
        if not item:
            return None
        element = ""
        try:
            element = self.identify_element(event.x, event.y)
        except tk.TclError:
            element = ""
        if "image" not in str(element):
            return None
        self._on_toggle(item)
        return "break"

    def _space(self, _event: tk.Event) -> str | None:
        item = self.focus()
        if item:
            self._on_toggle(item)
            return "break"
        return None


class StatValue(tk.Frame):
    """A big number with a caption under it."""

    def __init__(self, master: tk.Misc, fonts: theme.Fonts, caption: str,
                 value: str = "-", colour: str = theme.ACCENT, **kwargs) -> None:
        super().__init__(master, bg=theme.PANEL, **kwargs)
        self.value_label = tk.Label(self, text=value, bg=theme.PANEL, fg=colour,
                                    font=fonts.huge, anchor="w")
        self.value_label.pack(fill="x", anchor="w")
        tk.Label(self, text=caption, bg=theme.PANEL, fg=theme.MUTED,
                 font=fonts.small, anchor="w").pack(fill="x", anchor="w")

    def set(self, value: str) -> None:
        self.value_label.configure(text=value)


class Banner(tk.Frame):
    """A tinted strip for a single line of guidance or warning."""

    TONES = {
        "info": (theme.ACCENT_LIGHT, theme.ACCENT_DARK),
        "ok": (theme.OK_LIGHT, theme.OK),
        "warn": (theme.WARN_LIGHT, theme.WARN),
        "danger": (theme.DANGER_LIGHT, theme.DANGER),
    }

    def __init__(self, master: tk.Misc, fonts: theme.Fonts, text: str = "",
                 tone: str = "info", **kwargs) -> None:
        background, foreground = self.TONES[tone]
        super().__init__(master, bg=background, **kwargs)
        self.fonts = fonts
        self.label = tk.Label(self, text=text, bg=background, fg=foreground,
                              font=fonts.small, anchor="w", justify="left",
                              wraplength=260)
        self.label.pack(fill="x", padx=10, pady=7)
        autowrap(self.label, self, pad=22)

    def set(self, text: str, tone: str = "info") -> None:
        background, foreground = self.TONES[tone]
        self.configure(bg=background)
        self.label.configure(text=text, bg=background, fg=foreground)


def scrolled(master: tk.Misc, factory, **kwargs):
    """Wrap a Treeview (or similar) in a frame with a vertical scrollbar."""
    holder = tk.Frame(master, bg=theme.PANEL)
    widget = factory(holder, **kwargs)
    bar = ttk.Scrollbar(holder, orient="vertical", command=widget.yview)
    widget.configure(yscrollcommand=bar.set)
    widget.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y")
    return holder, widget


def separator(master: tk.Misc, pady: tuple[int, int] = (10, 10)) -> tk.Frame:
    line = tk.Frame(master, bg=theme.BORDER, height=1)
    line.pack(fill="x", pady=pady)
    return line


def center_on_screen(window: tk.Misc, width: int, height: int) -> None:
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = max(0, (screen_width - width) // 2)
    y = max(0, (screen_height - height) // 3)
    window.geometry(f"{width}x{height}+{x}+{y}")
