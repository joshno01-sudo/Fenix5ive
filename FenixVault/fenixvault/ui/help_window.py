"""The 'How this works' window.

Deliberately written as prose a non-technical person can read start to finish,
because the moment someone actually needs a backup is the worst possible moment
to be learning what the program does.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..version import APP_NAME, VERSION
from . import theme, widgets

SECTIONS: list[tuple[str, str]] = [
    ("What this program is for",
     "It makes a complete copy of the files you would be upset to lose -- "
     "photos, documents, artwork, cut files, print files, invoices, fonts, "
     "email -- and puts that copy on a drive you choose.\n\n"
     "It does not copy Windows or your installed programs. Those can be "
     "reinstalled. Your work cannot."),

    ("The three columns",
     "LEFT is where to look. It shows every drive attached to this computer "
     "and the folders inside them. Tick a folder and everything inside it is "
     "included. Untick a folder inside a ticked one to leave just that part "
     "out -- the tick box turns half-filled to show the folder is only "
     "partly included.\n\n"
     "MIDDLE is what to save. File types are grouped into plain categories. "
     "Once the folders have been looked through, each row shows how many "
     "files of that type you actually have and how much space they take, so "
     "you can decide with real numbers in front of you.\n\n"
     "RIGHT is the job itself: the totals, the drive it is going to, and the "
     "button that starts it."),

    ("It knows what you have installed",
     "On startup the program reads the list of software installed on this PC. "
     "If it finds Illustrator, CorelDRAW, Silhouette Studio, QuickBooks, "
     "embroidery software or anything else it recognises, the file types "
     "those programs create are ticked for you automatically.\n\n"
     "Anything it does not recognise is not lost either. Every file type "
     "found during the scan that is not in the built-in list appears under "
     "'Other file types found on this PC', with the name Windows itself uses "
     "for it. You can also type in any file ending by hand."),

    ("Recording how the PC is set up",
     "Files are only half of a rebuild. The other half is everything that "
     "lives nowhere you can copy: which printer is on which IP address, the "
     "Wi-Fi password nobody has written down for years, the drive encryption "
     "key without which the old disk is a brick.\n\n"
     "With 'Record this PC's setup' ticked, the backup also gets a page "
     "called REBUILD-THIS-PC.html. Open it on your phone while you reinstall "
     "Windows. It holds pictures of the desktop exactly as it looked, the "
     "list of installed programs, printers and their ports, network settings, "
     "Wi-Fi profiles, what starts with Windows, fonts, your regional "
     "settings, and exported copies of the Windows preference keys.\n\n"
     "Nothing on the machine is changed to collect any of it. Every reading "
     "is taken read-only.\n\n"
     "Because that page can contain Wi-Fi passwords, a BitLocker recovery key "
     "and your Windows product key, it says so at the top in red, and the "
     "drive you back up to should be kept somewhere safe."),

    ("How the copy is laid out",
     "The backup folder holds a folder called Data, and inside that the "
     "original folder structure is reproduced exactly:\n\n"
     "    Data\\C\\Users\\Josh\\Documents\\Logos\\logo.ai\n\n"
     "So a file that lived at C:\\Users\\Josh\\Documents\\Logos\\logo.ai is "
     "still recognisably in Documents, in Logos, under the same name. You can "
     "browse the backup by hand and drag out any single file without running "
     "anything at all."),

    ("Putting it back on another computer",
     "The backup carries the program with it. Copy the backup folder onto a "
     "USB or external drive, plug that drive into the other computer, open "
     "the folder and double-click RESTORE.\n\n"
     "It reads the list of files, rebuilds every folder that is missing, and "
     "puts each file back at the exact path it came from. Nothing needs to be "
     "installed on the second computer first.\n\n"
     "If the new PC has a different user name, it offers to send everything "
     "to the new user's folders. If a drive letter no longer exists, it asks "
     "you to pick somewhere for those files rather than guessing."),

    ("Nothing is overwritten by surprise",
     "Restoring leaves any file that is already there alone unless you "
     "explicitly choose otherwise. You can also tell it to restore everything "
     "into a single folder instead of the original locations, look through "
     "the result, and move things across yourself."),

    ("Running it again later",
     "Point a second backup at the same folder and it only copies what has "
     "changed since last time. Everything already there is left where it is, "
     "so a weekly backup takes a fraction of the time the first one did."),

    ("How you know the copy is good",
     "As each file is copied, a fingerprint of its contents is worked out and "
     "written into the file list. When the file is restored, the fingerprint "
     "is worked out again and compared. If a drive has gone bad and damaged "
     "something, you are told which file, instead of finding out years later."),

    ("If something cannot be copied",
     "A file that is locked by another program, or a folder Windows will not "
     "let you read, is written into backup-report.txt and the run carries on. "
     "One stubborn file never stops the rest of the backup."),
]


def show_help(parent: tk.Misc, fonts: theme.Fonts) -> tk.Toplevel:
    window = tk.Toplevel(parent)
    window.title(f"{APP_NAME} - how this works")
    window.configure(bg=theme.BG)
    widgets.center_on_screen(window, 720, 660)
    window.transient(parent)

    header = tk.Frame(window, bg=theme.HEADER_BG)
    header.pack(fill="x")
    tk.Label(header, text="How this works", bg=theme.HEADER_BG, fg="#ffffff",
             font=fonts.title).pack(anchor="w", padx=20, pady=(16, 2))
    tk.Label(header, text=f"{APP_NAME} {VERSION}", bg=theme.HEADER_BG,
             fg=theme.HEADER_MUTED, font=fonts.small).pack(anchor="w", padx=20,
                                                           pady=(0, 14))
    tk.Frame(window, bg=theme.ACCENT, height=3).pack(fill="x")

    holder = tk.Frame(window, bg=theme.PANEL)
    holder.pack(fill="both", expand=True)
    canvas = tk.Canvas(holder, bg=theme.PANEL, highlightthickness=0, bd=0)
    bar = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=theme.PANEL)
    window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=bar.set)
    canvas.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y")

    def on_configure(_event=None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.itemconfigure(window_id, width=canvas.winfo_width())

    inner.bind("<Configure>", on_configure)
    canvas.bind("<Configure>", on_configure)
    canvas.bind_all("<MouseWheel>",
                    lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
    canvas.bind_all("<Button-4>", lambda _e: canvas.yview_scroll(-2, "units"))
    canvas.bind_all("<Button-5>", lambda _e: canvas.yview_scroll(2, "units"))

    for index, (heading, text) in enumerate(SECTIONS):
        block = tk.Frame(inner, bg=theme.PANEL)
        block.pack(fill="x", padx=24, pady=(18 if index == 0 else 4, 0))
        tk.Label(block, text=heading, bg=theme.PANEL, fg=theme.ACCENT_DARK,
                 font=fonts.body_bold, anchor="w").pack(fill="x")
        tk.Label(block, text=text, bg=theme.PANEL, fg=theme.TEXT,
                 font=fonts.body, anchor="w", justify="left",
                 wraplength=630).pack(fill="x", pady=(3, 12))
        if index < len(SECTIONS) - 1:
            tk.Frame(inner, bg=theme.BORDER, height=1).pack(fill="x", padx=24)

    footer = tk.Frame(window, bg=theme.PANEL_ALT)
    footer.pack(fill="x")
    tk.Frame(footer, bg=theme.BORDER, height=1).pack(fill="x")
    ttk.Button(footer, text="Close", command=window.destroy).pack(
        side="right", padx=16, pady=12)

    def on_close() -> None:
        canvas.unbind_all("<MouseWheel>")
        canvas.unbind_all("<Button-4>")
        canvas.unbind_all("<Button-5>")
        window.destroy()

    window.protocol("WM_DELETE_WINDOW", on_close)
    return window
