"""Settings tab: printers, alert thresholds, popup and email options."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Optional

from ..config import ENV_SMTP_PASSWORD, PrinterConfig, SnmpSettings, slugify
from ..notify import Notifier
from ..poller import probe_printer

PROFILES = [
    ("hp_latex", "HP Latex (wide format)"),
    ("hp_laserjet", "HP LaserJet (office)"),
    ("generic", "Other / generic SNMP printer"),
]
PROFILE_LABELS = {key: label for key, label in PROFILES}
LABEL_PROFILES = {label: key for key, label in PROFILES}


class SettingsTab(ttk.Frame):
    def __init__(self, parent: tk.Misc, app):
        super().__init__(parent, padding=0)
        self.app = app

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.printers_page = PrintersPage(notebook, app)
        self.thresholds_page = ThresholdsPage(notebook, app)
        self.alerts_page = AlertsPage(notebook, app)

        notebook.add(self.printers_page, text="Printers")
        notebook.add(self.thresholds_page, text="Alert levels")
        notebook.add(self.alerts_page, text="Popup & email")

        footer = ttk.Frame(self, padding=(12, 0, 12, 12))
        footer.pack(fill="x")
        ttk.Button(footer, text="Save settings", command=self.save).pack(side="right")
        self.status = ttk.Label(footer, text="", foreground="#2e7d32")
        self.status.pack(side="right", padx=(0, 12))

    def refresh(self) -> None:
        self.printers_page.refresh()
        self.thresholds_page.refresh()
        self.alerts_page.refresh()

    def save(self) -> None:
        for page in (self.printers_page, self.thresholds_page, self.alerts_page):
            error = page.apply()
            if error:
                messagebox.showwarning("Settings", error, parent=self)
                return
        path = self.app.save_config()
        self.status.configure(text=f"Saved to {path}")
        self.after(4000, lambda: self.status.configure(text=""))
        self.app.on_config_changed()


# ---------------------------------------------------------------------------
# Printers
# ---------------------------------------------------------------------------


class PrintersPage(ttk.Frame):
    def __init__(self, parent: tk.Misc, app):
        super().__init__(parent, padding=12)
        self.app = app

        left = ttk.Frame(self)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Printers", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.listbox = tk.Listbox(left, width=28, height=12, exportselection=False)
        self.listbox.pack(pady=(6, 6), fill="y", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        buttons = ttk.Frame(left)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Add", width=7, command=self.add_printer).pack(side="left")
        ttk.Button(buttons, text="Remove", width=8, command=self.remove_printer).pack(
            side="left", padx=4
        )

        right = ttk.Frame(self, padding=(16, 0, 0, 0))
        right.pack(side="left", fill="both", expand=True)

        self.name_var = tk.StringVar()
        self.host_var = tk.StringVar()
        self.profile_var = tk.StringVar(value=PROFILE_LABELS["generic"])
        self.enabled_var = tk.BooleanVar(value=True)
        self.community_var = tk.StringVar(value="public")
        self.version_var = tk.StringVar(value="2c")
        self.port_var = tk.StringVar(value="161")
        self.timeout_var = tk.StringVar(value="3.0")
        self.retries_var = tk.StringVar(value="2")
        self.notes_var = tk.StringVar()

        fields = [
            ("Name", ttk.Entry(right, textvariable=self.name_var, width=36)),
            ("IP address / hostname", ttk.Entry(right, textvariable=self.host_var, width=36)),
            (
                "Type",
                ttk.Combobox(
                    right,
                    textvariable=self.profile_var,
                    values=[label for _, label in PROFILES],
                    state="readonly",
                    width=34,
                ),
            ),
            ("SNMP community", ttk.Entry(right, textvariable=self.community_var, width=20)),
            (
                "SNMP version",
                ttk.Combobox(
                    right,
                    textvariable=self.version_var,
                    values=["2c", "1"],
                    state="readonly",
                    width=8,
                ),
            ),
            ("SNMP port", ttk.Entry(right, textvariable=self.port_var, width=8)),
            ("Timeout (seconds)", ttk.Entry(right, textvariable=self.timeout_var, width=8)),
            ("Retries", ttk.Entry(right, textvariable=self.retries_var, width=8)),
            ("Notes", ttk.Entry(right, textvariable=self.notes_var, width=36)),
        ]
        for row, (label, widget) in enumerate(fields):
            ttk.Label(right, text=label).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 10))
            widget.grid(row=row, column=1, sticky="w", pady=4)

        row = len(fields)
        ttk.Checkbutton(right, text="Monitor this printer", variable=self.enabled_var).grid(
            row=row, column=1, sticky="w", pady=(6, 0)
        )
        ttk.Button(right, text="Test connection", command=self.test_connection).grid(
            row=row + 1, column=1, sticky="w", pady=(12, 0)
        )
        self.test_status = ttk.Label(right, text="", wraplength=340, foreground="#555")
        self.test_status.grid(row=row + 2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        ttk.Label(
            right,
            text=(
                "SNMP must be enabled on the printer. On both HP models it lives in the\n"
                "built-in web page (browse to the printer's IP) under Networking →\n"
                "SNMP. Read-only access with the community string is all this needs."
            ),
            foreground="#666",
            font=("Segoe UI", 8),
            justify="left",
        ).grid(row=row + 3, column=0, columnspan=2, sticky="w", pady=(14, 0))

        self._current: Optional[PrinterConfig] = None
        self.refresh()

    def refresh(self) -> None:
        selection = self.listbox.curselection()
        self.listbox.delete(0, "end")
        for printer in self.app.config.printers:
            marker = "" if printer.enabled else "  (off)"
            host = printer.host or "no IP set"
            self.listbox.insert("end", f"{printer.name} — {host}{marker}")
        if self.app.config.printers:
            index = selection[0] if selection and selection[0] < len(self.app.config.printers) else 0
            self.listbox.selection_set(index)
            self._load(self.app.config.printers[index])

    def _on_select(self, _event=None) -> None:
        # Keep edits to the printer we're leaving.
        if self._current is not None:
            self._store(self._current)
        selection = self.listbox.curselection()
        if selection:
            self._load(self.app.config.printers[selection[0]])

    def _load(self, printer: PrinterConfig) -> None:
        self._current = printer
        self.name_var.set(printer.name)
        self.host_var.set(printer.host)
        self.profile_var.set(PROFILE_LABELS.get(printer.profile, PROFILE_LABELS["generic"]))
        self.enabled_var.set(printer.enabled)
        self.community_var.set(printer.snmp.community)
        self.version_var.set(printer.snmp.version)
        self.port_var.set(str(printer.snmp.port))
        self.timeout_var.set(str(printer.snmp.timeout))
        self.retries_var.set(str(printer.snmp.retries))
        self.notes_var.set(printer.notes)
        self.test_status.configure(text="")

    def _store(self, printer: PrinterConfig) -> Optional[str]:
        name = self.name_var.get().strip()
        if not name:
            return "Every printer needs a name."
        printer.name = name
        printer.host = self.host_var.get().strip()
        printer.profile = LABEL_PROFILES.get(self.profile_var.get(), "generic")
        printer.enabled = self.enabled_var.get()
        printer.notes = self.notes_var.get().strip()
        printer.snmp.community = self.community_var.get().strip() or "public"
        printer.snmp.version = self.version_var.get()
        try:
            printer.snmp.port = int(self.port_var.get())
            printer.snmp.timeout = float(self.timeout_var.get())
            printer.snmp.retries = int(self.retries_var.get())
        except ValueError:
            return "SNMP port, timeout and retries must be numbers."
        if not 1 <= printer.snmp.port <= 65535:
            return "SNMP port must be between 1 and 65535."
        return None

    def apply(self) -> Optional[str]:
        if self._current is not None:
            error = self._store(self._current)
            if error:
                return error
        ids = [p.id for p in self.app.config.printers]
        if len(ids) != len(set(ids)):
            return "Two printers ended up with the same ID — rename one of them."
        self.refresh()
        return None

    def add_printer(self) -> None:
        name = simpledialog.askstring("Add printer", "Printer name:", parent=self)
        if not name:
            return
        printer_id = slugify(name)
        existing = {p.id for p in self.app.config.printers}
        suffix = 2
        while printer_id in existing:
            printer_id = f"{slugify(name)}-{suffix}"
            suffix += 1
        self.app.config.printers.append(
            PrinterConfig(id=printer_id, name=name, host="", profile="generic", snmp=SnmpSettings())
        )
        self._current = None
        self.refresh()
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set("end")
        self._on_select()

    def remove_printer(self) -> None:
        selection = self.listbox.curselection()
        if not selection:
            return
        printer = self.app.config.printers[selection[0]]
        if not messagebox.askyesno(
            "Remove printer",
            f"Stop monitoring “{printer.name}”?\n\n"
            "Its supply-list items and history stay in the database.",
            parent=self,
        ):
            return
        self.app.config.printers.remove(printer)
        self._current = None
        self.refresh()

    def test_connection(self) -> None:
        if self._current is None:
            return
        error = self._store(self._current)
        if error:
            messagebox.showwarning("Test connection", error, parent=self)
            return
        printer = self._current
        if not printer.host:
            self.test_status.configure(text="Set the IP address first.", foreground="#c62828")
            return

        self.test_status.configure(text=f"Contacting {printer.host}…", foreground="#555")

        def worker() -> None:
            result = probe_printer(printer)
            self.after(0, lambda: self._show_test_result(printer, result))

        threading.Thread(target=worker, daemon=True).start()

    def _show_test_result(self, printer: PrinterConfig, result: dict) -> None:
        ok = bool(result.get("ok"))
        message = str(result.get("message", ""))
        detected = result.get("version")
        if ok and detected and detected != printer.snmp.version:
            printer.snmp.version = str(detected)
            self.version_var.set(str(detected))
            message += f"\nSwitched this printer to SNMPv{detected} — remember to Save."
        self.test_status.configure(text=message, foreground="#2e7d32" if ok else "#c62828")
        reading = result.get("reading")
        if ok and reading is not None:
            self.app.apply_readings([reading])


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------


class ThresholdsPage(ttk.Frame):
    def __init__(self, parent: tk.Misc, app):
        super().__init__(parent, padding=12)
        self.app = app

        ttk.Label(
            self,
            text="Alert when a supply drops to these levels",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w")

        self.supply_warning = tk.IntVar()
        self.supply_critical = tk.IntVar()
        self.tray_warning = tk.IntVar()
        self.interval = tk.IntVar()
        self.repeat_hours = tk.DoubleVar()
        self.history_days = tk.IntVar()

        rows = [
            ("Low warning", self.supply_warning, "% remaining — first alert"),
            ("Critical", self.supply_critical, "% remaining — urgent alert"),
            ("Paper / media", self.tray_warning, "% remaining in a tray or roll"),
        ]
        for index, (label, var, hint) in enumerate(rows, start=1):
            ttk.Label(self, text=label).grid(row=index, column=0, sticky="w", pady=6, padx=(0, 10))
            spin = ttk.Spinbox(self, from_=0, to=100, textvariable=var, width=6)
            spin.grid(row=index, column=1, sticky="w")
            ttk.Label(self, text=hint, foreground="#666").grid(row=index, column=2, sticky="w", padx=8)

        ttk.Separator(self, orient="horizontal").grid(
            row=4, column=0, columnspan=3, sticky="ew", pady=14
        )
        ttk.Label(self, text="Timing", font=("Segoe UI", 10, "bold")).grid(
            row=5, column=0, columnspan=3, sticky="w"
        )

        timing = [
            ("Check every", self.interval, "seconds (300 = 5 minutes)", 30, 86400),
            ("Repeat alerts after", self.repeat_hours, "hours, if still low", 0, 720),
            ("Keep history for", self.history_days, "days", 1, 3650),
        ]
        for index, (label, var, hint, low, high) in enumerate(timing, start=6):
            ttk.Label(self, text=label).grid(row=index, column=0, sticky="w", pady=6, padx=(0, 10))
            ttk.Spinbox(self, from_=low, to=high, textvariable=var, width=8).grid(
                row=index, column=1, sticky="w"
            )
            ttk.Label(self, text=hint, foreground="#666").grid(row=index, column=2, sticky="w", padx=8)

        ttk.Separator(self, orient="horizontal").grid(
            row=9, column=0, columnspan=3, sticky="ew", pady=14
        )
        ttk.Label(
            self, text="Per-supply overrides", font=("Segoe UI", 10, "bold")
        ).grid(row=10, column=0, columnspan=3, sticky="w")
        ttk.Label(
            self,
            text=(
                "Use these when one cartridge deserves a different trip point — e.g. a\n"
                "colour you burn through on big wraps, or the maintenance cartridge."
            ),
            foreground="#666",
            font=("Segoe UI", 8),
            justify="left",
        ).grid(row=11, column=0, columnspan=3, sticky="w", pady=(2, 8))

        self.override_list = tk.Listbox(self, width=64, height=6, exportselection=False)
        self.override_list.grid(row=12, column=0, columnspan=3, sticky="w")

        override_buttons = ttk.Frame(self)
        override_buttons.grid(row=13, column=0, columnspan=3, sticky="w", pady=6)
        ttk.Button(override_buttons, text="Add / edit", command=self.add_override).pack(side="left")
        ttk.Button(override_buttons, text="Remove", command=self.remove_override).pack(
            side="left", padx=6
        )

        self.refresh()

    def refresh(self) -> None:
        config = self.app.config
        self.supply_warning.set(config.thresholds.supply_warning)
        self.supply_critical.set(config.thresholds.supply_critical)
        self.tray_warning.set(config.thresholds.tray_warning)
        self.interval.set(config.poll_interval_seconds)
        self.repeat_hours.set(config.alerts.repeat_hours)
        self.history_days.set(config.history_days)
        self._refresh_overrides()

    def _refresh_overrides(self) -> None:
        self.override_list.delete(0, "end")
        self._override_keys = sorted(self.app.config.thresholds.per_supply)
        for key in self._override_keys:
            values = self.app.config.thresholds.per_supply[key]
            self.override_list.insert(
                "end",
                f"{key}   →   warn {values.get('warning')}%, critical {values.get('critical')}%",
            )

    def apply(self) -> Optional[str]:
        config = self.app.config
        try:
            # A blanked-out spinbox raises TclError rather than returning 0.
            warning = int(self.supply_warning.get())
            critical = int(self.supply_critical.get())
            tray = int(self.tray_warning.get())
            interval = int(self.interval.get())
            repeat = float(self.repeat_hours.get())
            history = int(self.history_days.get())
        except (tk.TclError, ValueError):
            return "Every box on this page needs a number in it."

        if not 0 <= critical <= warning <= 100:
            return (
                "Alert levels must satisfy 0 ≤ critical ≤ low warning ≤ 100 "
                f"(got critical {critical}%, warning {warning}%)."
            )
        config.thresholds.supply_warning = warning
        config.thresholds.supply_critical = critical
        config.thresholds.tray_warning = max(0, min(100, tray))
        config.poll_interval_seconds = max(30, interval)
        config.alerts.repeat_hours = max(0.0, repeat)
        config.history_days = max(1, history)
        return None

    def add_override(self) -> None:
        dialog = OverrideDialog(self, self.app)
        if dialog.result:
            printer_id, supply_key, warning, critical = dialog.result
            self.app.config.thresholds.set_supply_override(
                printer_id, supply_key, warning, critical
            )
            self._refresh_overrides()

    def remove_override(self) -> None:
        selection = self.override_list.curselection()
        if not selection:
            return
        key = self._override_keys[selection[0]]
        self.app.config.thresholds.per_supply.pop(key, None)
        self._refresh_overrides()


class OverrideDialog(simpledialog.Dialog):
    """Pick a discovered supply and give it its own thresholds."""

    def __init__(self, parent: tk.Misc, app):
        self.app = app
        self.result: Optional[tuple[str, str, int, int]] = None
        super().__init__(parent, title="Per-supply alert level")

    def body(self, master):  # noqa: D102 - tkinter API
        master.configure(padx=12, pady=8)

        # Offer whatever the last poll discovered; fall back to free text.
        self._choices: list[tuple[str, str, str]] = []
        for reading in self.app.last_readings:
            for supply in reading.supplies:
                self._choices.append(
                    (
                        f"{reading.printer_name} — {supply.display_name}",
                        reading.printer_id,
                        supply.key,
                    )
                )

        ttk.Label(master, text="Supply").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        self.supply_var = tk.StringVar()
        if self._choices:
            self.supply_combo = ttk.Combobox(
                master,
                textvariable=self.supply_var,
                values=[label for label, _, _ in self._choices],
                state="readonly",
                width=44,
            )
            self.supply_combo.current(0)
        else:
            self.supply_combo = ttk.Entry(master, textvariable=self.supply_var, width=46)
        self.supply_combo.grid(row=0, column=1, sticky="w", pady=4)

        self.warning_var = tk.IntVar(value=self.app.config.thresholds.supply_warning)
        self.critical_var = tk.IntVar(value=self.app.config.thresholds.supply_critical)
        ttk.Label(master, text="Low warning %").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Spinbox(master, from_=0, to=100, textvariable=self.warning_var, width=6).grid(
            row=1, column=1, sticky="w", pady=4
        )
        ttk.Label(master, text="Critical %").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Spinbox(master, from_=0, to=100, textvariable=self.critical_var, width=6).grid(
            row=2, column=1, sticky="w", pady=4
        )

        if not self._choices:
            ttk.Label(
                master,
                text=(
                    "No supplies discovered yet — poll a printer first, or type the\n"
                    "supply key manually as printer-id:supply-key."
                ),
                foreground="#666",
                font=("Segoe UI", 8),
                justify="left",
            ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        return None

    def validate(self) -> bool:  # noqa: D102 - tkinter API
        if not self.supply_var.get().strip():
            return False
        if self.critical_var.get() > self.warning_var.get():
            messagebox.showwarning(
                "Alert levels",
                "The critical level must be at or below the low-warning level.",
                parent=self,
            )
            return False
        return True

    def apply(self) -> None:  # noqa: D102 - tkinter API
        chosen = self.supply_var.get().strip()
        printer_id, supply_key = "", chosen
        for label, pid, key in self._choices:
            if label == chosen:
                printer_id, supply_key = pid, key
                break
        else:
            if ":" in chosen:
                printer_id, supply_key = chosen.split(":", 1)
        self.result = (printer_id, supply_key, self.warning_var.get(), self.critical_var.get())


# ---------------------------------------------------------------------------
# Popup & email
# ---------------------------------------------------------------------------


class AlertsPage(ttk.Frame):
    def __init__(self, parent: tk.Misc, app):
        super().__init__(parent, padding=12)
        self.app = app

        self.popup_var = tk.BooleanVar()
        self.email_var = tk.BooleanVar()
        self.inventory_var = tk.BooleanVar()
        self.offline_var = tk.BooleanVar()
        self.printer_error_var = tk.BooleanVar()

        ttk.Label(self, text="How to notify", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        checks = [
            ("Show a popup on this computer", self.popup_var),
            ("Send an email", self.email_var),
            ("Also alert when shelf stock hits its reorder point", self.inventory_var),
            ("Also alert when a printer stops responding", self.offline_var),
            ("Also forward the printer's own errors (jams, doors, service)", self.printer_error_var),
        ]
        for index, (label, var) in enumerate(checks, start=1):
            ttk.Checkbutton(self, text=label, variable=var).grid(
                row=index, column=0, columnspan=2, sticky="w", pady=2
            )

        ttk.Separator(self, orient="horizontal").grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=14
        )
        ttk.Label(self, text="Email server (SMTP)", font=("Segoe UI", 10, "bold")).grid(
            row=7, column=0, columnspan=2, sticky="w"
        )

        self.host_var = tk.StringVar()
        self.port_var = tk.StringVar()
        self.encryption_var = tk.StringVar()
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.from_var = tk.StringVar()
        self.to_var = tk.StringVar()
        self.prefix_var = tk.StringVar()

        fields = [
            ("SMTP server", ttk.Entry(self, textvariable=self.host_var, width=34)),
            ("Port", ttk.Entry(self, textvariable=self.port_var, width=8)),
            (
                "Encryption",
                ttk.Combobox(
                    self,
                    textvariable=self.encryption_var,
                    values=["starttls", "ssl", "none"],
                    state="readonly",
                    width=10,
                ),
            ),
            ("Username", ttk.Entry(self, textvariable=self.username_var, width=34)),
            ("Password", ttk.Entry(self, textvariable=self.password_var, width=34, show="•")),
            ("From address", ttk.Entry(self, textvariable=self.from_var, width=34)),
            ("Send alerts to", ttk.Entry(self, textvariable=self.to_var, width=46)),
            ("Subject prefix", ttk.Entry(self, textvariable=self.prefix_var, width=24)),
        ]
        for index, (label, widget) in enumerate(fields, start=8):
            ttk.Label(self, text=label).grid(row=index, column=0, sticky="w", pady=4, padx=(0, 10))
            widget.grid(row=index, column=1, sticky="w", pady=4)

        row = 8 + len(fields)
        ttk.Label(
            self,
            text="Separate multiple recipients with commas.",
            foreground="#666",
            font=("Segoe UI", 8),
        ).grid(row=row, column=1, sticky="w")

        ttk.Button(self, text="Send test email", command=self.send_test).grid(
            row=row + 1, column=1, sticky="w", pady=(12, 0)
        )
        self.test_status = ttk.Label(self, text="", wraplength=420, foreground="#555")
        self.test_status.grid(row=row + 2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        ttk.Label(
            self,
            text=(
                "The password is stored in the config file with owner-only permissions.\n"
                f"To keep it off disk entirely, leave the box empty and set the {ENV_SMTP_PASSWORD}\n"
                "environment variable instead. For Gmail/Microsoft 365 accounts with 2-factor\n"
                "authentication, use an app password rather than the account password."
            ),
            foreground="#666",
            font=("Segoe UI", 8),
            justify="left",
        ).grid(row=row + 3, column=0, columnspan=2, sticky="w", pady=(14, 0))

        self.refresh()

    def refresh(self) -> None:
        config = self.app.config
        self.popup_var.set(config.alerts.popup_enabled)
        self.email_var.set(config.alerts.email_enabled)
        self.inventory_var.set(config.alerts.inventory_alerts)
        self.offline_var.set(config.alerts.offline_alerts)
        self.printer_error_var.set(config.alerts.printer_error_alerts)

        email = config.email
        self.host_var.set(email.smtp_host)
        self.port_var.set(str(email.smtp_port))
        self.encryption_var.set(email.encryption)
        self.username_var.set(email.username)
        self.password_var.set(email.password)
        self.from_var.set(email.from_addr)
        self.to_var.set(", ".join(email.to_addrs))
        self.prefix_var.set(email.subject_prefix)

    def apply(self) -> Optional[str]:
        config = self.app.config
        config.alerts.popup_enabled = self.popup_var.get()
        config.alerts.email_enabled = self.email_var.get()
        config.alerts.inventory_alerts = self.inventory_var.get()
        config.alerts.offline_alerts = self.offline_var.get()
        config.alerts.printer_error_alerts = self.printer_error_var.get()

        email = config.email
        email.smtp_host = self.host_var.get().strip()
        try:
            email.smtp_port = int(self.port_var.get())
        except ValueError:
            return "The SMTP port must be a number (usually 587, or 465 for SSL)."
        email.encryption = self.encryption_var.get()
        email.username = self.username_var.get().strip()
        email.password = self.password_var.get()
        email.from_addr = self.from_var.get().strip()
        email.to_addrs = [a.strip() for a in self.to_var.get().split(",") if a.strip()]
        email.subject_prefix = self.prefix_var.get().strip()

        if config.alerts.email_enabled and not email.is_configured():
            return (
                "Email alerts are switched on, but the SMTP server, From address or "
                "recipient list is incomplete."
            )
        return None

    def send_test(self) -> None:
        error = self.apply()
        if error:
            messagebox.showwarning("Email settings", error, parent=self)
            return
        if not self.app.config.email.is_configured():
            self.test_status.configure(
                text="Fill in the SMTP server, From address and at least one recipient first.",
                foreground="#c62828",
            )
            return

        self.test_status.configure(text="Sending…", foreground="#555")
        settings = self.app.config.email

        def worker() -> None:
            try:
                Notifier(settings, popup_enabled=False, email_enabled=True).send_test_email()
                message, color = (
                    f"Test email sent to {', '.join(settings.to_addrs)}.",
                    "#2e7d32",
                )
            except Exception as exc:  # noqa: BLE001 - surface whatever SMTP said
                message, color = f"Failed: {exc}", "#c62828"
            self.after(0, lambda: self.test_status.configure(text=message, foreground=color))

        threading.Thread(target=worker, daemon=True).start()
