"""Import the GUI modules against a stub tkinter.

The shop PC has tkinter (it ships with Python), but CI containers often don't.
Stubbing it keeps the GUI covered against typos, bad base classes and
module-level mistakes, which is most of what breaks in UI code that is never
imported by the other tests.
"""

from __future__ import annotations

import sys
import types

import pytest


def _stub_tkinter() -> dict[str, types.ModuleType]:
    """Build a tkinter package whose widgets are real (if inert) classes."""

    class _Widget:
        def __init__(self, *args, **kwargs):
            self._kwargs = kwargs

        def __getattr__(self, name):  # any method call is a no-op
            def anything(*_args, **_kwargs):
                return None

            return anything

    class _StringVar(_Widget):
        def __init__(self, *args, value=None, **kwargs):
            super().__init__(*args, **kwargs)
            self._value = value

        def get(self):
            return self._value

        def set(self, value):
            self._value = value

    tkinter = types.ModuleType("tkinter")
    for name in (
        "Tk",
        "Toplevel",
        "Frame",
        "Label",
        "Button",
        "Canvas",
        "Listbox",
        "Text",
        "Misc",
        "Widget",
        "PhotoImage",
        "Menu",
        "Scrollbar",
    ):
        setattr(tkinter, name, type(name, (_Widget,), {}))
    for name in ("StringVar", "IntVar", "DoubleVar", "BooleanVar"):
        setattr(tkinter, name, type(name, (_StringVar,), {}))
    tkinter.TclError = type("TclError", (Exception,), {})

    ttk = types.ModuleType("tkinter.ttk")
    for name in (
        "Frame",
        "Label",
        "Button",
        "Entry",
        "Combobox",
        "Checkbutton",
        "Notebook",
        "Treeview",
        "Scrollbar",
        "Separator",
        "Spinbox",
        "Style",
        "Progressbar",
    ):
        setattr(ttk, name, type(name, (_Widget,), {}))

    messagebox = types.ModuleType("tkinter.messagebox")
    for name in ("showinfo", "showwarning", "showerror", "askyesno"):
        setattr(messagebox, name, lambda *a, **k: None)

    filedialog = types.ModuleType("tkinter.filedialog")
    filedialog.asksaveasfilename = lambda *a, **k: ""
    filedialog.askopenfilename = lambda *a, **k: ""

    simpledialog = types.ModuleType("tkinter.simpledialog")
    simpledialog.Dialog = type("Dialog", (_Widget,), {})
    simpledialog.askstring = lambda *a, **k: None

    tkinter.ttk = ttk
    tkinter.messagebox = messagebox
    tkinter.filedialog = filedialog
    tkinter.simpledialog = simpledialog

    return {
        "tkinter": tkinter,
        "tkinter.ttk": ttk,
        "tkinter.messagebox": messagebox,
        "tkinter.filedialog": filedialog,
        "tkinter.simpledialog": simpledialog,
    }


GUI_MODULES = [
    "printer_monitor.gui.popup",
    "printer_monitor.gui.dashboard",
    "printer_monitor.gui.supplies",
    "printer_monitor.gui.settings",
    "printer_monitor.gui.app",
]


@pytest.fixture
def stub_tkinter(monkeypatch):
    for name, module in _stub_tkinter().items():
        monkeypatch.setitem(sys.modules, name, module)
    # Force a fresh import of the GUI modules under the stub.
    for name in list(sys.modules):
        if name.startswith("printer_monitor.gui"):
            monkeypatch.delitem(sys.modules, name, raising=False)
    yield


@pytest.mark.parametrize("module_name", GUI_MODULES)
def test_gui_module_imports(stub_tkinter, module_name):
    import importlib

    module = importlib.import_module(module_name)
    assert module is not None


def test_expected_classes_exist(stub_tkinter):
    import importlib

    app = importlib.import_module("printer_monitor.gui.app")
    dashboard = importlib.import_module("printer_monitor.gui.dashboard")
    supplies = importlib.import_module("printer_monitor.gui.supplies")
    settings = importlib.import_module("printer_monitor.gui.settings")
    popup = importlib.import_module("printer_monitor.gui.popup")

    assert callable(app.run_gui)
    for attribute in ("MonitorApp", "AlertsTab"):
        assert hasattr(app, attribute)
    for attribute in ("DashboardTab", "PrinterCard", "LevelRow"):
        assert hasattr(dashboard, attribute)
    for attribute in ("SuppliesTab", "ItemRow", "ItemDialog"):
        assert hasattr(supplies, attribute)
    for attribute in ("SettingsTab", "PrintersPage", "ThresholdsPage", "AlertsPage"):
        assert hasattr(settings, attribute)
    assert hasattr(popup, "AlertPopup")


def test_level_colour_thresholds(stub_tkinter):
    import importlib

    dashboard = importlib.import_module("printer_monitor.gui.dashboard")
    colour = dashboard._level_color
    assert colour(None, 20, 8) == dashboard.MUTED
    assert colour(50, 20, 8) == dashboard.OK
    assert colour(20, 20, 8) == dashboard.WARNING
    assert colour(8, 20, 8) == dashboard.CRITICAL
    assert colour(0, 20, 8) == dashboard.CRITICAL


def test_swatch_colours(stub_tkinter):
    import importlib

    from printer_monitor.models import Supply

    dashboard = importlib.import_module("printer_monitor.gui.dashboard")
    cyan = Supply(index=1, description="HP 831 Latex Cyan")
    assert dashboard._swatch_for(cyan) == "#00b7eb"

    waste = Supply(index=2, description="Maintenance Cartridge", class_code=4)
    assert dashboard._swatch_for(waste) == "#8d6e63"


def test_profile_label_maps_are_consistent(stub_tkinter):
    import importlib

    settings = importlib.import_module("printer_monitor.gui.settings")
    assert set(settings.PROFILE_LABELS) == {"hp_latex", "hp_laserjet", "generic"}
    for key, label in settings.PROFILE_LABELS.items():
        assert settings.LABEL_PROFILES[label] == key


def test_gui_is_not_imported_by_the_headless_path():
    """`printer-monitor check` must work on a machine with no tkinter at all."""
    for name in list(sys.modules):
        if name.startswith("printer_monitor"):
            del sys.modules[name]

    import printer_monitor
    from printer_monitor import cli, notify, service

    # Referenced so the imports are plainly deliberate rather than dead.
    assert all(module is not None for module in (printer_monitor, cli, notify, service))
    assert not any(name.startswith("printer_monitor.gui") for name in sys.modules)
    assert "tkinter" not in sys.modules
