"""The main window: dashboard, supply list, alert history, settings.

``MonitorApp`` deliberately owns a ``tk.Tk`` root rather than subclassing it —
the tabs reach for ``app.config``, and ``Tk.config()`` is an existing method
that must not be shadowed.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional, Sequence

from ..config import AppConfig, default_db_path
from ..models import AlertEvent, PrinterReading
from ..notify import Notifier
from ..service import MonitorService
from ..single_instance import AlreadyRunning, SingleInstance
from ..storage import Storage
from .dashboard import DashboardTab
from .popup import AlertPopup
from .settings import SettingsTab
from .supplies import SuppliesTab

log = logging.getLogger(__name__)


class MonitorApp:
    def __init__(
        self,
        config: AppConfig,
        storage: Optional[Storage] = None,
        minimized: bool = False,
    ):
        self.config = config
        self.storage = storage or Storage(default_db_path())
        self.last_readings: list[PrinterReading] = []

        # Worker threads hand work back to the Tk thread through these.
        self._reading_queue: "queue.Queue[list[PrinterReading]]" = queue.Queue()
        self._alert_queue: "queue.Queue[list[AlertEvent]]" = queue.Queue()

        self.root = tk.Tk()
        self.root.title("Printer Supply Monitor")
        self.root.geometry("1080x740")
        self.root.minsize(900, 600)
        self._set_icon()

        self.notifier = Notifier(
            config.email,
            popup_enabled=config.alerts.popup_enabled,
            email_enabled=config.alerts.email_enabled,
            popup_hook=self._popup_shown_by_ui,
        )
        self.service = MonitorService(
            config,
            self.storage,
            notifier=self.notifier,
            on_readings=self._reading_queue.put,
            on_alerts=self._alert_queue.put,
        )

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(200, self._drain_queues)

        if config.enabled_printers():
            self.service.start()
            self.set_status("Monitoring started — polling now…")
            if minimized:
                # Started with Windows: monitor quietly rather than throwing a
                # window at whoever just logged in. Alert popups still appear.
                self.root.iconify()
        else:
            self.set_status("No printer IPs configured yet — open Settings → Printers.")
            self.notebook.select(self.settings_index)

    def mainloop(self) -> None:
        self.root.mainloop()

    # -- UI ---------------------------------------------------------------

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        for theme in ("vista", "clam", "default"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break

        toolbar = ttk.Frame(self.root, padding=(12, 10, 12, 6))
        toolbar.pack(fill="x")

        ttk.Label(
            toolbar, text="Printer Supply Monitor", font=("Segoe UI", 14, "bold")
        ).pack(side="left")

        self.refresh_button = ttk.Button(toolbar, text="Refresh now", command=self.refresh_now)
        self.refresh_button.pack(side="right")

        self.pause_button = ttk.Button(toolbar, text="Pause", command=self.toggle_monitoring)
        self.pause_button.pack(side="right", padx=(0, 8))

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)

        self.dashboard = DashboardTab(self.notebook, self)
        self.supplies = SuppliesTab(self.notebook, self)
        self.alerts = AlertsTab(self.notebook, self)
        self.settings = SettingsTab(self.notebook, self)

        self.notebook.add(self.dashboard, text="  Printer levels  ")
        self.notebook.add(self.supplies, text="  Supply list  ")
        self.notebook.add(self.alerts, text="  Alert history  ")
        self.notebook.add(self.settings, text="  Settings  ")
        self.settings_index = 3
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        status_bar = ttk.Frame(self.root, padding=(12, 6))
        status_bar.pack(fill="x")
        self.status_label = ttk.Label(status_bar, text="Starting…", foreground="#555")
        self.status_label.pack(side="left")
        self.alert_badge = ttk.Label(status_bar, text="", foreground="#c62828")
        self.alert_badge.pack(side="right")
        self.refresh_alert_badge()

    def _set_icon(self) -> None:
        # Reuse the site's favicon when the tool sits inside the repo. Searched
        # upward rather than by a fixed depth, so moving the folder can't break it.
        for parent in Path(__file__).resolve().parents:
            candidate = parent / "assets" / "img" / "favicon.png"
            if candidate.exists():
                try:
                    self._icon = tk.PhotoImage(file=str(candidate))
                    self.root.iconphoto(True, self._icon)
                except tk.TclError:
                    pass
                return

    def _on_tab_changed(self, _event=None) -> None:
        current = self.notebook.index(self.notebook.select())
        if current == 1:
            self.supplies.refresh()
        elif current == 2:
            self.alerts.refresh()
        elif current == self.settings_index:
            self.settings.refresh()

    def set_status(self, text: str) -> None:
        self.status_label.configure(text=text)

    def refresh_alert_badge(self) -> None:
        try:
            reorder = len(self.storage.items_needing_reorder())
        except Exception:  # noqa: BLE001
            reorder = 0
        self.alert_badge.configure(text=f"{reorder} item(s) to reorder" if reorder else "")

    # -- monitoring --------------------------------------------------------

    def refresh_now(self) -> None:
        if not self.config.enabled_printers():
            messagebox.showinfo(
                "Refresh",
                "No printers are set up yet. Add an IP address in Settings → Printers.",
                parent=self.root,
            )
            return
        self.set_status("Polling printers…")
        if self.service.running:
            self.service.poll_now()
        else:
            threading.Thread(target=self.service.poll_once, daemon=True).start()

    def toggle_monitoring(self) -> None:
        if self.service.running:
            self.service.stop()
            self.pause_button.configure(text="Resume")
            self.set_status("Monitoring paused.")
        else:
            self.service.start()
            self.pause_button.configure(text="Pause")
            self.set_status("Monitoring resumed.")

    def _popup_shown_by_ui(self, _events: Sequence[AlertEvent]) -> bool:
        """Notifier popup hook, called from the poll thread.

        The window is opened by ``_show_alerts`` off the ``on_alerts`` callback,
        which already delivers the same batch on the Tk thread. This only tells
        the notifier the popup channel is handled — queueing here as well would
        open two identical popups per alert.
        """
        return True

    def _drain_queues(self) -> None:
        try:
            while True:
                self.apply_readings(self._reading_queue.get_nowait())
        except queue.Empty:
            pass

        try:
            while True:
                self._show_alerts(self._alert_queue.get_nowait())
        except queue.Empty:
            pass

        self.root.after(400, self._drain_queues)

    def apply_readings(self, readings: list[PrinterReading]) -> None:
        """Update the dashboard. Must run on the Tk thread."""
        merged = {r.printer_id: r for r in self.last_readings}
        for reading in readings:
            merged[reading.printer_id] = reading
        order = [p.id for p in self.config.printers]
        self.last_readings = sorted(
            merged.values(),
            key=lambda r: order.index(r.printer_id) if r.printer_id in order else 99,
        )
        self.dashboard.update_readings(self.last_readings)
        self.refresh_alert_badge()

        online = sum(1 for r in self.last_readings if r.online)
        offline = len(self.last_readings) - online
        status = f"Last checked {time.strftime('%I:%M:%S %p')} — {online} printer(s) online"
        if offline:
            status += f", {offline} offline"
        if self.service.last_error:
            status += f"  ·  {self.service.last_error}"
        self.set_status(status)

    def _show_alerts(self, events: list[AlertEvent]) -> None:
        self.alerts.refresh()
        self.refresh_alert_badge()
        if not events or not self.config.alerts.popup_enabled:
            return
        try:
            AlertPopup(self.root, events)
        except Exception:  # noqa: BLE001 - never let a popup take the app down
            log.exception("failed to show alert popup")

    # -- config ------------------------------------------------------------

    def save_config(self) -> Path:
        return self.config.save()

    def on_config_changed(self) -> None:
        """Called after Settings saves: pick up the new values immediately."""
        self.notifier.popup_enabled = self.config.alerts.popup_enabled
        self.notifier.email_enabled = self.config.alerts.email_enabled
        self.notifier.email.settings = self.config.email
        if self.config.enabled_printers():
            if self.service.running:
                self.service.poll_now()
            else:
                self.service.start()
                self.pause_button.configure(text="Pause")
        self.supplies.refresh()

    # -- shutdown ----------------------------------------------------------

    def on_close(self) -> None:
        self.service.stop()
        try:
            self.storage.close()
        except Exception:  # noqa: BLE001
            pass
        self.root.destroy()


class AlertsTab(ttk.Frame):
    """Log of everything that has been alerted on."""

    def __init__(self, parent: tk.Misc, app: MonitorApp):
        super().__init__(parent, padding=12)
        self.app = app

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Button(toolbar, text="Mark all read", command=self.acknowledge).pack(
            side="left", padx=6
        )
        self.count_label = ttk.Label(toolbar, text="", foreground="#555")
        self.count_label.pack(side="right")

        columns = ("when", "severity", "printer", "item", "level", "message")
        headings = {
            "when": ("When", 140),
            "severity": ("Severity", 80),
            "printer": ("Printer", 130),
            "item": ("Item", 190),
            "level": ("Level", 60),
            "message": ("Details", 420),
        }
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=20)
        for column in columns:
            title, width = headings[column]
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, anchor="w")

        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.tree.tag_configure("critical", foreground="#c62828")
        self.tree.tag_configure("warning", foreground="#ef6c00")

        self.refresh()

    def refresh(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)
        rows = self.app.storage.recent_alerts(limit=300)
        for row in rows:
            when = time.strftime("%d %b %I:%M %p", time.localtime(row["created_at"]))
            percent = row["level_percent"]
            if percent is None:
                level = "—"
            elif row["kind"] in ("supply", "tray"):
                level = f"{percent:.0f}%"
            else:
                level = f"{percent:.0f}"
            self.tree.insert(
                "",
                "end",
                values=(
                    when,
                    row["severity"].upper(),
                    row["printer_name"] or row["printer_id"],
                    row["subject_name"],
                    level,
                    row["message"],
                ),
                tags=(row["severity"],),
            )
        self.count_label.configure(text=f"{len(rows)} alert(s) logged")

    def acknowledge(self) -> None:
        self.app.storage.acknowledge_alerts()
        self.app.refresh_alert_badge()
        self.refresh()


def run_gui(
    config: Optional[AppConfig] = None,
    db_path: Optional[Path] = None,
    minimized: bool = False,
) -> int:
    """Open the window. Returns 2 if another copy already holds the lock."""
    config = config or AppConfig.load()

    lock = SingleInstance()
    try:
        lock.acquire()
    except AlreadyRunning:
        _warn_already_running()
        return 2

    try:
        storage = Storage(db_path) if db_path else None
        MonitorApp(config, storage=storage, minimized=minimized).mainloop()
    finally:
        lock.release()
    return 0


# How long the "already running" notice stays up before closing itself.
ALREADY_RUNNING_NOTICE_SECONDS = 8


def _warn_already_running() -> None:
    """Say so in a window, since a windowed build has nowhere to print.

    Closes itself after a few seconds rather than using a modal message box.
    The startup shortcut can fire while somebody already has the monitor open,
    and a dialog nobody is there to dismiss would sit on the desktop for the
    rest of the day.
    """
    log.info("another copy is already running; not starting a second one")
    try:
        root = tk.Tk()
        root.title("Printer Supply Monitor")
        root.resizable(False, False)
        root.attributes("-topmost", True)

        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text="The monitor is already running.",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            frame,
            text=(
                "Look for its window on the taskbar — it may have started\n"
                "minimised with Windows."
            ),
            justify="left",
        ).pack(anchor="w", pady=(6, 14))
        ttk.Button(frame, text="OK", command=root.destroy).pack(anchor="e")

        root.after(ALREADY_RUNNING_NOTICE_SECONDS * 1000, root.destroy)
        root.mainloop()
    except Exception:  # noqa: BLE001 - no display: the log line above will do
        log.debug("could not show the already-running notice", exc_info=True)
