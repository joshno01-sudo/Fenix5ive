"""The restore window.

This is the half of the program that runs on the *other* computer, usually off
a USB drive, often by someone who has never seen the program before. So it
shows what it found, states exactly where each group of files is going, and
writes nothing until the button is pressed.
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .. import catalog
from ..platformutil import human_bytes, user_profile_dir
from ..restore import (CONFLICT_KEEP_BOTH, CONFLICT_OVERWRITE, CONFLICT_SKIP,
                       RestoreOptions, RestorePlan, RestoreProgress,
                       RestoreResult, read_plan, run_restore, suggest_drive_map,
                       suggest_profile_remap)
from ..version import APP_NAME
from . import theme, widgets
from .widgets import Banner, Card


class RestoreWindow:
    def __init__(self, parent: tk.Misc, fonts: theme.Fonts, icons: theme.Icons,
                 backup_dir: str) -> None:
        self.parent = parent
        self.fonts = fonts
        self.icons = icons
        self.backup_dir = backup_dir

        self.plan: RestorePlan | None = None
        self.bucket_vars: dict[str, tk.StringVar] = {}
        self.events: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.profile_from = ""
        self.profile_to = ""

        self.window = tk.Toplevel(parent)
        self._build()
        self.window.after(80, self._pump)
        self._start_reading()

    # ------------------------------------------------------------------

    def _build(self) -> None:
        window = self.window
        window.title(f"{APP_NAME} - put your files back")
        window.configure(bg=theme.BG)
        widgets.center_on_screen(window, 940, 760)
        window.transient(self.parent)
        window.protocol("WM_DELETE_WINDOW", self._on_close)

        header = tk.Frame(window, bg=theme.HEADER_BG)
        header.pack(fill="x")
        tk.Label(header, text="Put your files back", bg=theme.HEADER_BG,
                 fg="#ffffff", font=self.fonts.title).pack(anchor="w", padx=20,
                                                           pady=(16, 2))
        self.source_label = tk.Label(header, text="Reading the file list...",
                                     bg=theme.HEADER_BG, fg=theme.HEADER_MUTED,
                                     font=self.fonts.small, anchor="w",
                                     justify="left")
        self.source_label.pack(anchor="w", padx=20, pady=(0, 14))
        tk.Frame(window, bg=theme.ACCENT, height=3).pack(fill="x")

        body = tk.Frame(window, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=14, pady=12)

        top = tk.Frame(body, bg=theme.BG)
        top.pack(fill="both", expand=True)

        self._build_contents_card(top)
        self._build_destination_card(top)

        self._build_conflict_card(body)

        self.restore_button = ttk.Button(body, text="PUT MY FILES BACK",
                                         style="Primary.TButton",
                                         command=self.start_restore,
                                         state="disabled")
        self.restore_button.pack(fill="x", pady=(12, 0))

        self._build_status_bar()

    def _build_contents_card(self, master: tk.Misc) -> None:
        card = Card(master, self.fonts, step="1", title="What is in this backup",
                    hint="Every one of these files will be put back where it "
                         "came from.")
        card.pack(side="left", fill="both", expand=True, padx=(0, 7))

        self.totals_label = tk.Label(card.body, text="-", bg=theme.PANEL,
                                     fg=theme.ACCENT, font=self.fonts.big,
                                     anchor="w")
        self.totals_label.pack(fill="x", padx=14, pady=(12, 2))

        self.details_label = tk.Label(card.body, text="", bg=theme.PANEL,
                                      fg=theme.MUTED, font=self.fonts.small,
                                      anchor="w", justify="left")
        self.details_label.pack(fill="x", padx=14, pady=(0, 8))

        holder, tree = widgets.scrolled(
            card.body, ttk.Treeview, columns=("count", "size"),
            show="tree", selectmode="none")
        holder.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.contents_tree = tree
        tree.column("#0", stretch=True, minwidth=150, width=200)
        tree.column("count", width=70, anchor="e", stretch=False)
        tree.column("size", width=85, anchor="e", stretch=False)

    def _build_destination_card(self, master: tk.Misc) -> None:
        card = Card(master, self.fonts, step="2", title="Where it goes",
                    hint="Check these before you start. Nothing is written "
                         "until you press the button.")
        card.pack(side="left", fill="both", expand=True, padx=(7, 0))
        self.dest_body = card.body

        self.dest_rows = tk.Frame(self.dest_body, bg=theme.PANEL)
        self.dest_rows.pack(fill="x", padx=14, pady=(12, 4))

        self.profile_banner = Banner(self.dest_body, self.fonts, "", "info")
        self.profile_var = tk.BooleanVar(value=True)
        self.profile_check = ttk.Checkbutton(
            self.dest_body, text="", variable=self.profile_var,
            command=self._update_ready)

        widgets.separator(self.dest_body).pack_configure(padx=14)

        self.sandbox_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.dest_body,
                        text="Restore into one folder instead (nothing on this "
                             "PC is touched)",
                        variable=self.sandbox_var,
                        command=self._on_sandbox_toggled).pack(anchor="w",
                                                               padx=14)
        sandbox_row = tk.Frame(self.dest_body, bg=theme.PANEL)
        sandbox_row.pack(fill="x", padx=14, pady=(4, 10))
        self.sandbox_path = tk.StringVar(
            value=os.path.join(user_profile_dir(), "Desktop",
                               "Restored files"))
        self.sandbox_entry = ttk.Entry(sandbox_row,
                                       textvariable=self.sandbox_path,
                                       state="disabled")
        self.sandbox_entry.pack(side="left", fill="x", expand=True)
        self.sandbox_browse = ttk.Button(sandbox_row, text="Browse...",
                                         style="Ghost.TButton",
                                         state="disabled",
                                         command=self._choose_sandbox)
        self.sandbox_browse.pack(side="left", padx=(6, 0))

        self.ready_banner = Banner(self.dest_body, self.fonts,
                                   "Reading the file list...", "info")
        self.ready_banner.pack(fill="x", padx=14, pady=(0, 12))

    def _build_conflict_card(self, master: tk.Misc) -> None:
        card = Card(master, self.fonts, step="3",
                    title="If a file is already there",
                    hint="This only applies when a file with the same name "
                         "already exists in the same place.")
        card.pack(fill="x", pady=(14, 0))
        row = tk.Frame(card.body, bg=theme.PANEL)
        row.pack(fill="x", padx=14, pady=12)
        self.conflict_var = tk.StringVar(value=CONFLICT_SKIP)
        for value, label in (
                (CONFLICT_SKIP, "Leave the existing file alone (safest)"),
                (CONFLICT_KEEP_BOTH, "Keep both - add '(restored)'"),
                (CONFLICT_OVERWRITE, "Replace it with the backup copy")):
            ttk.Radiobutton(row, text=label, value=value,
                            variable=self.conflict_var).pack(side="left",
                                                             padx=(0, 16))

    def _build_status_bar(self) -> None:
        bar = tk.Frame(self.window, bg=theme.PANEL_ALT)
        bar.pack(fill="x", side="bottom")
        tk.Frame(bar, bg=theme.BORDER, height=1).pack(fill="x")
        inner = tk.Frame(bar, bg=theme.PANEL_ALT)
        inner.pack(fill="x", padx=16, pady=9)
        self.progress = ttk.Progressbar(inner, mode="determinate", maximum=1000)
        self.progress.pack(side="left", fill="x", expand=True)
        self.status_label = tk.Label(inner, text="", bg=theme.PANEL_ALT,
                                     fg=theme.MUTED, font=self.fonts.small,
                                     anchor="w", width=46)
        self.status_label.pack(side="left", padx=(12, 8))
        self.stop_button = ttk.Button(inner, text="Stop", style="Danger.TButton",
                                      command=self._request_cancel,
                                      state="disabled")
        self.stop_button.pack(side="right")

    # ------------------------------------------------------------------
    # Reading the plan
    # ------------------------------------------------------------------

    def _start_reading(self) -> None:
        self.progress.configure(mode="indeterminate")
        self.progress.start(14)
        self.status_label.configure(text="Reading the file list...")

        def work() -> None:
            try:
                plan = read_plan(self.backup_dir)
            except Exception as exc:  # surfaced to the user, never swallowed
                self.events.put(("plan_failed", str(exc)))
            else:
                self.events.put(("plan_ready", plan))

        threading.Thread(target=work, daemon=True).start()

    def _on_plan_ready(self, plan: RestorePlan) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate", value=0)
        self.status_label.configure(text="")
        self.plan = plan
        info = plan.info

        self.source_label.configure(
            text=f"From {info.source_computer or 'an unknown PC'}"
                 f"  -  user {info.source_user or 'unknown'}"
                 f"  -  {info.source_os or 'unknown system'}"
                 f"  -  made {info.created_utc or 'at an unknown time'}")
        self.totals_label.configure(
            text=f"{plan.total_files:,} files   -   "
                 f"{human_bytes(plan.total_bytes)}")
        notes = []
        if not info.complete:
            notes.append("This backup was stopped part way through. Everything "
                         "listed here is still complete and safe to restore.")
        if info.verified:
            notes.append("Every file carries a fingerprint, which is checked as "
                         "it is put back.")
        self.details_label.configure(text="\n".join(notes))

        self.contents_tree.delete(*self.contents_tree.get_children(""))
        rows = sorted(plan.by_extension.items(), key=lambda item: -item[1][1])
        for ext, (count, size) in rows[:60]:
            self.contents_tree.insert(
                "", "end", text=f"  {ext}  {catalog.label_of(ext)}",
                values=(f"{count:,}", human_bytes(size)))

        self._build_bucket_rows(plan)
        self._setup_profile_remap(plan)
        self._update_ready()

        if plan.format_too_new:
            self.ready_banner.set(
                "This backup was made by a newer version of Fenix Vault. "
                "Update the program before restoring it.", "danger")
            self.restore_button.configure(state="disabled")

    def _on_plan_failed(self, message: str) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate", value=0)
        self.ready_banner.set(f"Could not read this backup: {message}", "danger")
        self.status_label.configure(text="Could not read this backup.")

    def _build_bucket_rows(self, plan: RestorePlan) -> None:
        for child in self.dest_rows.winfo_children():
            child.destroy()
        self.bucket_vars.clear()
        suggested = suggest_drive_map(plan)

        for bucket, (count, size) in sorted(plan.buckets.items()):
            row = tk.Frame(self.dest_rows, bg=theme.PANEL)
            row.pack(fill="x", pady=(0, 8))
            tk.Label(row,
                     text=f"{plan.bucket_label(bucket)}   "
                          f"{count:,} files, {human_bytes(size)}",
                     bg=theme.PANEL, fg=theme.TEXT, font=self.fonts.small_bold,
                     anchor="w").pack(fill="x")
            entry_row = tk.Frame(row, bg=theme.PANEL)
            entry_row.pack(fill="x", pady=(3, 0))
            variable = tk.StringVar(value=suggested.get(bucket, ""))
            variable.trace_add("write", lambda *_: self._update_ready())
            self.bucket_vars[bucket] = variable
            entry = ttk.Entry(entry_row, textvariable=variable)
            entry.pack(side="left", fill="x", expand=True)
            ttk.Button(entry_row, text="Browse...", style="Ghost.TButton",
                       command=lambda b=bucket: self._choose_bucket(b)).pack(
                           side="left", padx=(6, 0))

    def _setup_profile_remap(self, plan: RestorePlan) -> None:
        self.profile_from, self.profile_to = suggest_profile_remap(plan.info)
        if not self.profile_from:
            return
        self.profile_banner.set(
            f"This backup came from a different user folder "
            f"({plan.info.source_profile}). This PC uses {self.profile_to}.",
            "warn")
        self.profile_banner.pack(fill="x", padx=14, pady=(4, 4),
                                 before=self.profile_check)
        self.profile_check.configure(
            text="Send those files to this PC's user folders instead")
        self.profile_check.pack(anchor="w", padx=14, pady=(0, 6))

    def _choose_bucket(self, bucket: str) -> None:
        chosen = filedialog.askdirectory(
            parent=self.window,
            title=f"Choose where files from {bucket} should go",
            initialdir=self.bucket_vars[bucket].get() or user_profile_dir())
        if chosen:
            self.bucket_vars[bucket].set(chosen)

    def _choose_sandbox(self) -> None:
        chosen = filedialog.askdirectory(
            parent=self.window, title="Choose an empty folder for the files",
            initialdir=self.sandbox_path.get() or user_profile_dir(),
            mustexist=False)
        if chosen:
            self.sandbox_path.set(chosen)

    def _on_sandbox_toggled(self) -> None:
        on = self.sandbox_var.get()
        state = "normal" if on else "disabled"
        self.sandbox_entry.configure(state=state)
        self.sandbox_browse.configure(state=state)
        for child in self.dest_rows.winfo_children():
            _set_state_deep(child, "disabled" if on else "normal")
        self._update_ready()

    # ------------------------------------------------------------------

    def _current_options(self) -> RestoreOptions:
        options = RestoreOptions(conflict=self.conflict_var.get(), verify=True)
        if self.sandbox_var.get():
            options.sandbox_root = self.sandbox_path.get().strip()
            return options
        options.drive_map = {bucket: variable.get().strip()
                             for bucket, variable in self.bucket_vars.items()}
        if self.profile_from and self.profile_var.get():
            options.profile_from = self.profile_from
            options.profile_to = self.profile_to
        return options

    def _missing_destinations(self) -> list[str]:
        if self.sandbox_var.get():
            return [] if self.sandbox_path.get().strip() else ["folder"]
        missing = []
        for bucket, variable in self.bucket_vars.items():
            if variable.get().strip():
                continue
            if (self.profile_from and self.profile_var.get()
                    and self.profile_from.split("/", 1)[0] == bucket):
                continue
            missing.append(bucket)
        return missing

    def _update_ready(self) -> None:
        if self.plan is None or self.busy:
            return
        missing = self._missing_destinations()
        if missing:
            self.ready_banner.set(
                "Choose where these should go: "
                + ", ".join(f"drive {b}:" for b in missing), "warn")
            self.restore_button.configure(state="disabled")
            return
        if self.sandbox_var.get():
            self.ready_banner.set(
                f"Everything will be rebuilt inside "
                f"{self.sandbox_path.get().strip()}. Nothing else on this PC is "
                f"touched.", "ok")
        else:
            self.ready_banner.set(
                f"Ready. {self.plan.total_files:,} files will be put back in "
                f"their original folders, which are created if missing.", "ok")
        self.restore_button.configure(state="normal")

    # ------------------------------------------------------------------

    def start_restore(self) -> None:
        if self.busy or self.plan is None:
            return
        options = self._current_options()
        if options.sandbox_root:
            where = options.sandbox_root
        else:
            where = "their original folders"
        if not messagebox.askokcancel(
                APP_NAME,
                f"Put {self.plan.total_files:,} files "
                f"({human_bytes(self.plan.total_bytes)}) back into {where}?",
                parent=self.window):
            return

        self.cancel.clear()
        self._set_busy(True)
        self.progress.configure(mode="determinate", style="TProgressbar", value=0)
        backup_dir = self.backup_dir
        plan = self.plan

        def work() -> None:
            result = run_restore(
                backup_dir, options, plan=plan, cancel=self.cancel,
                progress=lambda p: self.events.put(("restore_progress", p)))
            self.events.put(("restore_done", result))

        threading.Thread(target=work, daemon=True).start()

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.restore_button.configure(state="disabled" if busy else "normal")
        self.stop_button.configure(state="normal" if busy else "disabled")

    def _request_cancel(self) -> None:
        self.cancel.set()
        self.status_label.configure(text="Stopping...")

    # ------------------------------------------------------------------

    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "plan_ready":
                    self._on_plan_ready(payload)
                elif kind == "plan_failed":
                    self._on_plan_failed(payload)
                elif kind == "restore_progress":
                    self._on_progress(payload)
                elif kind == "restore_done":
                    self._on_done(payload)
        except queue.Empty:
            pass
        if self.window.winfo_exists():
            self.window.after(80, self._pump)

    def _on_progress(self, state: RestoreProgress) -> None:
        self.progress.configure(value=int(state.fraction * 1000))
        name = os.path.basename(state.current_file) or state.message
        self.status_label.configure(
            text=f"{int(state.fraction * 100)}%  -  {state.files_done:,} of "
                 f"{state.files_total:,}  -  {name[:28]}")

    def _on_done(self, result: RestoreResult) -> None:
        self._set_busy(False)
        self.status_label.configure(text=result.summary())
        if result.ok:
            self.progress.configure(value=1000, style="Done.TProgressbar")
        lines = [result.summary()]
        if result.files_skipped:
            lines.append("\nFiles that were already on this PC were left alone.")
        if result.files_corrupt:
            lines.append("\nSome files did not match their fingerprint. They "
                         "were still written, but check them.")
        if result.errors:
            lines.append("\nFirst problems:")
            lines.extend(f"  {message}" for message in result.errors[:6])
        if result.ok:
            messagebox.showinfo(f"{APP_NAME} - all done", "\n".join(lines),
                                parent=self.window)
        else:
            messagebox.showwarning(f"{APP_NAME} - finished with problems",
                                   "\n".join(lines), parent=self.window)
        self._update_ready()

    def _on_close(self) -> None:
        if self.busy:
            if not messagebox.askyesno(
                    APP_NAME, "A restore is running. Stop it and close?",
                    parent=self.window):
                return
            self.cancel.set()
        self.window.destroy()


def _set_state_deep(widget: tk.Misc, state: str) -> None:
    try:
        widget.configure(state=state)  # type: ignore[call-arg]
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        _set_state_deep(child, state)
