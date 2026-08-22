#!/usr/bin/env python3
"""Inline the embedded assets into the card artboards.

Replaces the @@FONT_*@@, @@QR_PATH@@ and @@QR_VB@@ placeholders in
Main.dc.html / Back.dc.html with base64 woff2 fonts (latin subsets,
OFL-licensed Google Fonts from the site's own font stack) and the vCard
QR module path + viewBox size from make_qr.py. Idempotent: files already
built are left untouched.
"""
import base64
import pathlib

HERE = pathlib.Path(__file__).parent

def b64(path):
    return base64.b64encode((HERE / path).read_bytes()).decode()

qr_size, qr_path = (HERE / "qr/qr_path.txt").read_text().splitlines()[:2]

subs = {
    "@@FONT_ROBOTO@@": b64("fonts/roboto400.woff2"),
    "@@FONT_ROBOTO_I@@": b64("fonts/roboto900i.woff2"),
    "@@FONT_RMONO@@": b64("fonts/rmono400.woff2"),
    "@@QR_VB@@": str(int(qr_size) + 8),  # modules + 4-module quiet zone per side
    "@@QR_PATH@@": qr_path,
}

for name in ("Main.dc.html", "Back.dc.html", "SteelFront.dc.html", "SteelBack.dc.html"):
    p = HERE / name
    text = p.read_text()
    hits = [k for k in subs if k in text]
    for k in hits:
        text = text.replace(k, subs[k])
    if hits:
        p.write_text(text)
    print(f"{name}: replaced {len(hits)} placeholder(s), {len(text)} bytes")
