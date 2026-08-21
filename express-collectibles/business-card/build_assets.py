#!/usr/bin/env python3
"""Inline the embedded assets into the card artboards.

Replaces the @@FONT_*@@ and @@QR_PATH@@ placeholders in Main.dc.html /
Back.dc.html with base64 woff2 fonts (latin subsets, OFL-licensed Google
Fonts) and the vCard QR module path from make_qr.py. Idempotent: files
already built are left untouched.
"""
import base64
import pathlib

HERE = pathlib.Path(__file__).parent

def b64(path):
    return base64.b64encode((HERE / path).read_bytes()).decode()

subs = {
    "@@FONT_PS2P@@": b64("fonts/ps2p.woff2"),
    "@@FONT_PLEX4@@": b64("fonts/plex400.woff2"),
    "@@FONT_PLEX6@@": b64("fonts/plex600.woff2"),
    "@@QR_PATH@@": (HERE / "qr/qr_path.txt").read_text().splitlines()[1],
}

for name in ("Main.dc.html", "Back.dc.html"):
    p = HERE / name
    text = p.read_text()
    hits = [k for k in subs if k in text]
    for k in hits:
        text = text.replace(k, subs[k])
    if hits:
        p.write_text(text)
    print(f"{name}: replaced {len(hits)} placeholder(s), {len(text)} bytes")
