"""The rebuild report.

One HTML file, written to the root of the backup, that answers "how was this
machine set up?" without needing the machine. It is meant to be opened on a
phone or a second computer while the first one is being reinstalled, so it has
to work with no network, no fonts to download and no scripts.
"""

from __future__ import annotations

import html
import os
from datetime import datetime

from .sysinfo import SysSnapshot
from .version import APP_NAME, VERSION

REPORT_FILENAME = "REBUILD-THIS-PC.html"

_STYLE = """
:root {
  --bg: #f2f3f6; --panel: #ffffff; --ink: #1b1e25; --muted: #626a78;
  --line: #d9dce3; --accent: #e2521a; --accent-dark: #b8400f;
  --warn-bg: #fdf3e3; --warn-ink: #8a4c04;
  --danger-bg: #fdecea; --danger-ink: #a51f18;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.55 "Segoe UI", system-ui, -apple-system, sans-serif;
}
header { background: #15171c; color: #fff; padding: 28px 20px 22px; }
header h1 { margin: 0; font-size: 1.7rem; letter-spacing: .01em; }
header h1 span { color: var(--accent); }
header .meta { color: #a6adba; font-size: .92rem; margin-top: 8px; }
header .rule { height: 3px; background: var(--accent); margin-top: 22px;
  margin-left: -20px; margin-right: -20px; }
main { max-width: 900px; margin: 0 auto; padding: 20px 16px 80px; }
.card { background: var(--panel); border: 1px solid var(--line);
  border-radius: 8px; padding: 18px 20px; margin: 0 0 18px; }
.card h2 { margin: 0 0 4px; font-size: 1.12rem; }
.card h2 a { color: inherit; text-decoration: none; }
.note { color: var(--muted); font-size: .9rem; margin: 6px 0 12px; }
pre { background: #f7f8fa; border: 1px solid var(--line); border-radius: 6px;
  padding: 12px 14px; overflow-x: auto; font-size: .84rem; line-height: 1.45;
  font-family: Consolas, "SF Mono", Menlo, monospace; white-space: pre; margin: 0; }
.banner { border-radius: 8px; padding: 14px 18px; margin: 0 0 18px;
  border: 1px solid transparent; }
.banner.danger { background: var(--danger-bg); color: var(--danger-ink);
  border-color: #f0c4c0; }
.banner.warn { background: var(--warn-bg); color: var(--warn-ink);
  border-color: #ecd6ac; }
.banner strong { display: block; margin-bottom: 4px; }
.toc { columns: 2; column-gap: 26px; margin: 0; padding-left: 20px; }
.toc li { margin: 2px 0; break-inside: avoid; }
.toc a { color: var(--accent-dark); text-decoration: none; }
.toc a:hover { text-decoration: underline; }
.shots { display: grid; grid-template-columns: 1fr; gap: 14px; }
.shots figure { margin: 0; }
.shots img { width: 100%; height: auto; border: 1px solid var(--line);
  border-radius: 6px; display: block; }
.shots figcaption { color: var(--muted); font-size: .85rem; margin-top: 5px; }
.missing { color: var(--muted); font-style: italic; }
.tag { display: inline-block; background: var(--warn-bg); color: var(--warn-ink);
  border-radius: 4px; font-size: .72rem; padding: 2px 7px; margin-left: 8px;
  vertical-align: middle; font-weight: 600; letter-spacing: .02em; }
footer { color: var(--muted); font-size: .85rem; text-align: center;
  padding: 0 16px 40px; }
@media (max-width: 640px) { .toc { columns: 1; } body { font-size: 15px; } }
@media print {
  body { background: #fff; } .card { break-inside: avoid; border-color: #bbb; }
  header { background: #fff; color: #000; } header h1 span { color: #000; }
}
"""


def _escape(text: str) -> str:
    return html.escape(text or "", quote=False)


def _slug(key: str) -> str:
    return "section-" + "".join(ch if ch.isalnum() else "-" for ch in key)


def build_html(snapshot: SysSnapshot, computer: str = "", when: str = "",
               backup_note: str = "") -> str:
    """Render the whole report as a single HTML string."""
    stamp = when or datetime.now().strftime("%d %B %Y at %H:%M")
    name = computer or "this PC"

    parts: list[str] = []
    parts.append("<!doctype html>\n<html lang=\"en\">\n<head>")
    parts.append("<meta charset=\"utf-8\">")
    parts.append("<meta name=\"viewport\" content=\"width=device-width,"
                 "initial-scale=1\">")
    parts.append(f"<title>Rebuilding {_escape(name)}</title>")
    parts.append(f"<style>{_STYLE}</style>")
    parts.append("</head>\n<body>")

    parts.append("<header>")
    parts.append(f"<h1>How to rebuild <span>{_escape(name)}</span></h1>")
    parts.append(f"<div class=\"meta\">Recorded {_escape(stamp)} by "
                 f"{APP_NAME} {VERSION}</div>")
    parts.append("<div class=\"rule\"></div>")
    parts.append("</header>")
    parts.append("<main>")

    parts.append("<div class=\"banner warn\"><strong>Read this before you "
                 "wipe the machine.</strong>Everything below describes how "
                 "this PC was set up. Your files are in the "
                 "<code>Data</code> folder beside this report; this page is "
                 "the other half &mdash; the settings, drivers, passwords and "
                 "program list that no file copy can capture.</div>")

    if snapshot.holds_secrets:
        parts.append("<div class=\"banner danger\"><strong>This page contains "
                     "passwords.</strong>Wi-Fi keys, and possibly a BitLocker "
                     "recovery key and your Windows product key, are printed "
                     "in plain text further down. Keep this drive somewhere "
                     "safe and do not hand it to anyone you would not give "
                     "those to.</div>")

    if backup_note:
        parts.append(f"<div class=\"card\"><h2>What was backed up</h2>"
                     f"<pre>{_escape(backup_note)}</pre></div>")

    shown = [s for s in snapshot.sections if s.ok or s.error]
    if snapshot.screenshots or shown:
        parts.append("<div class=\"card\"><h2>On this page</h2><ul class=\"toc\">")
        if snapshot.screenshots:
            parts.append("<li><a href=\"#screenshots\">Pictures of the "
                         "desktop</a></li>")
        for section in shown:
            parts.append(f"<li><a href=\"#{_slug(section.key)}\">"
                         f"{_escape(section.title)}</a></li>")
        parts.append("</ul></div>")

    if snapshot.screenshots:
        parts.append("<div class=\"card\" id=\"screenshots\">")
        parts.append("<h2>Pictures of the desktop</h2>")
        parts.append("<p class=\"note\">Taken the moment the backup ran: "
                     "icon positions, what was pinned to the taskbar, and "
                     "which windows were open.</p>")
        parts.append("<div class=\"shots\">")
        for path in snapshot.screenshots:
            relative = "SystemSnapshot/Screenshots/" + os.path.basename(path)
            label = os.path.splitext(os.path.basename(path))[0].replace("-", " ")
            parts.append(f"<figure><img src=\"{_escape(relative)}\" "
                         f"alt=\"{_escape(label)}\" loading=\"lazy\">"
                         f"<figcaption>{_escape(label)}</figcaption></figure>")
        parts.append("</div></div>")

    for section in shown:
        parts.append(f"<div class=\"card\" id=\"{_slug(section.key)}\">")
        tag = "<span class=\"tag\">CONTAINS SECRETS</span>" \
            if section.sensitive else ""
        parts.append(f"<h2><a href=\"#{_slug(section.key)}\">"
                     f"{_escape(section.title)}</a>{tag}</h2>")
        if section.note:
            parts.append(f"<p class=\"note\">{_escape(section.note)}</p>")
        if section.error:
            parts.append(f"<p class=\"missing\">Could not be read: "
                         f"{_escape(section.error)}</p>")
        if section.body.strip():
            parts.append(f"<pre>{_escape(section.body)}</pre>")
        parts.append("</div>")

    parts.append("</main>")
    parts.append(f"<footer>Written by {APP_NAME} {VERSION}. "
                 f"Nothing on this page was changed on the computer &mdash; "
                 f"every reading was taken without altering a setting."
                 f"</footer>")
    parts.append("</body>\n</html>")
    return "\n".join(parts)


def write_report(backup_dir: str, snapshot: SysSnapshot, computer: str = "",
                 backup_note: str = "") -> str:
    """Write the report to the root of the backup and return its path."""
    path = os.path.join(backup_dir, REPORT_FILENAME)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(build_html(snapshot, computer=computer,
                                backup_note=backup_note))
    return path
