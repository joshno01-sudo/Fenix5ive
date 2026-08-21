#!/usr/bin/env python3
"""Generate laser-engraving masks from the steel artboards.

Two flavors per face, derived from SteelFront.dc.html / SteelBack.dc.html:

  engrave/{front,back}-engrave-shaded.png   8-bit grayscale, 600 dpi. Keeps
      the depth layers (echo shadows, halos, grid horizon fade) as mid-gray
      tones — engrave with xTool Creative Space's grayscale/dither mode so
      grays become fine dot patterns (dimmer silver). RECOMMENDED.
  engrave/{front,back}-engrave-mask.png     1-bit line art (shading layers
      stripped) for plain black/white engrave mode.

Both are exactly 86 x 54 mm; BLACK = ENGRAVE. Mockup-only layers (brushed
texture, sheen — data-mock) never engrave. The QR plate engraves to silver
with modules left black steel, so scanners read normal polarity.
"""
import pathlib
from PIL import Image
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
OUT = HERE / "engrave"
OUT.mkdir(exist_ok=True)

# Ordered: the grid's exact rgba string goes solid black BEFORE the generic
# silver-rgba prefix turns the shading layers into translucent black.
COLOR_MAP = [
    ("rgba(214,217,221,0.30)", "#000000"),   # grid lines -> full engrave
    ("rgba(214,217,221,", "rgba(0,0,0,"),    # shading silvers -> gray density
    ("#d6d9dd", "#000000"),                  # bright silver -> engrave
    ("#9ba1a9", "#000000"),                  # muted silver -> engrave
    ("#121417", "#ffffff"),                  # steel -> untouched (skip)
]

DPI = 600
SCALE = DPI / 96          # artboards are authored at 96 px/in
W, H = 325, 204           # 86 x 54 mm at 96 px/in

def make_mask_html(src, strip_shading):
    lines = (HERE / src).read_text().splitlines()
    lines = [l for l in lines if 'data-mock="1"' not in l
             and not (strip_shading and 'data-shade="1"' in l)]
    text = "\n".join(lines)
    for k, v in COLOR_MAP:
        text = text.replace(k, v)
    # square the card corners: the physical blank's radius is the cutter's job
    text = text.replace("border-radius: 10px;", "border-radius: 0;")
    return text

def snap(v):
    # keep shading mid-tones; snap near-black/near-white so text edges and
    # background stay clean instead of dithering as noise
    if v < 60:
        return 0
    if v > 235:
        return 255
    return v

jobs = [("SteelFront.dc.html", "front"), ("SteelBack.dc.html", "back")]

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium",
                                args=["--no-sandbox", "--force-color-profile=srgb"])
    for src, face in jobs:
        for strip_shading, suffix in ((False, "engrave-shaded"), (True, "engrave-mask")):
            tmp = OUT / f"_mask_{src}"
            tmp.write_text(make_mask_html(src, strip_shading))
            ctx = browser.new_context(viewport={"width": W, "height": H},
                                      device_scale_factor=SCALE)
            page = ctx.new_page()
            page.goto(tmp.as_uri())
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(900)
            raw = OUT / f"_raw_{face}.png"
            page.screenshot(path=str(raw))
            ctx.close()
            tmp.unlink()

            im = Image.open(raw).convert("L")
            im = im.crop((0, 0, round(W * SCALE), round(H * SCALE)))
            if strip_shading:
                out = im.point(lambda v: 0 if v < 128 else 255, mode="L").convert("1")
            else:
                out = im.point(snap, mode="L")
            out.save(OUT / f"{face}-{suffix}.png", dpi=(DPI, DPI))
            raw.unlink()
            print(f"{face}-{suffix}.png", out.mode, out.size,
                  f"{out.size[0]/DPI*25.4:.1f}x{out.size[1]/DPI*25.4:.1f} mm")
    browser.close()
