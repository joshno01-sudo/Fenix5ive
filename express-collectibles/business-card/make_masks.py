#!/usr/bin/env python3
"""Generate 1-bit laser-engraving masks from the steel artboards.

Derives engrave/front-engrave-mask.png and engrave/back-engrave-mask.png
from SteelFront.dc.html / SteelBack.dc.html: mockup-only layers (brushed
texture, sheen — marked data-mock) are stripped, steel color maps to white
(skip) and silver marks map to black (engrave), then each face renders at
600 dpi and is thresholded to pure 1-bit. Import into xTool Creative Space
at 86 x 54 mm; black pixels engrave (the QR plate engraves to silver and
its modules stay black steel, so scanners read it with normal polarity).
"""
import pathlib
import re
from PIL import Image
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
OUT = HERE / "engrave"
OUT.mkdir(exist_ok=True)

COLOR_MAP = {
    "#121417": "#ffffff",              # steel -> untouched (white = skip)
    "#d6d9dd": "#000000",              # bright silver -> engrave
    "#9ba1a9": "#000000",              # muted silver -> engrave
    "rgba(214,217,221,0.30)": "#000000",  # grid lines -> engrave
}

DPI = 600
SCALE = DPI / 96          # artboards are authored at 96 px/in
W, H = 325, 204           # 86 x 54 mm at 96 px/in

def make_mask_html(src):
    text = (HERE / src).read_text()
    text = "\n".join(l for l in text.splitlines() if 'data-mock="1"' not in l)
    for k, v in COLOR_MAP.items():
        text = text.replace(k, v)
    # square the card corners: the physical blank's radius is the cutter's job
    text = re.sub(r"border-radius: 10px;", "border-radius: 0;", text, count=0)
    return text

jobs = [("SteelFront.dc.html", "front-engrave-mask.png"),
        ("SteelBack.dc.html", "back-engrave-mask.png")]

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium",
                                args=["--no-sandbox", "--force-color-profile=srgb"])
    for src, out in jobs:
        tmp = OUT / f"_mask_{src}"
        tmp.write_text(make_mask_html(src))
        ctx = browser.new_context(viewport={"width": W, "height": H},
                                  device_scale_factor=SCALE)
        page = ctx.new_page()
        page.goto(tmp.as_uri())
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(900)
        page.screenshot(path=str(OUT / f"_raw_{out}"))
        ctx.close()
        tmp.unlink()

        im = Image.open(OUT / f"_raw_{out}").convert("L")
        im = im.crop((0, 0, round(W * SCALE), round(H * SCALE)))
        mask = im.point(lambda v: 0 if v < 128 else 255, mode="L").convert("1")
        mask.save(OUT / out, dpi=(DPI, DPI))
        (OUT / f"_raw_{out}").unlink()
        print(out, mask.size, f"{mask.size[0]/DPI*25.4:.1f}x{mask.size[1]/DPI*25.4:.1f} mm")
    browser.close()
