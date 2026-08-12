"""The main window: where to look, what to save, back it up.

Threading rule for the whole file: scans and copies run on a worker thread and
report by putting messages on ``self.events``. Only ``_pump`` -- which runs on
the Tk main loop -- ever touches a widget. Tk is not thread-safe and this is
the single place that guarantees we never break that.
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .. import appdetect, catalog
from ..backup import BackupOptions, BackupProgress, BackupResult, estimate, run_backup
from ..manifest import default_backup_name, find_backup_root, is_backup_folder
from ..platformutil import (DRIVE_FIXED, DRIVE_REMOVABLE, human_bytes,
                            list_drives, norm, personal_folders, user_profile_dir)
from ..scanner import ScanProgress, ScanResult, list_subfolders, scan
from ..selection import ExcludeRules, FolderSelection
from ..version import APP_NAME, TAGLINE, VERSION
from . import theme, widgets
from .widgets import Banner, ButtonRow, Card, CheckTree, StatValue

MIN_WIDTH, MIN_HEIGHT = 1060, 680
START_WIDTH, START_HEIGHT = 1280, 800

LOADING_TAG = "__loading__"


class FenixVaultApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.fonts = theme.apply(root)
        self.icons = theme.Icons()

        self.selection = FolderSelection()
        self.excludes = ExcludeRules()
        self.extensions: set[str] = catalog.default_extensions()
        self.custom_extensions: set[str] = set()
        self.scan_result: ScanResult | None = None
        self.detection = appdetect.detect()

        self.events: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.worker: threading.Thread | None = None
        self.busy = False
        self.needs_rescan = True

        # Treeview bookkeeping for the lazily-filled folder tree.
        self.node_path: dict[str, str] = {}
        self.path_node: dict[str, str] = {}
        self.loaded_nodes: set[str] = set()

        self.ext_nodes: dict[str, str] = {}      # extension -> tree item id
        self.cat_nodes: dict[str, str] = {}      # category key -> tree item id
        self.cat_blurbs: dict[str, str] = {}     # category key -> explanation

        self._build()
        self._apply_program_suggestions()
        self._preselect_personal_folders()
        self._refresh_types_tree()
        self._update_summary()

        self.root.after(80, self._pump)
        self.root.after(400, self.start_scan)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.root.title(f"{APP_NAME} {VERSION} - {TAGLINE}")
        self.root.configure(bg=theme.BG)
        self.root.minsize(MIN_WIDTH, MIN_HEIGHT)
        widgets.center_on_screen(self.root, START_WIDTH, START_HEIGHT)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_header()
        # The status bar is packed before the body so that the body, which
        # expands, cannot swallow the space the bar needs.
        self._build_status_bar()

        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=14, pady=(12, 12))

        left = self._build_where_panel(body)
        middle = self._build_what_panel(body)
        right = self._build_action_panel(body)
        body.add(left, weight=3)
        body.add(middle, weight=4)
        body.add(right, weight=3)
        self.body = body

    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg=theme.HEADER_BG)
        header.pack(fill="x", side="top")
        inner = tk.Frame(header, bg=theme.HEADER_BG)
        inner.pack(fill="x", padx=18, pady=(14, 14))

        left = tk.Frame(inner, bg=theme.HEADER_BG)
        left.pack(side="left", fill="x", expand=True)

        title_row = tk.Frame(left, bg=theme.HEADER_BG)
        title_row.pack(anchor="w")
        tk.Label(title_row, text="FENIX", bg=theme.HEADER_BG, fg="#ffffff",
                 font=self.fonts.title).pack(side="left")
        tk.Label(title_row, text="VAULT", bg=theme.HEADER_BG, fg=theme.ACCENT,
                 font=self.fonts.title).pack(side="left", padx=(6, 0))
        tk.Label(title_row, text=f"v{VERSION}", bg=theme.HEADER_BG,
                 fg=theme.HEADER_MUTED, font=self.fonts.small).pack(
                     side="left", padx=(10, 0), pady=(8, 0))

        tk.Label(left,
                 text="Copies your personal and business files onto a drive, "
                      "keeping every folder exactly as it is now.",
                 bg=theme.HEADER_BG, fg="#d8dce4", font=self.fonts.subtitle,
                 anchor="w", justify="left").pack(anchor="w", pady=(4, 8))

        steps = tk.Frame(left, bg=theme.HEADER_BG)
        steps.pack(anchor="w")
        for number, text in ((" 1 ", "Pick where to look"),
                             (" 2 ", "Tick the kinds of files to save"),
                             (" 3 ", "Choose a drive and press Back Up Now")):
            chunk = tk.Frame(steps, bg=theme.HEADER_BG)
            chunk.pack(side="left", padx=(0, 22))
            tk.Label(chunk, text=number, bg=theme.ACCENT, fg="#ffffff",
                     font=self.fonts.step).pack(side="left", padx=(0, 7))
            tk.Label(chunk, text=text, bg=theme.HEADER_BG, fg="#e9ecf1",
                     font=self.fonts.small_bold).pack(side="left")

        right = tk.Frame(inner, bg=theme.HEADER_BG)
        right.pack(side="right", anchor="ne")
        ttk.Button(right, text="How this works", style="HeaderGhost.TButton",
                   command=self.show_help).pack(side="top", anchor="e")
        ttk.Button(right, text="Put files back from a backup",
                   style="HeaderGhost.TButton",
                   command=self.open_restore).pack(side="top", anchor="e",
                                                   pady=(6, 0))
        tk.Label(right, text=appdetect.describe_environment(),
                 bg=theme.HEADER_BG, fg=theme.HEADER_MUTED,
                 font=self.fonts.small).pack(side="top", anchor="e", pady=(8, 0))

        tk.Frame(self.root, bg=theme.ACCENT, height=3).pack(fill="x", side="top")

    # -- panel 1 --------------------------------------------------------

    def _build_where_panel(self, master: tk.Misc) -> tk.Widget:
        card = Card(master, self.fonts, step="1", title="Where to look",
                    hint="These are the drives and folders on this computer. "
                         "Tick a folder to include everything inside it; untick "
                         "anything you do not want.")
        body = card.body

        holder, tree = widgets.scrolled(
            body, CheckTree, icons=self.icons, on_toggle=self._toggle_folder,
            show="tree", selectmode="browse")
        holder.pack(fill="both", expand=True, padx=10, pady=(10, 6))
        self.folder_tree = tree
        tree.column("#0", stretch=True, minwidth=220, width=300)
        tree.bind("<<TreeviewOpen>>", self._on_expand, add="+")

        controls = tk.Frame(body, bg=theme.PANEL)
        controls.pack(fill="x", padx=10, pady=(0, 8))
        ButtonRow(controls, self.fonts, [
            ("My folders", self._preselect_personal_folders),
            ("All drives", self._select_all_drives),
            ("Clear", self._clear_selection),
        ]).pack(anchor="w")

        options = tk.Frame(body, bg=theme.PANEL)
        options.pack(fill="x", padx=10, pady=(2, 8))
        self.var_skip_system = tk.BooleanVar(value=True)
        ttk.Checkbutton(options,
                        text="Skip Windows and program folders (recommended)",
                        variable=self.var_skip_system,
                        command=self._on_excludes_changed).pack(anchor="w")
        self.var_skip_hidden = tk.BooleanVar(value=True)
        ttk.Checkbutton(options, text="Skip hidden and system folders",
                        variable=self.var_skip_hidden,
                        command=self._on_excludes_changed).pack(anchor="w")

        self.scan_button = ttk.Button(
            body, text="Look through these folders", command=self.start_scan)
        self.scan_button.pack(fill="x", padx=10, pady=(0, 10))
        self._refresh_drive_roots()
        return card

    # -- panel 2 --------------------------------------------------------

    def _build_what_panel(self, master: tk.Misc) -> tk.Widget:
        card = Card(master, self.fonts, step="2", title="What to save",
                    hint="Tick the kinds of files that matter. Counts appear "
                         "once the folders above have been looked through.")
        body = card.body

        # Bottom-up in priority order, so a short window shrinks the list of
        # file types rather than hiding the controls that drive it.
        custom = tk.Frame(body, bg=theme.PANEL)
        custom.pack(fill="x", padx=10, pady=(6, 10), side="bottom")
        tk.Label(custom, text="Add another file type:", bg=theme.PANEL,
                 fg=theme.MUTED, font=self.fonts.small).pack(side="left")
        self.custom_entry = ttk.Entry(custom, width=10)
        self.custom_entry.pack(side="left", padx=6)
        self.custom_entry.bind("<Return>", lambda _e: self._add_custom_extension())
        ttk.Button(custom, text="Add", style="Ghost.TButton",
                   command=self._add_custom_extension).pack(side="left")

        self.var_only_found = tk.BooleanVar(value=True)
        ttk.Checkbutton(body, text="Only show types found on this computer",
                        variable=self.var_only_found,
                        command=self._refresh_types_tree).pack(anchor="w",
                                                               padx=12,
                                                               side="bottom")

        controls = tk.Frame(body, bg=theme.PANEL)
        controls.pack(fill="x", padx=10, pady=(0, 4), side="bottom")
        ButtonRow(controls, self.fonts, [
            ("Recommended", self._types_recommended),
            ("Everything", self._types_all),
            ("None", self._types_none),
        ]).pack(anchor="w")

        # The per-category explanation lives here rather than as a row in the
        # tree, where the column width would cut it in half.
        self.type_blurb = tk.Label(
            body, text="Tick a category to include every file type inside it.",
            bg=theme.PANEL, fg=theme.MUTED, font=self.fonts.small, anchor="w",
            justify="left", wraplength=300, height=2)
        self.type_blurb.pack(fill="x", padx=12, pady=(0, 4), side="bottom")
        widgets.autowrap(self.type_blurb, body)

        self.programs_banner = Banner(body, self.fonts, "", "info")
        self.programs_banner.pack(fill="x", padx=10, pady=(10, 0))

        holder, tree = widgets.scrolled(
            body, CheckTree, icons=self.icons, on_toggle=self._toggle_type,
            columns=("files", "size"), show="tree headings", selectmode="browse")
        holder.pack(fill="both", expand=True, padx=10, pady=(8, 6))
        self.types_tree = tree
        tree.heading("#0", text="File type", anchor="w")
        tree.heading("files", text="Files", anchor="e")
        tree.heading("size", text="Size", anchor="e")
        tree.column("#0", stretch=True, minwidth=150, width=210)
        tree.column("files", width=60, anchor="e", stretch=False)
        tree.column("size", width=74, anchor="e", stretch=False)
        tree.tag_configure("category", font=self.fonts.body_bold)
        tree.tag_configure("empty", foreground=theme.FAINT)
        tree.bind("<<TreeviewSelect>>", self._on_type_selected, add="+")
        return card

    # -- panel 3 --------------------------------------------------------

    def _build_action_panel(self, master: tk.Misc) -> tk.Widget:
        card = Card(master, self.fonts, step="3", title="Back it up",
                    hint="Plug in your drive, check the numbers, then press the "
                         "orange button.")
        body = card.body

        # Packed first so pack gives it space before anything else: the button
        # that starts the job must never be the thing that gets clipped.
        bottom = tk.Frame(body, bg=theme.PANEL)
        bottom.pack(fill="x", side="bottom")
        self.backup_button = ttk.Button(bottom, text="BACK UP NOW",
                                        style="Primary.TButton",
                                        command=self.start_backup)
        self.backup_button.pack(fill="x", padx=14, pady=(10, 6))
        footer = tk.Label(
            bottom,
            text="Afterwards: unplug the drive, plug it into the other PC, open "
                 "the backup folder and double-click RESTORE.",
            bg=theme.PANEL, fg=theme.MUTED, font=self.fonts.small,
            anchor="w", justify="left", wraplength=260)
        footer.pack(fill="x", padx=14, pady=(0, 12))
        widgets.autowrap(footer, bottom, pad=32)

        # Everything below is packed bottom-up in priority order, so that when
        # the panel is short it is the breakdown list -- the one purely
        # informational widget -- that gives up its rows, never a control.
        options = tk.Frame(body, bg=theme.PANEL)
        options.pack(fill="x", padx=14, pady=(0, 2), side="bottom")
        self.var_payload = tk.BooleanVar(value=True)
        ttk.Checkbutton(options,
                        text="Put the restore program in with the backup",
                        variable=self.var_payload).pack(anchor="w", side="bottom")
        self.var_incremental = tk.BooleanVar(value=True)
        ttk.Checkbutton(options,
                        text="Only copy what has changed since last time",
                        variable=self.var_incremental).pack(anchor="w",
                                                            side="bottom")
        self.var_verify = tk.BooleanVar(value=True)
        ttk.Checkbutton(options,
                        text="Fingerprint every file so damage can be spotted",
                        variable=self.var_verify).pack(anchor="w", side="bottom")

        self.space_banner = Banner(body, self.fonts, "", "info")
        self.space_banner.pack(fill="x", padx=14, pady=(4, 8), side="bottom")

        dest_row = tk.Frame(body, bg=theme.PANEL)
        dest_row.pack(fill="x", padx=14, pady=(4, 0), side="bottom")
        self.dest_var = tk.StringVar(value=self._default_destination())
        self.dest_entry = ttk.Entry(dest_row, textvariable=self.dest_var)
        self.dest_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(dest_row, text="Browse...", style="Ghost.TButton",
                   command=self._choose_destination).pack(side="left", padx=(6, 0))
        self.dest_var.trace_add("write", lambda *_: self._update_space_banner())

        tk.Label(body, text="COPY THE BACKUP TO", bg=theme.PANEL,
                 fg=theme.FAINT, font=self.fonts.small_bold,
                 anchor="w").pack(fill="x", padx=14, pady=(8, 0), side="bottom")

        stats = tk.Frame(body, bg=theme.PANEL)
        stats.pack(fill="x", padx=14, pady=(14, 4))
        self.stat_files = StatValue(stats, self.fonts, "files will be copied")
        self.stat_files.pack(side="left", fill="x", expand=True)
        self.stat_size = StatValue(stats, self.fonts, "total size",
                                   colour=theme.TEXT)
        self.stat_size.pack(side="left", fill="x", expand=True)

        self.stale_label = tk.Label(body, text="", bg=theme.PANEL,
                                    fg=theme.WARN, font=self.fonts.small_bold,
                                    anchor="w", justify="left", wraplength=260)
        self.stale_label.pack(fill="x", padx=14)
        widgets.autowrap(self.stale_label, body)

        tk.Label(body, text="BIGGEST FILE TYPES SELECTED", bg=theme.PANEL,
                 fg=theme.FAINT, font=self.fonts.small_bold,
                 anchor="w").pack(fill="x", padx=14, pady=(8, 3))
        self.breakdown = ttk.Treeview(body, columns=("count", "size"),
                                      show="tree", height=4, selectmode="none")
        self.breakdown.column("#0", width=90, minwidth=70, stretch=True)
        self.breakdown.column("count", width=58, anchor="e", stretch=False)
        self.breakdown.column("size", width=72, anchor="e", stretch=False)
        self.breakdown.pack(fill="x", padx=14, pady=(0, 6))
        # Absorbs the leftover slack so the list above always ends on a whole
        # row rather than a sliced one.
        tk.Frame(body, bg=theme.PANEL).pack(fill="both", expand=True)

        return card

    def _build_status_bar(self) -> None:
        bar = tk.Frame(self.root, bg=theme.PANEL_ALT)
        bar.pack(fill="x", side="bottom")
        tk.Frame(bar, bg=theme.BORDER, height=1).pack(fill="x")
        inner = tk.Frame(bar, bg=theme.PANEL_ALT)
        inner.pack(fill="x", padx=16, pady=9)

        self.progress = ttk.Progressbar(inner, mode="determinate", maximum=1000)
        self.progress.pack(side="left", fill="x", expand=True)
        self.status_label = tk.Label(inner, text="Ready.", bg=theme.PANEL_ALT,
                                     fg=theme.MUTED, font=self.fonts.small,
                                     anchor="w", width=54)
        self.status_label.pack(side="left", padx=(12, 8))
        self.stop_button = ttk.Button(inner, text="Stop", style="Danger.TButton",
                                      command=self._request_cancel,
                                      state="disabled")
        self.stop_button.pack(side="right")

    # ------------------------------------------------------------------
    # Folder tree
    # ------------------------------------------------------------------

    def _refresh_drive_roots(self) -> None:
        self.folder_tree.delete(*self.folder_tree.get_children(""))
        self.node_path.clear()
        self.path_node.clear()
        self.loaded_nodes.clear()
        for drive in list_drives():
            suffix = ""
            if drive.kind == DRIVE_REMOVABLE:
                suffix = "  - removable"
            elif drive.is_system:
                suffix = "  - this PC"
            label = (f"{drive.path}  {drive.label or 'Local Disk'}{suffix}"
                     f"   ({human_bytes(drive.free_bytes)} free)")
            node = self.folder_tree.insert(
                "", "end", text=label,
                image=self.icons.checkbox(self.selection.state(drive.path)),
                open=False)
            self._register(node, drive.path)
            self.folder_tree.insert(node, "end", text="", tags=(LOADING_TAG,))

    def _register(self, node: str, path: str) -> None:
        self.node_path[node] = path
        self.path_node[norm(path)] = node

    def _on_expand(self, _event: tk.Event) -> None:
        node = self.folder_tree.focus()
        if node:
            self._load_children(node)

    def _load_children(self, node: str) -> None:
        if node in self.loaded_nodes:
            return
        self.loaded_nodes.add(node)
        path = self.node_path.get(node)
        if not path:
            return
        for child in self.folder_tree.get_children(node):
            if LOADING_TAG in self.folder_tree.item(child, "tags"):
                self.folder_tree.delete(child)
        folders = list_subfolders(path, self._current_excludes())
        if not folders:
            return
        for folder in folders:
            child = self.folder_tree.insert(
                node, "end", text=folder.name,
                image=self.icons.checkbox(self.selection.state(folder.path)))
            self._register(child, folder.path)
            if folder.has_children:
                self.folder_tree.insert(child, "end", text="", tags=(LOADING_TAG,))

    def _toggle_folder(self, node: str) -> None:
        path = self.node_path.get(node)
        if not path:
            return
        self.selection.toggle(path)
        self._refresh_folder_states()
        self._mark_stale()

    def _refresh_folder_states(self) -> None:
        for node, path in self.node_path.items():
            if self.folder_tree.exists(node):
                self.folder_tree.set_check(node, self.selection.state(path))

    def _reveal(self, path: str) -> None:
        """Expand the tree down to *path* so a ticked folder is visible."""
        parts: list[str] = []
        current = os.path.abspath(path)
        while True:
            parts.append(current)
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        for step in reversed(parts):
            node = self.path_node.get(norm(step))
            if node is None:
                return
            self._load_children(node)
            if norm(step) != norm(path):
                self.folder_tree.item(node, open=True)

    def _preselect_personal_folders(self) -> None:
        self.selection.clear()
        folders = personal_folders()
        for path in folders.values():
            self.selection.set(path, True)
        if not folders:
            self.selection.set(user_profile_dir(), True)
        for path in list(folders.values())[:8]:
            self._reveal(path)
        self._refresh_folder_states()
        self._mark_stale()

    def _select_all_drives(self) -> None:
        self.selection.clear()
        for drive in list_drives():
            if drive.kind in (DRIVE_FIXED, DRIVE_REMOVABLE):
                self.selection.set(drive.path, True)
        self._refresh_folder_states()
        self._mark_stale()

    def _clear_selection(self) -> None:
        self.selection.clear()
        self._refresh_folder_states()
        self._mark_stale()

    def _current_excludes(self) -> ExcludeRules:
        return ExcludeRules(skip_system=self.var_skip_system.get(),
                            skip_hidden=self.var_skip_hidden.get())

    def _on_excludes_changed(self) -> None:
        self.excludes = self._current_excludes()
        expanded = [self.node_path[node] for node in self.node_path
                    if self.folder_tree.exists(node)
                    and self.folder_tree.item(node, "open")]
        self._refresh_drive_roots()
        for path in expanded:
            self._reveal(path)
        self._refresh_folder_states()
        self._mark_stale()

    # ------------------------------------------------------------------
    # File-type tree
    # ------------------------------------------------------------------

    def _apply_program_suggestions(self) -> None:
        names = self.detection.matched_program_names()
        if not names:
            self.detection.suggested_categories = set()
            return
        for key in self.detection.suggested_categories:
            found = catalog.category_by_key(key)
            if found:
                self.extensions.update(found.extensions)

    def _programs_message(self) -> tuple[str, str]:
        names = self.detection.matched_program_names()
        if names:
            shown = ", ".join(names[:4])
            more = f" and {len(names) - 4} more" if len(names) > 4 else ""
            return (f"Found on this PC: {shown}{more}. Their file types are "
                    f"already ticked below.", "ok")
        if self.detection.programs:
            return (f"{len(self.detection.programs)} programs are installed. "
                    f"Nothing needed changing - the recommended file types are "
                    f"ticked.", "info")
        return ("Tick everything you would be upset to lose. The recommended "
                "set is already on.", "info")

    def _visible_extensions(self) -> dict[str, tuple[int, int]]:
        """Extension -> (count, bytes) from the last scan, or empty before one."""
        if self.scan_result is None:
            return {}
        return {ext: (self.scan_result.ext_counts.get(ext, 0),
                      self.scan_result.ext_bytes.get(ext, 0))
                for ext in self.scan_result.ext_counts}

    def _refresh_types_tree(self) -> None:
        tree = self.types_tree
        opened = {key for key, node in self.cat_nodes.items()
                  if tree.exists(node) and tree.item(node, "open")}
        tree.delete(*tree.get_children(""))
        self.ext_nodes.clear()
        self.cat_nodes.clear()
        self.cat_blurbs.clear()

        found = self._visible_extensions()
        only_found = self.var_only_found.get() and self.scan_result is not None
        message, tone = self._programs_message()
        self.programs_banner.set(message, tone)

        groups: list[tuple[str, str, str, list[str]]] = [
            (cat.key, cat.name, cat.blurb, cat.extensions)
            for cat in catalog.CATEGORIES
        ]
        unknown = sorted(ext for ext in found
                         if catalog.category_of(ext) is None
                         and ext not in self.custom_extensions)
        if unknown:
            groups.append((catalog.DISCOVERED_KEY,
                           "Other file types found on this PC",
                           "Not in our list, but present on this computer. "
                           "Tick anything you recognise.",
                           unknown))
        if self.custom_extensions:
            groups.append((catalog.CUSTOM_KEY, "Added by you",
                           "File types you typed in.",
                           sorted(self.custom_extensions)))

        for key, name, blurb, extensions in groups:
            shown = [ext for ext in extensions
                     if not only_found or found.get(ext, (0, 0))[0] > 0]
            if only_found and not shown:
                continue
            count = sum(found.get(ext, (0, 0))[0] for ext in extensions)
            size = sum(found.get(ext, (0, 0))[1] for ext in extensions)
            node = tree.insert(
                "", "end", text=f" {name}",
                image=self.icons.checkbox(self._category_state(extensions)),
                values=(f"{count:,}" if count else "",
                        human_bytes(size) if size else ""),
                tags=("category",),
                open=key in opened or (bool(opened) is False and count > 0))
            self.cat_nodes[key] = node
            self.cat_blurbs[key] = blurb
            for ext in shown:
                ext_count, ext_size = found.get(ext, (0, 0))
                label = catalog.label_of(ext)
                if key == catalog.DISCOVERED_KEY:
                    label = self.detection.registered.get(ext, "File")
                tags = () if ext_count else ("empty",)
                child = tree.insert(
                    node, "end", text=f"  {ext}   {label}",
                    image=self.icons.checkbox(
                        "on" if ext in self.extensions else "off"),
                    values=(f"{ext_count:,}" if ext_count else "-",
                            human_bytes(ext_size) if ext_size else "-"),
                    tags=tags)
                self.ext_nodes[ext] = child

    def _on_type_selected(self, _event: tk.Event) -> None:
        selected = self.types_tree.focus()
        for key, node in self.cat_nodes.items():
            if node == selected:
                self.type_blurb.configure(text=self.cat_blurbs.get(key, ""))
                return
        for ext, node in self.ext_nodes.items():
            if node == selected:
                parent = self.types_tree.parent(node)
                for key, cat_node in self.cat_nodes.items():
                    if cat_node == parent:
                        self.type_blurb.configure(
                            text=f"{ext} - {catalog.label_of(ext)}. "
                                 f"Part of {self.cat_blurbs.get(key, '')}")
                        return
                return

    def _category_state(self, extensions: list[str]) -> str:
        if not extensions:
            return "off"
        selected = sum(1 for ext in extensions if ext in self.extensions)
        if selected == 0:
            return "off"
        if selected == len(extensions):
            return "on"
        return "partial"

    def _toggle_type(self, node: str) -> None:
        for ext, item in self.ext_nodes.items():
            if item == node:
                if ext in self.extensions:
                    self.extensions.discard(ext)
                else:
                    self.extensions.add(ext)
                self.types_tree.set_check(
                    node, "on" if ext in self.extensions else "off")
                self._refresh_category_checks()
                self._update_summary()
                return
        for key, item in self.cat_nodes.items():
            if item == node:
                extensions = self._extensions_of(key)
                turning_on = self._category_state(extensions) != "on"
                if turning_on:
                    self.extensions.update(extensions)
                else:
                    self.extensions.difference_update(extensions)
                for ext in extensions:
                    child = self.ext_nodes.get(ext)
                    if child and self.types_tree.exists(child):
                        self.types_tree.set_check(
                            child, "on" if turning_on else "off")
                self.types_tree.set_check(node, "on" if turning_on else "off")
                self._update_summary()
                return

    def _extensions_of(self, key: str) -> list[str]:
        if key == catalog.CUSTOM_KEY:
            return sorted(self.custom_extensions)
        if key == catalog.DISCOVERED_KEY:
            found = self._visible_extensions()
            return sorted(ext for ext in found
                          if catalog.category_of(ext) is None
                          and ext not in self.custom_extensions)
        found = catalog.category_by_key(key)
        return found.extensions if found else []

    def _refresh_category_checks(self) -> None:
        for key, node in self.cat_nodes.items():
            if self.types_tree.exists(node):
                self.types_tree.set_check(
                    node, self._category_state(self._extensions_of(key)))

    def _types_recommended(self) -> None:
        self.extensions = catalog.default_extensions()
        self._apply_program_suggestions()
        self.extensions.update(self.custom_extensions)
        self._refresh_types_tree()
        self._update_summary()

    def _types_all(self) -> None:
        self.extensions = catalog.known_extensions()
        self.extensions.update(self.custom_extensions)
        found = self._visible_extensions()
        self.extensions.update(found)
        self._refresh_types_tree()
        self._update_summary()

    def _types_none(self) -> None:
        self.extensions = set()
        self._refresh_types_tree()
        self._update_summary()

    def _add_custom_extension(self) -> None:
        raw = self.custom_entry.get()
        ext = catalog.normalise_ext(raw)
        if not ext:
            messagebox.showwarning(
                APP_NAME,
                "Type a file ending such as  ai  or  .plt  and press Add.",
                parent=self.root)
            return
        self.custom_entry.delete(0, "end")
        if catalog.category_of(ext) is None:
            self.custom_extensions.add(ext)
        self.extensions.add(ext)
        self._refresh_types_tree()
        self._update_summary()

    # ------------------------------------------------------------------
    # Summary panel
    # ------------------------------------------------------------------

    def _default_destination(self) -> str:
        """Guess the drive they plugged in: the emptiest usable removable one."""
        usable = [d for d in list_drives()
                  if d.kind == DRIVE_REMOVABLE and d.free_bytes > 1 << 30]
        if usable:
            return max(usable, key=lambda d: d.free_bytes).path
        desktop = personal_folders().get("Desktop")
        return desktop or user_profile_dir()

    def _choose_destination(self) -> None:
        chosen = filedialog.askdirectory(
            parent=self.root, title="Choose the drive or folder for the backup",
            initialdir=self.dest_var.get() or user_profile_dir(), mustexist=False)
        if chosen:
            self.dest_var.set(chosen)

    def _selected_totals(self) -> tuple[int, int]:
        if self.scan_result is None:
            return 0, 0
        return self.scan_result.files_for(self.extensions)

    def _update_summary(self) -> None:
        count, size = self._selected_totals()
        self.stat_files.set(f"{count:,}" if self.scan_result else "-")
        self.stat_size.set(human_bytes(size) if self.scan_result else "-")

        self.breakdown.delete(*self.breakdown.get_children(""))
        if self.scan_result is not None:
            rows = self.scan_result.top_extensions(self.extensions, limit=6)
            if not rows:
                self.breakdown.insert("", "end", text="  nothing selected yet",
                                      values=("", ""))
            for ext, ext_count, ext_size in rows:
                self.breakdown.insert(
                    "", "end", text=f"  {ext}  {catalog.label_of(ext)}",
                    values=(f"{ext_count:,}", human_bytes(ext_size)))
        else:
            self.breakdown.insert("", "end",
                                  text="  look through your folders first",
                                  values=("", ""))
        self._update_space_banner()
        self._refresh_category_checks()

    def _update_space_banner(self) -> None:
        destination = self.dest_var.get().strip()
        if not destination:
            self.space_banner.set("Choose a drive or folder for the backup.",
                                  "warn")
            return
        count, size = self._selected_totals()
        if self.scan_result is None:
            self.space_banner.set(
                "Press 'Look through these folders' to see how much there is.",
                "info")
            return
        fits, message = estimate(count, size, destination)
        self.space_banner.set(message, "ok" if fits else "danger")

    def _mark_stale(self) -> None:
        self.needs_rescan = True
        if self.scan_result is not None:
            self.stale_label.configure(
                text="Folders changed - look through them again to update these "
                     "numbers.")
            self.scan_button.configure(text="Look through these folders again")

    def _clear_stale(self) -> None:
        self.needs_rescan = False
        self.stale_label.configure(text="")
        self.scan_button.configure(text="Look through these folders again")

    # ------------------------------------------------------------------
    # Work
    # ------------------------------------------------------------------

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.scan_button.configure(state=state)
        self.backup_button.configure(state=state)
        self.stop_button.configure(state="normal" if busy else "disabled")

    def _request_cancel(self) -> None:
        self.cancel.set()
        self.status_label.configure(text="Stopping...")

    def start_scan(self) -> None:
        if self.busy:
            return
        if self.selection.is_empty():
            messagebox.showinfo(
                APP_NAME, "Tick at least one drive or folder on the left first.",
                parent=self.root)
            return
        self.cancel.clear()
        self.excludes = self._current_excludes()
        self._set_busy(True)
        self.progress.configure(mode="indeterminate", style="TProgressbar")
        self.progress.start(14)
        self.status_label.configure(text="Looking through your folders...")

        selection = self.selection
        excludes = self.excludes

        def work() -> None:
            result = scan(selection, excludes,
                          progress=lambda p: self.events.put(("scan_progress", p)),
                          cancel=self.cancel)
            self.events.put(("scan_done", result))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def start_backup(self) -> None:
        if self.busy:
            return
        if self.scan_result is None or self.needs_rescan:
            if not messagebox.askyesno(
                    APP_NAME,
                    "The folders have not been looked through since you last "
                    "changed them.\n\nBack up anyway? Everything currently "
                    "ticked will still be copied correctly.",
                    parent=self.root):
                return
        if not self.extensions:
            messagebox.showinfo(APP_NAME,
                                "Tick at least one kind of file in the middle "
                                "column.", parent=self.root)
            return
        destination = self.dest_var.get().strip()
        if not destination:
            messagebox.showinfo(APP_NAME, "Choose where the backup should go.",
                                parent=self.root)
            return
        if not os.path.isdir(destination):
            try:
                os.makedirs(destination, exist_ok=True)
            except OSError as exc:
                messagebox.showerror(APP_NAME,
                                     f"Cannot use that destination:\n{exc}",
                                     parent=self.root)
                return

        count, size = self._selected_totals()
        fits, message = estimate(count, size, destination)
        if not fits and not messagebox.askyesno(
                APP_NAME, f"{message}\n\nStart anyway? It will copy what it can "
                          f"and tell you where it stopped.", parent=self.root):
            return

        backup_dir = os.path.join(destination, default_backup_name())
        if not messagebox.askokcancel(
                APP_NAME,
                f"Copy {count:,} files ({human_bytes(size)}) to:\n\n{backup_dir}"
                f"\n\nYour original files are not touched.", parent=self.root):
            return

        self.cancel.clear()
        self._set_busy(True)
        self.progress.stop()
        self.progress.configure(mode="determinate", style="TProgressbar", value=0)
        self.status_label.configure(text="Starting the copy...")

        selection = self.selection
        excludes = self._current_excludes()
        extensions = set(self.extensions)
        options = BackupOptions(verify=self.var_verify.get(),
                                incremental=self.var_incremental.get(),
                                include_restore_tool=self.var_payload.get(),
                                expected_files=count, expected_bytes=size)

        def work() -> None:
            result = run_backup(
                selection, excludes, extensions, backup_dir, options,
                progress=lambda p: self.events.put(("backup_progress", p)),
                cancel=self.cancel)
            self.events.put(("backup_done", result))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    # ------------------------------------------------------------------
    # Event pump - the only code that touches widgets during work
    # ------------------------------------------------------------------

    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "scan_progress":
                    self._on_scan_progress(payload)
                elif kind == "scan_done":
                    self._on_scan_done(payload)
                elif kind == "backup_progress":
                    self._on_backup_progress(payload)
                elif kind == "backup_done":
                    self._on_backup_done(payload)
        except queue.Empty:
            pass
        self.root.after(80, self._pump)

    def _on_scan_progress(self, state: ScanProgress) -> None:
        folder = os.path.basename(state.current_dir.rstrip("\\/")) or state.current_dir
        self.status_label.configure(
            text=f"{state.files_seen:,} files seen "
                 f"({human_bytes(state.bytes_seen)}) - in {folder[:28]}")

    def _on_scan_done(self, result: ScanResult) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate", value=0)
        self.scan_result = result
        self._set_busy(False)
        self._clear_stale()
        self._refresh_types_tree()
        self._update_summary()
        if result.cancelled:
            self.status_label.configure(
                text=f"Stopped. Counted {result.total_files:,} files so far.")
        else:
            self.status_label.configure(
                text=f"Found {result.total_files:,} files "
                     f"({human_bytes(result.total_bytes)}) in "
                     f"{result.dirs_scanned:,} folders.")
        if result.errors:
            self.status_label.configure(
                text=self.status_label.cget("text")
                + f"  {len(result.errors)} folder(s) could not be read.")

    def _on_backup_progress(self, state: BackupProgress) -> None:
        self.progress.configure(value=int(state.fraction * 1000))
        name = os.path.basename(state.current_file) or state.message
        self.status_label.configure(
            text=f"{int(state.fraction * 100)}%  -  "
                 f"{state.files_done:,} of {state.files_total:,}  -  {name[:34]}")

    def _on_backup_done(self, result: BackupResult) -> None:
        self._set_busy(False)
        self.progress.configure(value=1000 if result.ok else self.progress["value"],
                                style="Done.TProgressbar" if result.ok
                                else "TProgressbar")
        self.status_label.configure(text=result.summary())
        self._show_backup_result(result)

    def _show_backup_result(self, result: BackupResult) -> None:
        lines = [result.summary(), "", f"Saved in:\n{result.backup_dir}"]
        if result.report_path:
            lines += ["", f"Some items were skipped. Details in:\n"
                          f"{os.path.basename(result.report_path)}"]
        if result.cancelled:
            lines += ["", "You stopped it early. What was copied is complete "
                          "and can be restored; run it again to finish."]
        else:
            lines += ["", "Now unplug the drive, plug it into the other PC, open "
                          "this folder and double-click RESTORE."]
        title = f"{APP_NAME} - backup finished"
        if result.files_failed or result.cancelled:
            messagebox.showwarning(title, "\n".join(lines), parent=self.root)
        else:
            messagebox.showinfo(title, "\n".join(lines), parent=self.root)

    # ------------------------------------------------------------------
    # Secondary windows
    # ------------------------------------------------------------------

    def show_help(self) -> None:
        from .help_window import show_help
        show_help(self.root, self.fonts)

    def open_restore(self, backup_dir: str | None = None) -> None:
        from .restore_window import RestoreWindow
        if backup_dir is None:
            chosen = filedialog.askdirectory(
                parent=self.root,
                title="Find the backup folder (the one holding 'Data')",
                initialdir=self.dest_var.get() or user_profile_dir())
            if not chosen:
                return
            backup_dir = find_backup_root(chosen) or chosen
        if not is_backup_folder(backup_dir):
            messagebox.showerror(
                APP_NAME,
                "That folder is not a Fenix Vault backup.\n\nLook for the folder "
                "that contains 'backup-info.json' and a 'Data' folder inside it.",
                parent=self.root)
            return
        RestoreWindow(self.root, self.fonts, self.icons, backup_dir)

    def _on_close(self) -> None:
        if self.busy:
            if not messagebox.askyesno(
                    APP_NAME, "Something is still running. Stop it and close?",
                    parent=self.root):
                return
            self.cancel.set()
        self.root.destroy()


def launch(restore_dir: str | None = None) -> int:
    """Open the window. Returns a process exit code."""
    root = tk.Tk()
    app = FenixVaultApp(root)
    if restore_dir:
        root.after(200, lambda: app.open_restore(restore_dir))
    elif find_backup_root() and is_backup_folder(find_backup_root() or ""):
        # Launched from inside a backup folder: this is almost certainly
        # RESTORE.exe on a USB drive, so go straight to putting files back.
        root.after(200, lambda: app.open_restore(find_backup_root()))
    root.mainloop()
    return 0
