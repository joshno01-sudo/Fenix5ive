"""Tkinter user interface for the printer monitor."""

from __future__ import annotations

__all__ = ["run_gui", "MonitorApp", "AlertPopup"]


def __getattr__(name: str):
    # Imported lazily so the headless CLI never needs a display or tkinter.
    if name in ("run_gui", "MonitorApp"):
        from .app import MonitorApp, run_gui

        return {"run_gui": run_gui, "MonitorApp": MonitorApp}[name]
    if name == "AlertPopup":
        from .popup import AlertPopup

        return AlertPopup
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
