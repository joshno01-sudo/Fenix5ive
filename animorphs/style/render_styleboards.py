#!/usr/bin/env python3
"""Style-board generator for the Animorphs fan adaptation.

Draws the same six kids (Jake, Rachel, Marco, Cassie, Tobias, Ax) in two
animation treatments so they can be compared side by side:

  * "Dark Deco"  - the Bruce Timm / Batman & Superman Adventures look:
                   angular unbroken outlines, small eyes, one flat shadow
                   tone, few colours, backgrounds painted light-on-black.
  * "Grounded"   - the Young Justice (Phil Bourassa) look: realistic teen
                   proportions, finer line, irises and highlights, two
                   shading tones, layered real-world clothing.

Plus a "first episode" scene (the construction site), an alien model sheet
(Andalite + Hork-Bajir) and a title card, all in the Dark Deco treatment.

Usage:
    python3 render_styleboards.py            # writes renders/*.svg

Rasterize with the bundled chromium (see README.md):
    chromium --headless --no-sandbox --hide-scrollbars \
        --window-size=1600,900 --force-device-scale-factor=2 \
        --screenshot=renders/01-lineup-dark-deco.png renders/01-lineup-dark-deco.svg

No dependencies beyond Python 3; fonts are read from ./fonts and embedded.
"""
import base64
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "renders")
FONT_DIR = os.path.join(HERE, "fonts")

W, H = 1600, 900

# ------------------------------------------------------------------ fonts

FONTS = {
    "Limelight": "Limelight.woff2",
    "Oswald": "Oswald.woff2",
    "Big Shoulders Display": "BigShouldersDisplay.woff2",
}


def font_css():
    rules = []
    for family, fname in FONTS.items():
        p = os.path.join(FONT_DIR, fname)
        if not os.path.isfile(p):
            continue
        with open(p, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        rules.append(
            f"@font-face{{font-family:'{family}';"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}"
        )
    return "\n".join(rules)


# ------------------------------------------------------------- primitives

def f1(v):
    return f"{v:.1f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def pts_str(pts):
    return " ".join(f"{f1(x)},{f1(y)}" for x, y in pts)


def attrs(fill=None, stroke=None, sw=None, extra=""):
    a = []
    a.append(f'fill="{fill}"' if fill is not None else 'fill="none"')
    if stroke is not None:
        a.append(f'stroke="{stroke}"')
        a.append('stroke-linejoin="round" stroke-linecap="round"')
    if sw is not None:
        a.append(f'stroke-width="{f1(sw)}"')
    if extra:
        a.append(extra)
    return " ".join(a)


def poly(pts, fill=None, stroke=None, sw=None, extra=""):
    return f'<polygon points="{pts_str(pts)}" {attrs(fill, stroke, sw, extra)}/>'


def pline(pts, stroke, sw, extra=""):
    return f'<polyline points="{pts_str(pts)}" {attrs(None, stroke, sw, extra)}/>'


def path(d, fill=None, stroke=None, sw=None, extra=""):
    return f'<path d="{d}" {attrs(fill, stroke, sw, extra)}/>'


def circle(cx, cy, r, fill=None, stroke=None, sw=None, extra=""):
    return (f'<circle cx="{f1(cx)}" cy="{f1(cy)}" r="{f1(r)}" '
            f'{attrs(fill, stroke, sw, extra)}/>')


def ellipse(cx, cy, rx, ry, fill=None, stroke=None, sw=None, extra=""):
    return (f'<ellipse cx="{f1(cx)}" cy="{f1(cy)}" rx="{f1(rx)}" ry="{f1(ry)}" '
            f'{attrs(fill, stroke, sw, extra)}/>')


def rect(x, y, w, h, fill=None, stroke=None, sw=None, extra=""):
    return (f'<rect x="{f1(x)}" y="{f1(y)}" width="{f1(w)}" height="{f1(h)}" '
            f'{attrs(fill, stroke, sw, extra)}/>')


def text(x, y, s, size, fill, family="Oswald", weight=500, anchor="middle",
         extra=""):
    s = (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return (f'<text x="{f1(x)}" y="{f1(y)}" font-family="{family}, sans-serif" '
            f'font-size="{f1(size)}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{anchor}" {extra}>{s}</text>')


def smooth(pts, closed=False, tension=1.0):
    """Catmull-Rom spline through pts as a cubic bezier path string."""
    if len(pts) < 3:
        return "M " + " L ".join(f"{f1(x)},{f1(y)}" for x, y in pts)
    if closed:
        p = [pts[-1]] + list(pts) + [pts[0], pts[1]]
    else:
        p = [pts[0]] + list(pts) + [pts[-1]]
    d = f"M {f1(p[1][0])},{f1(p[1][1])} "
    k = tension / 6.0
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) * k, p1[1] + (p2[1] - p0[1]) * k)
        c2 = (p2[0] - (p3[0] - p1[0]) * k, p2[1] - (p3[1] - p1[1]) * k)
        d += (f"C {f1(c1[0])},{f1(c1[1])} {f1(c2[0])},{f1(c2[1])} "
              f"{f1(p2[0])},{f1(p2[1])} ")
    if closed:
        d += "Z"
    return d


def mirror(pts):
    return [(-x, y) for x, y in pts]


def sym(right_half):
    """Closed symmetric outline from a top-to-bottom right-hand half.

    right_half runs from the top centre (x may be 0) down to the bottom
    centre; the left side is the mirror, walked back up.
    """
    return list(right_half) + [(-x, y) for x, y in reversed(right_half)]


def shape(pts, mode, fill=None, stroke=None, sw=None, extra="", closed=True):
    """Polygon in 'dcau' (angular) mode, smoothed spline in 'yj' mode."""
    if mode == "dcau":
        if closed:
            return poly(pts, fill, stroke, sw, extra)
        return pline(pts, stroke, sw, extra)
    return path(smooth(pts, closed=closed, tension=0.85), fill, stroke, sw, extra)


def group(inner, transform="", extra=""):
    t = f' transform="{transform}"' if transform else ""
    return f"<g{t} {extra}>\n" + "\n".join(inner) + "\n</g>"


def svg_doc(body, bg, w=W, h=H):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}">\n<style>{font_css()}</style>\n'
            f'<rect width="{w}" height="{h}" fill="{bg}"/>\n' + body + "\n</svg>\n")


# --------------------------------------------------------------- palettes

# Two treatments. Line weights are in "head units" (head = 100 tall).
STYLES = {
    "dcau": dict(line="#0a0a0d", lw=3.4, thin=2.4, tones=1, eye="timm"),
    "yj": dict(line="#1c1519", lw=1.9, thin=1.3, tones=2, eye="iris"),
}


def shade(hexcol, k):
    """Darken (k<1) or lighten (k>1) a hex colour."""
    h = hexcol.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    if k <= 1:
        r, g, b = int(r * k), int(g * k), int(b * k)
    else:
        r = int(r + (255 - r) * (k - 1))
        g = int(g + (255 - g) * (k - 1))
        b = int(b + (255 - b) * (k - 1))
    return "#%02x%02x%02x" % (min(r, 255), min(g, 255), min(b, 255))


# -------------------------------------------------------------- characters
#
# Head coordinate system: head is 100 units tall, top of skull at y=0,
# chin at y=100, centred on x=0. Busts extend to about y=190.

CHARS = [
    dict(key="jake", name="JAKE", tag="the reluctant leader", g="m",
         skin="#efc39a", hair="#6a4326", hair_hi="#8d5f3a", eyes="#5a3b22",
         cloth="#3d6795", cloth2="#9aa3ad", outfit="tee",
         brow="flat", mouth="flat"),
    dict(key="rachel", name="RACHEL", tag="Xena, warrior princess", g="f",
         skin="#f5d3b6", hair="#e6c46a", hair_hi="#f4dc98", eyes="#3f78b5",
         cloth="#7a3d7c", cloth2="#4c6a94", outfit="jacket",
         brow="arch", mouth="smirk"),
    dict(key="marco", name="MARCO", tag="the wise guy", g="m",
         skin="#d9ad80", hair="#221a19", hair_hi="#3d3231", eyes="#3a2418",
         cloth="#556b52", cloth2="#2f3d2e", outfit="hoodie",
         brow="raised", mouth="grin"),
    dict(key="cassie", name="CASSIE", tag="the heart", g="f",
         skin="#8a5a3c", hair="#1c1412", hair_hi="#33261f", eyes="#2c1a10",
         cloth="#e3bd4e", cloth2="#4a6a96", outfit="overalls",
         brow="soft", mouth="smile"),
    dict(key="tobias", name="TOBIAS", tag="the outsider", g="m",
         skin="#edd0b4", hair="#c6a463", hair_hi="#dcc088", eyes="#6b7a49",
         cloth="#8b3a33", cloth2="#9a9793", outfit="flannel",
         brow="worried", mouth="flat"),
    dict(key="ax", name="AX", tag="Aximili, in human morph", g="m",
         skin="#c79c73", hair="#7d5a34", hair_hi="#b58a4e", eyes="#5a4020",
         cloth="#e8e3d8", cloth2="#b9b1a3", outfit="tee",
         brow="curious", mouth="open"),
]


def face_outline(g, mode):
    if g == "m":
        half = [(0, 0), (17, 1), (30, 6), (38, 16), (42, 30), (42, 46),
                (39, 62), (32, 80), (17, 96), (9, 100), (0, 100)]
    else:
        half = [(0, 0), (15, 1), (27, 6), (34, 16), (37, 30), (36, 47),
                (33, 63), (26, 81), (12, 97), (5, 100.5), (0, 101)]
    pts = sym(half)
    if mode == "dcau":
        return pts
    # a softer, less lantern-jawed head for the grounded treatment
    return [(x * 0.98, y) for x, y in pts]


def face_shadow(g, mode):
    """Right-hand cel shadow: temple, cheek, jaw and under the chin."""
    if g == "m":
        pts = [(24, 30), (42, 30), (42, 46), (39, 62), (32, 80), (17, 96),
               (9, 100), (-9, 100), (-9, 97), (10, 92), (24, 74), (28, 56)]
    else:
        pts = [(22, 32), (37, 30), (36, 47), (33, 63), (26, 81), (12, 97),
               (5, 100.5), (-5, 100.5), (-3, 97), (8, 92), (20, 74), (24, 56)]
    return pts


def draw_eyes(c, st, mode):
    g = c["g"]
    ex, ey = (17, 48) if g == "m" else (16, 47)
    out = []
    for sgn in (-1, 1):
        x = sgn * ex
        if st["eye"] == "timm":
            wdt, hgt = (7, 4) if g == "m" else (7.5, 5)
            white = [(x - wdt, ey - 1), (x - wdt * 0.55, ey - hgt),
                     (x + wdt * 0.55, ey - hgt), (x + wdt, ey - 1),
                     (x + wdt * 0.55, ey + hgt * 0.7), (x - wdt * 0.55, ey + hgt * 0.7)]
            out.append(poly(white, "#f5f2ee", st["line"], st["thin"]))
            px = x + 1.2 * sgn
            out.append(circle(px, ey - 0.5, 2.6 if g == "m" else 2.9, st["line"]))
            # heavy upper lid line, the Timm signature
            out.append(pline([(x - wdt, ey - 1), (x - wdt * 0.55, ey - hgt),
                              (x + wdt * 0.55, ey - hgt), (x + wdt, ey - 1)],
                             st["line"], st["lw"]))
            if g == "f":
                out.append(pline([(x + wdt * sgn, ey - 1), (x + (wdt + 3.5) * sgn, ey - 3.5)],
                                 st["line"], st["lw"]))
        else:
            wdt, hgt = (8, 5) if g == "m" else (8.5, 5.8)
            eye_pts = [(x - wdt, ey), (x - wdt * 0.5, ey - hgt), (x + wdt * 0.5, ey - hgt * 0.95),
                       (x + wdt, ey - 0.5), (x + wdt * 0.5, ey + hgt * 0.75),
                       (x - wdt * 0.5, ey + hgt * 0.75)]
            out.append(path(smooth(eye_pts, True, 0.9), "#f7f4f0", st["line"], st["thin"]))
            ix = x + 0.8 * sgn
            out.append(f'<clipPath id="eye{c["key"]}{mode}{sgn+1}">'
                       f'<path d="{smooth(eye_pts, True, 0.9)}"/></clipPath>')
            clip = f'clip-path="url(#eye{c["key"]}{mode}{sgn+1})"'
            out.append(circle(ix, ey, 3.9, c["eyes"], st["line"], 0.8, clip))
            out.append(circle(ix, ey, 1.9, st["line"], extra=clip))
            out.append(circle(ix - 1.3, ey - 1.4, 0.9, "#ffffff", extra=clip))
            # lid line, lash flick for the girls
            out.append(path(smooth([(x - wdt, ey), (x - wdt * 0.5, ey - hgt),
                                    (x + wdt * 0.5, ey - hgt * 0.95), (x + wdt, ey - 0.5)],
                                   False, 0.9), None, st["line"], st["lw"] * 1.05))
            if g == "f":
                out.append(pline([(x + wdt * sgn, ey - 0.5), (x + (wdt + 3) * sgn, ey - 3)],
                                 st["line"], st["lw"]))
                out.append(path(smooth([(x - wdt * 0.5, ey + hgt * 0.75), (x + wdt * 0.5, ey + hgt * 0.75)],
                                       False), None, st["line"], st["thin"] * 0.8))
    return out


def draw_brows(c, st, mode):
    g = c["g"]
    ex, by = (17, 38) if g == "m" else (16, 37.5)
    kind = c["brow"]
    out = []
    thick = 3.2 if g == "m" else 2.2
    for sgn in (-1, 1):
        x = sgn * ex
        inner, outer = x - 9 * sgn, x + 9 * sgn
        yi, yo = by, by
        if kind == "flat":
            yi, yo = by - 0.5, by - 1
        elif kind == "arch":
            yi, yo = by + 1.5, by - 1.5
        elif kind == "raised":
            # one brow up (Marco's permanent scepticism)
            yi, yo = (by - 1, by - 2) if sgn == 1 else (by + 2.5, by - 0.5)
            if sgn == 1:
                yi, yo = by - 5, by - 2.5
        elif kind == "soft":
            yi, yo = by + 0.5, by - 2
        elif kind == "worried":
            yi, yo = by - 3.5, by + 0.5
        elif kind == "curious":
            yi, yo = by - 3, by - 3
        mid = ((inner + outer) / 2, min(yi, yo) - 1.5)
        top = [(inner, yi), mid, (outer, yo)]
        bottom = [(outer, yo + thick * 0.6), (mid[0], mid[1] + thick), (inner, yi + thick * 0.8)]
        pts = top + bottom
        if mode == "dcau":
            out.append(poly(pts, st["line"]))
        else:
            out.append(path(smooth(pts, True, 0.7), c["hair"] if c["hair"] != "#e6c46a" else "#a77f2e",
                            st["line"], 0.7))
    return out


def draw_nose(c, st, mode):
    g = c["g"]
    if st["eye"] == "timm":
        # the single-stroke Timm nose: bridge line down, tiny hook
        if g == "m":
            return [pline([(2, 54), (6, 66), (1, 69)], st["line"], st["lw"])]
        return [pline([(1.5, 56), (4.5, 65), (0.5, 67.5)], st["line"], st["lw"] * 0.9)]
    out = [path(smooth([(2, 52), (4, 60), (5.5, 66), (1.5, 69)], False), None,
                st["line"], st["lw"])]
    out.append(path(smooth([(-6, 66.5), (-4, 69), (-1, 69.5)], False), None,
                    st["line"], st["thin"]))
    out.append(path(smooth([(3.5, 67), (6.5, 68), (7.5, 65.5)], False), None,
                    st["line"], st["thin"]))
    return out


def draw_mouth(c, st, mode):
    kind = c["mouth"]
    y = 81 if c["g"] == "m" else 80
    out = []
    if kind == "flat":
        pts = [(-7, y), (0, y + 0.5), (7, y)]
    elif kind == "smirk":
        pts = [(-7, y + 1), (0, y + 0.5), (8, y - 2.5)]
    elif kind == "grin":
        pts = [(-9, y - 2.5), (0, y + 2), (9, y - 3)]
    elif kind == "smile":
        pts = [(-7, y - 1), (0, y + 1.5), (7, y - 1)]
    elif kind == "open":
        pts = [(-6, y - 1), (0, y), (6, y - 1)]
    else:
        pts = [(-7, y), (7, y)]
    lw = st["lw"] if mode == "dcau" else st["lw"] * 0.95
    out.append(path(smooth(pts, False), None, st["line"], lw))
    if kind in ("grin",):
        # teeth
        out.append(path(smooth([(-8, y - 2), (0, y + 1.5), (8, y - 2.5)], False) +
                        " L 8,%s L -8,%s Z" % (f1(y - 2.5), f1(y - 2)), "#f5f2ee", st["line"], st["thin"]))
        out.append(path(smooth(pts, False), None, st["line"], lw))
    if kind == "open":
        out.append(path("M -5,%s Q 0,%s 5,%s Z" % (f1(y - 0.5), f1(y + 7), f1(y - 0.5)),
                        "#3a1b1d", st["line"], st["thin"]))
    if mode == "yj":
        # lower lip shadow line
        out.append(path(smooth([(-4.5, y + 5), (0, y + 6), (4.5, y + 5)], False), None,
                        st["line"], st["thin"] * 0.9))
    return out


def draw_ears(c, st, mode):
    out = []
    g = c["g"]
    x0 = 42 if g == "m" else 36
    for sgn in (-1, 1):
        pts = [(sgn * (x0 - 2), 46), (sgn * (x0 + 5), 44), (sgn * (x0 + 7), 52),
               (sgn * (x0 + 4), 62), (sgn * (x0 - 1), 64)]
        out.append(shape(pts, mode, c["skin"], st["line"], st["lw"]))
        out.append(shape([(sgn * (x0 + 3), 49), (sgn * (x0 + 4), 55), (sgn * (x0 + 1), 59)],
                         mode, None, st["line"], st["thin"], closed=False))
    return out


# ------------------------------------------------------------------- hair

def hair_jake(c, st, mode):
    hi = c["hair_hi"]
    front = [(-44, 34), (-42, 14), (-32, 2), (-12, -5), (12, -8), (34, -3), (46, 6),
             (56, 12), (48, 22), (44, 34), (40, 28), (32, 20), (24, 26), (14, 18), (4, 24),
             (-6, 18), (-16, 26), (-26, 20), (-34, 28), (-40, 36)]
    out = [shape(front, mode, c["hair"], st["line"], st["lw"])]
    if mode == "dcau":
        out.append(poly([(-8, 4), (10, -2), (34, 0), (24, 8), (4, 10)], hi))
    else:
        out.append(path(smooth([(-10, 6), (8, -1), (30, 1), (22, 7), (2, 11)], True), hi))
        for s in ([(-30, 4), (-20, 14)], [(0, -4), (8, 8)], [(28, -1), (36, 14)], [(44, 10), (50, 18)]):
            out.append(path(smooth(s, False), None, shade(c["hair"], 0.6), st["thin"]))
    return [], out


def hair_rachel(c, st, mode):
    back = [(-48, 26), (-42, 0), (-22, -12), (0, -14), (22, -12), (42, 0), (48, 26),
            (54, 80), (62, 140), (66, 190), (-66, 190), (-62, 140), (-54, 80)]
    left = [(-40, 8), (-24, -8), (-2, -12), (-2, -2), (-12, 12), (-24, 34), (-34, 62),
            (-46, 74), (-44, 44), (-44, 28)]
    right = [(2, -12), (24, -9), (40, 4), (46, 26), (46, 46), (48, 78), (34, 66), (28, 50),
             (22, 30), (10, 8), (2, -1)]
    outb = [shape(back, mode, c["hair"], st["line"], st["lw"])]
    if mode == "yj":
        outb.append(path(smooth([(-50, 60), (-56, 120), (-58, 190), (-36, 190), (-40, 120), (-38, 62)], True),
                         shade(c["hair"], 0.8)))
        outb.append(path(smooth([(50, 60), (56, 120), (58, 190), (36, 190), (40, 120), (38, 62)], True),
                         shade(c["hair"], 0.8)))
    outf = [shape(left, mode, c["hair"], st["line"], st["lw"]),
            shape(right, mode, c["hair"], st["line"], st["lw"])]
    hi = c["hair_hi"]
    if mode == "dcau":
        outf.append(poly([(-30, -4), (-8, -10), (-10, 0), (-24, 12), (-34, 30)], hi))
        outf.append(poly([(8, -8), (26, -5), (34, 8), (22, 4), (12, -2)], hi))
    else:
        outf.append(path(smooth([(-30, -4), (-8, -10), (-10, 0), (-24, 12), (-34, 30)], True), hi))
        outf.append(path(smooth([(8, -8), (26, -5), (34, 8), (22, 4), (12, -2)], True), hi))
        for s in ([(-40, 20), (-42, 60)], [(-20, 4), (-30, 40)], [(30, 6), (40, 40)], [(52, 90), (58, 160)],
                  [(-52, 90), (-58, 160)]):
            outf.append(path(smooth(s, False), None, shade(c["hair"], 0.65), st["thin"]))
    return outb, outf


def hair_marco(c, st, mode):
    back = [(-50, 30), (-44, 0), (-22, -12), (0, -14), (22, -12), (44, 0), (50, 30),
            (52, 72), (48, 104), (36, 108), (-36, 108), (-48, 104), (-52, 72)]
    front = [(-46, 44), (-44, 6), (-24, -9), (0, -12), (24, -9), (44, 6), (46, 44),
             (40, 30), (32, 40), (24, 26), (14, 38), (4, 26), (-6, 38), (-16, 26),
             (-26, 40), (-36, 30)]
    outb = [shape(back, mode, c["hair"], st["line"], st["lw"])]
    outf = [shape(front, mode, c["hair"], st["line"], st["lw"])]
    hi = c["hair_hi"]
    if mode == "dcau":
        outf.append(poly([(-20, -2), (0, -8), (22, -4), (12, 4), (-8, 6)], hi))
    else:
        outf.append(path(smooth([(-20, -2), (0, -8), (22, -4), (12, 4), (-8, 6)], True), hi))
        for s in ([(-36, 10), (-40, 40)], [(-10, -4), (-14, 26)], [(16, -4), (22, 24)], [(36, 12), (42, 40)],
                  [(46, 60), (44, 100)], [(-46, 60), (-44, 100)]):
            outf.append(path(smooth(s, False), None, shade(c["hair"], 1.4), st["thin"]))
    return outb, outf


def hair_cassie(c, st, mode):
    cap = [(-40, 40), (-40, 12), (-30, -1), (-12, -8), (10, -9), (30, -3), (40, 12), (40, 40),
           (37, 28), (28, 17), (14, 13), (0, 12), (-14, 13), (-28, 17), (-37, 28)]
    out = [shape(cap, mode, c["hair"], st["line"], st["lw"])]
    hi = c["hair_hi"]
    if mode == "dcau":
        out.append(poly([(-14, 0), (6, -5), (26, 0), (16, 5), (-2, 5)], hi))
    else:
        out.append(path(smooth([(-14, 0), (6, -5), (26, 0), (16, 5), (-2, 5)], True), hi))
        # tight-crop texture: short scallops along the crown
        for x in range(-30, 31, 10):
            out.append(path(smooth([(x - 4, 4 + abs(x) * 0.15), (x, 1 + abs(x) * 0.15), (x + 4, 4 + abs(x) * 0.15)],
                                   False), None, shade(c["hair"], 1.6), st["thin"] * 0.8))
    return [], out


def hair_tobias(c, st, mode):
    front = [(-46, 44), (-44, 8), (-26, -7), (0, -11), (26, -7), (44, 8), (48, 42), (50, 60),
             (44, 54), (40, 36), (36, 46), (28, 30), (24, 46), (16, 32), (8, 46), (0, 30),
             (-8, 44), (-16, 30), (-24, 46), (-30, 32), (-38, 46), (-44, 56), (-48, 60)]
    out = [shape(front, mode, c["hair"], st["line"], st["lw"])]
    hi = c["hair_hi"]
    if mode == "dcau":
        out.append(poly([(-24, 2), (-4, -6), (18, -3), (10, 6), (-10, 8)], hi))
    else:
        out.append(path(smooth([(-24, 2), (-4, -6), (18, -3), (10, 6), (-10, 8)], True), hi))
        for s in ([(-34, 6), (-40, 40)], [(-14, -6), (-18, 30)], [(6, -8), (10, 30)], [(30, 0), (38, 34)]):
            out.append(path(smooth(s, False), None, shade(c["hair"], 0.7), st["thin"]))
    return [], out


def hair_ax(c, st, mode):
    """Medium length with loose curls: a scalloped silhouette built from arcs
    (the Timm way to say 'curly' with one unbroken line)."""
    import math as _m
    cx, cy = 0, 30
    d = ""
    angs = [190 - 14 * k for k in range(14)]  # 190 .. 8 degrees, over the top
    first = True
    for i in range(len(angs) - 1):
        a0, a1 = _m.radians(angs[i]), _m.radians(angs[i + 1])
        r0, r1 = 47, 47
        am = (a0 + a1) / 2
        rm = 56
        x0, y0 = cx + r0 * _m.cos(a0), cy - r0 * _m.sin(a0) * 1.1
        xm, ym = cx + rm * _m.cos(am), cy - rm * _m.sin(am) * 1.1
        x1, y1 = cx + r1 * _m.cos(a1), cy - r1 * _m.sin(a1) * 1.1
        if first:
            d += f"M {f1(x0)},{f1(y0)} "
            first = False
        d += f"Q {f1(xm)},{f1(ym)} {f1(x1)},{f1(y1)} "
    # right side down past the ear, then the fringe back across the forehead
    d += "Q 56,42 50,58 L 44,52 L 42,36 L 32,24 L 20,32 L 8,20 L -2,32 L -12,20 L -24,32 L -34,24 "
    d += "L -42,36 L -44,52 L -50,58 Q -56,42 -47,26 Z"
    out = [path(d, c["hair"], st["line"], st["lw"])]
    hi = c["hair_hi"]
    if mode == "dcau":
        out.append(poly([(-20, -6), (2, -12), (24, -7), (14, 2), (-6, 4)], hi))
    else:
        out.append(path(smooth([(-20, -6), (2, -12), (24, -7), (14, 2), (-6, 4)], True), hi))
        for (x, y) in [(-40, 10), (-8, -8), (24, -4), (44, 28)]:
            out.append(path(f"M {x-4},{y} q 4,-6 8,0", None, shade(c["hair"], 0.6), st["thin"]))
    return [], out


HAIR = dict(jake=hair_jake, rachel=hair_rachel, marco=hair_marco, cassie=hair_cassie,
            tobias=hair_tobias, ax=hair_ax)


# ---------------------------------------------------------------- outfits

TORSO = [(-17, 116), (-30, 122), (-52, 130), (-84, 144), (-94, 200), (94, 200), (84, 144),
         (52, 130), (30, 122), (17, 116)]


def neck(c, st, mode):
    g = c["g"]
    w = 14 if g == "m" else 11
    pts = [(-w, 88), (w, 88), (w + 1, 122), (-w - 1, 122)]
    out = [poly(pts, c["skin"], st["line"], st["lw"])]
    out.append(poly([(w * 0.1, 96), (w, 92), (w + 1, 122), (-w * 0.3, 122)], shade(c["skin"], 0.78)))
    if mode == "yj":
        out.append(pline([(-w * 0.4, 100), (-w * 0.3, 118)], st["line"], st["thin"]))
    return out


def outfit(c, st, mode):
    kind = c["outfit"]
    line, lw, thin = st["line"], st["lw"], st["thin"]
    col, col2 = c["cloth"], c["cloth2"]
    dark = shade(col, 0.72)
    out = []
    torso = TORSO
    if kind == "hoodie":
        # hood bunched behind the neck
        hood = [(-30, 100), (-44, 108), (-52, 128), (-30, 124), (0, 122), (30, 124), (52, 128), (44, 108), (30, 100)]
        out.append(shape(hood, mode, dark, line, lw))
    out.append(shape(torso, mode, col, line, lw))
    out.append(shape([(20, 118), (52, 130), (84, 144), (94, 200), (40, 200), (34, 150)], mode, dark))
    if kind == "tee":
        collar = [(-20, 116), (-10, 124), (0, 127), (10, 124), (20, 116), (16, 113), (0, 121), (-16, 113)]
        out.append(shape(collar, mode, dark, line, lw))
    elif kind == "hoodie":
        # kangaroo pocket seam and drawstrings
        out.append(shape([(-22, 116), (0, 128), (22, 116)], mode, None, line, lw, closed=False))
        for sgn in (-1, 1):
            out.append(pline([(sgn * 10, 126), (sgn * 12, 170), (sgn * 15, 176)], line, thin))
            out.append(circle(sgn * 15, 178, 2.4, dark, line, thin))
        out.append(shape([(-60, 170), (60, 170)], mode, None, line, thin, closed=False))
    elif kind == "jacket":
        # fitted top with a cropped denim jacket over it
        out.append(shape([(-13, 116), (0, 128), (13, 116)], mode, None, line, lw, closed=False))
        for sgn in (-1, 1):
            lapel = [(sgn * 17, 114), (sgn * 30, 122), (sgn * 52, 130), (sgn * 84, 144), (sgn * 94, 200),
                     (sgn * 30, 200), (sgn * 20, 160), (sgn * 12, 136)]
            out.append(shape(lapel, mode, col2, line, lw))
            out.append(poly([(sgn * 17, 114), (sgn * 34, 120), (sgn * 28, 140), (sgn * 12, 136)],
                            shade(col2, 0.8), line, lw))
            if mode == "yj":
                out.append(pline([(sgn * 40, 150), (sgn * 36, 200)], shade(col2, 0.7), thin))
                out.append(pline([(sgn * 70, 140), (sgn * 82, 200)], shade(col2, 0.7), thin))
    elif kind == "overalls":
        # yellow tee under denim bib
        out.append(shape([(-20, 116), (-10, 124), (0, 127), (10, 124), (20, 116), (16, 113), (0, 121), (-16, 113)],
                         mode, dark, line, lw))
        bib = [(-30, 152), (30, 152), (32, 200), (-32, 200)]
        for sgn in (-1, 1):
            strap = [(sgn * 26, 152), (sgn * 30, 128), (sgn * 40, 128), (sgn * 34, 152)]
            out.append(shape(strap, mode, col2, line, lw))
        out.append(shape(bib, mode, col2, line, lw))
        out.append(poly([(8, 152), (30, 152), (32, 200), (12, 200)], shade(col2, 0.78)))
        for sgn in (-1, 1):
            out.append(circle(sgn * 24, 156, 3.4, "#c9b46a", line, thin))
        out.append(shape([(-18, 168), (18, 168), (18, 192), (-18, 192)], mode, None, line, thin))
    elif kind == "flannel":
        # grey tee under an open flannel
        out.append(shape([(-16, 116), (0, 126), (16, 116)], mode, None, line, lw, closed=False))
        for sgn in (-1, 1):
            panel = [(sgn * 19, 114), (sgn * 30, 122), (sgn * 52, 130), (sgn * 84, 144), (sgn * 94, 200),
                     (sgn * 34, 200), (sgn * 26, 160), (sgn * 20, 130)]
            pid = f"fl{c['key']}{mode}{sgn+1}"
            out.append(f'<clipPath id="{pid}">{shape(panel, mode, "#000")}</clipPath>')
            out.append(shape(panel, mode, col, line, lw))
            grid = []
            for x in range(-100, 101, 16):
                grid.append(rect(x, 100, 5, 110, shade(col, 0.72)))
            for y in range(104, 210, 18):
                grid.append(rect(-100, y, 200, 5, shade(col, 0.72)))
            out.append(group(grid, extra=f'clip-path="url(#{pid})" opacity="0.9"'))
            out.append(shape(panel, mode, None, line, lw))
        # tee showing between panels
        out.append(shape([(-19, 114), (-20, 130), (-26, 160), (-34, 200), (34, 200), (26, 160), (20, 130), (19, 114),
                          (10, 124), (0, 127), (-10, 124)], mode, col2, line, lw))
        for sgn in (-1, 1):
            panel = [(sgn * 19, 114), (sgn * 30, 122), (sgn * 52, 130), (sgn * 84, 144), (sgn * 94, 200),
                     (sgn * 34, 200), (sgn * 26, 160), (sgn * 20, 130)]
            out.append(shape(panel, mode, None, line, lw))
    if mode == "yj":
        # a couple of cloth folds
        out.append(path(smooth([(-60, 150), (-52, 176), (-56, 200)], False), None, line, thin))
        out.append(path(smooth([(58, 152), (66, 180), (62, 200)], False), None, line, thin))
    return out


# ------------------------------------------------------------------- bust

def bust(c, mode):
    st = STYLES[mode]
    g = c["g"]
    parts = []
    back_hair, front_hair = HAIR[c["key"]](c, st, mode)
    parts += back_hair
    parts += neck(c, st, mode)
    parts += outfit(c, st, mode)
    parts += draw_ears(c, st, mode)
    face = face_outline(g, mode)
    parts.append(shape(face, mode, c["skin"], st["line"], st["lw"]))
    parts.append(shape(face_shadow(g, mode), mode, shade(c["skin"], 0.8)))
    if st["tones"] >= 2:
        # highlight plane on the lit cheek / forehead
        parts.append(shape([(-30, 28), (-16, 22), (-8, 40), (-14, 58), (-26, 56), (-33, 42)], mode,
                           shade(c["skin"], 1.12)))
    if mode == "yj":
        # cheekbone and jaw contour lines
        parts.append(path(smooth([(-30, 62), (-26, 74), (-16, 86)], False), None, st["line"], st["thin"]))
    parts += draw_brows(c, st, mode)
    parts += draw_eyes(c, st, mode)
    parts += draw_nose(c, st, mode)
    parts += draw_mouth(c, st, mode)
    parts += front_hair
    # front hair sits under the outline of the face, so redraw the jaw line
    parts.append(shape(face, mode, None, st["line"], st["lw"]))
    return parts


# ---------------------------------------------------------- backgrounds

def deco_skyline(x0, x1, base_y, seed=3, col="#26324a", col2="#1a2436"):
    """Painted light-on-black towers, the Radomski background trick."""
    out = []
    import random
    rnd = random.Random(seed)
    x = x0
    while x < x1:
        w = rnd.choice([26, 34, 44, 58, 70])
        h = rnd.choice([80, 120, 160, 200, 240, 300])
        c = rnd.choice([col, col2])
        out.append(rect(x, base_y - h, w, h, c))
        # deco setbacks
        out.append(rect(x + w * 0.25, base_y - h - 18, w * 0.5, 18, c))
        out.append(rect(x + w * 0.4, base_y - h - 34, w * 0.2, 16, c))
        # a few lit windows
        for _ in range(rnd.randint(2, 6)):
            wx = x + rnd.uniform(3, max(4, w - 8))
            wy = base_y - rnd.uniform(10, h - 10)
            out.append(rect(wx, wy, 3, 5, rnd.choice(["#c9b26a", "#7f8fa8", "#e0d3a0"]), extra='opacity="0.85"'))
        x += w + rnd.choice([4, 8, 14])
    return out


def label_strip(title, subtitle, fg, sub_fg, family_title="Big Shoulders Display"):
    out = [text(60, 78, title, 56, fg, family_title, 900, "start", 'letter-spacing="2"')]
    out.append(text(60, 112, subtitle, 20, sub_fg, "Oswald", 500, "start", 'letter-spacing="3"'))
    return out


# ----------------------------------------------------------------- sheets

def sheet_lineup(mode):
    st = STYLES[mode]
    if mode == "dcau":
        bg = "#07070a"
        body = []
        # gradient haze along the horizon, light painted onto black
        body.append('<defs><linearGradient id="haze" x1="0" y1="0" x2="0" y2="1">'
                    '<stop offset="0" stop-color="#07070a" stop-opacity="0"/>'
                    '<stop offset="1" stop-color="#1c2740" stop-opacity="1"/></linearGradient>'
                    '<radialGradient id="moon" cx="0.5" cy="0.5" r="0.5">'
                    '<stop offset="0" stop-color="#e9e2c8"/><stop offset="1" stop-color="#b9b39a"/></radialGradient>'
                    '</defs>')
        body.append(rect(0, 400, W, 500, "url(#haze)"))
        body.append(circle(1130, 146, 36, "url(#moon)"))
        body += deco_skyline(0, W, 900, seed=7)
        body += label_strip("ANIMORPHS  /  CHARACTER LINEUP", "DARK DECO TREATMENT  -  BATMAN & SUPERMAN ADVENTURES REFERENCE",
                            "#e9e2c8", "#8f9bb3")
        name_fg, tag_fg = "#e9e2c8", "#8f9bb3"
        panel = "#0d0f16"
    else:
        bg = "#1b2331"
        body = []
        body.append('<defs><linearGradient id="dusk" x1="0" y1="0" x2="0" y2="1">'
                    '<stop offset="0" stop-color="#151b27"/><stop offset="0.55" stop-color="#2b3a4f"/>'
                    '<stop offset="1" stop-color="#5d5a52"/></linearGradient>'
                    '<linearGradient id="ground" x1="0" y1="0" x2="0" y2="1">'
                    '<stop offset="0" stop-color="#3a3630"/><stop offset="1" stop-color="#211f1c"/></linearGradient>'
                    '</defs>')
        body.append(rect(0, 0, W, H, "url(#dusk)"))
        body.append(rect(0, 760, W, 140, "url(#ground)"))
        # a low, believable suburban horizon: rooftops and power lines
        for i, (x, w, h) in enumerate([(0, 220, 70), (240, 180, 90), (440, 260, 60), (720, 200, 100),
                                        (940, 240, 70), (1200, 200, 110), (1420, 200, 80)]):
            body.append(poly([(x, 760), (x, 760 - h), (x + w * 0.5, 760 - h - 40), (x + w, 760 - h), (x + w, 760)],
                             "#2a2c33" if i % 2 else "#33363e"))
        body.append(path("M 0,690 Q 400,720 800,690 T 1600,690", None, "#15181f", 2))
        body += label_strip("ANIMORPHS  /  CHARACTER LINEUP", "GROUNDED TREATMENT  -  YOUNG JUSTICE REFERENCE",
                            "#f1eadb", "#a9b3c4")
        name_fg, tag_fg = "#f1eadb", "#a9b3c4"
        panel = "#20283a"

    # six busts across; each in its own crop window
    n = len(CHARS)
    slot = (W - 120) / n
    scale = 1.62
    for i, c in enumerate(CHARS):
        cx = 60 + slot * (i + 0.5)
        top = 250
        clip_id = f"crop{mode}{i}"
        body.append(f'<clipPath id="{clip_id}"><rect x="{f1(cx - slot/2 + 8)}" y="{top - 60}" '
                    f'width="{f1(slot - 16)}" height="{f1(200 * scale + 60)}" rx="4"/></clipPath>')
        body.append(rect(cx - slot / 2 + 8, top - 60, slot - 16, 200 * scale + 60, panel,
                         extra='opacity="0.55"' if mode == "dcau" else 'opacity="0.35"'))
        inner = group(bust(c, mode), f"translate({f1(cx)},{f1(top)}) scale({scale})")
        body.append(f'<g clip-path="url(#{clip_id})">{inner}</g>')
        body.append(text(cx, top + 200 * scale + 40, c["name"], 30, name_fg, "Big Shoulders Display", 900,
                         extra='letter-spacing="3"'))
        body.append(text(cx, top + 200 * scale + 66, c["tag"], 16, tag_fg, "Oswald", 500,
                         extra='letter-spacing="1"'))
    # treatment notes in the corner
    notes = {
        "dcau": ["unbroken angular outline, uniform 3px line", "small eyes, heavy upper lid, one-stroke nose",
                 "flat colour + one cel shadow", "hair as a single solid silhouette"],
        "yj": ["realistic teen proportions, softer jaw", "irises, highlights, lash detail",
               "two shade tones + a highlight plane", "layered clothing, seams and folds"],
    }[mode]
    for j, n_ in enumerate(notes):
        body.append(text(W - 60, 66 + j * 22, n_, 15, tag_fg, "Oswald", 500, "end", 'letter-spacing="1"'))
    return svg_doc("\n".join(body), bg)


# ------------------------------------------------------------- the scene

def andalite_fighter(x, y, s, glow=True):
    """Elfangor's fighter: an egg hull resting on two engine pods, with a
    thick tail cocked forward over the hull and a scythe blade at its tip.
    It should read as 'an Andalite made into a ship'."""
    out = []
    hull, hull_d, hull_l = "#4d5f7c", "#33415a", "#7d90ad"
    line = "#0a0a0d"
    T = lambda pts: [(x + px * s, y + py * s) for px, py in pts]
    if glow:
        out.append(ellipse(x, y + 92 * s, 230 * s, 30 * s, "#2f6fb8", extra='opacity="0.35"'))
        out.append(ellipse(x, y + 90 * s, 150 * s, 16 * s, "#6fb3ff", extra='opacity="0.35"'))
    # tail: thick at the root, curling up and forward
    piv = (100, -6)
    K = lambda pts, k=0.68: [(piv[0] + (px - piv[0]) * k, piv[1] + (py - piv[1]) * k) for px, py in pts]
    tail = K([(90, -40), (150, -62), (200, -104), (222, -150), (248, -146), (230, -70), (180, -14), (118, 20)])
    out.append(path(smooth(T(tail), True, 0.8), hull_d, line, 3))
    out.append(path(smooth(T(K([(120, -42), (170, -70), (208, -112), (222, -150), (232, -134), (206, -92),
                                (170, -54), (128, -30)])), True, 0.8), hull))
    blade = K([(222, -150), (248, -146), (236, -196), (200, -232), (150, -252), (192, -216), (216, -184)])
    out.append(path(smooth(T(blade), True, 0.5), "#d3ccb6", line, 3))
    out.append(path(smooth(T(K([(216, -184), (236, -196), (200, -232), (192, -216)])), True, 0.5), "#a9a28c"))
    # struts and landing pods, below the hull so they read
    for sgn in (-1, 1):
        out.append(poly(T([(sgn * 50, 30), (sgn * 74, 30), (sgn * 128, 74), (sgn * 108, 74)]), hull_d, line, 3))
        out.append(ellipse(x + sgn * 126 * s, y + 80 * s, 44 * s, 15 * s, hull, line, 3))
        out.append(ellipse(x + sgn * 126 * s, y + 80 * s, 44 * s, 15 * s, None, line, 3))
        out.append(ellipse(x + sgn * (126 + 30) * s, y + 80 * s, 8 * s, 8 * s, "#8fd1ff", line, 2))
    # hull
    out.append(ellipse(x, y, 130 * s, 55 * s, hull, line, 3.5))
    out.append(path(smooth(T([(-100, 28), (0, 52), (110, 20), (122, 4), (20, 36), (-90, 10)]), True, 0.9), hull_d))
    # raised canopy dome with a lit slit
    out.append(path(smooth(T([(-96, -22), (-70, -58), (-20, -70), (30, -60), (56, -34), (0, -46), (-60, -40)]),
                           True, 0.9), hull_l, line, 3))
    out.append(path(smooth(T([(-80, -38), (-40, -54), (14, -52)]), False), None, "#8fd1ff", 4 * s))
    # open hatch, light spilling down
    out.append(poly(T([(-20, 54), (30, 54), (60, 108), (-60, 108)]), "#8fd1ff", extra='opacity="0.5"'))
    return out


def silhouette_kid(x, y, s, height, hair, col="#04040a", rim="#3f7fc4"):
    """Standing silhouette, back to camera, looking at the ship."""
    out = []
    hh = 24 * s
    top = y - height * s
    neck_y = top + hh
    sh_y = neck_y + 8 * s
    hip_y = y - 74 * s
    out.append(rect(x - 5 * s, neck_y - 3 * s, 10 * s, 12 * s, col))  # neck
    torso = [(x - 21 * s, sh_y), (x + 21 * s, sh_y), (x + 15 * s, hip_y), (x - 15 * s, hip_y)]
    out.append(poly(torso, col))
    # legs, slightly apart
    out.append(poly([(x - 15 * s, hip_y), (x - 2 * s, hip_y), (x - 3 * s, y), (x - 15 * s, y)], col))
    out.append(poly([(x + 2 * s, hip_y), (x + 15 * s, hip_y), (x + 16 * s, y), (x + 4 * s, y)], col))
    # arms hanging
    out.append(poly([(x - 21 * s, sh_y), (x - 27 * s, sh_y + 6 * s), (x - 24 * s, hip_y + 6 * s),
                     (x - 17 * s, hip_y + 4 * s)], col))
    out.append(poly([(x + 21 * s, sh_y), (x + 27 * s, sh_y + 6 * s), (x + 24 * s, hip_y + 6 * s),
                     (x + 17 * s, hip_y + 4 * s)], col))
    # head and hair silhouette
    out.append(ellipse(x, top + hh / 2, 11 * s, hh / 2, col))
    if hair == "long":
        out.append(poly([(x - 12 * s, top + 6 * s), (x + 12 * s, top + 6 * s), (x + 15 * s, top + 60 * s),
                         (x - 15 * s, top + 60 * s)], col))
    elif hair == "shaggy":
        out.append(poly([(x - 13 * s, top + 4 * s), (x - 15 * s, top + 26 * s), (x - 9 * s, top + 22 * s),
                         (x, top + 28 * s), (x + 9 * s, top + 22 * s), (x + 15 * s, top + 26 * s),
                         (x + 13 * s, top + 4 * s)], col))
    elif hair == "chin":
        out.append(poly([(x - 12 * s, top + 6 * s), (x - 13 * s, top + 30 * s), (x + 13 * s, top + 30 * s),
                         (x + 12 * s, top + 6 * s)], col))
    # one colour of light: blue rim on the ship-facing edge
    out.append(path(smooth([(x + 9 * s, top + 3 * s), (x + 11 * s, top + hh / 2), (x + 7 * s, neck_y - 1 * s)],
                           False), None, rim, 2.4, 'opacity="0.95"'))
    out.append(pline([(x + 20 * s, sh_y + 2 * s), (x + 15 * s, hip_y), (x + 15 * s, y - 4 * s)], rim, 2.2,
                     'opacity="0.85"'))
    # faint ground shadow toward camera
    out.append(ellipse(x, y + 4 * s, 26 * s, 5 * s, "#000000", extra='opacity="0.6"'))
    return out


def sheet_scene():
    bg = "#04040a"
    b = []
    b.append('<defs>'
             '<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
             '<stop offset="0" stop-color="#04040a"/><stop offset="0.7" stop-color="#0c1220"/>'
             '<stop offset="1" stop-color="#1a2338"/></linearGradient>'
             '<radialGradient id="shipglow" cx="0.5" cy="0.5" r="0.5">'
             '<stop offset="0" stop-color="#4f9be6" stop-opacity="0.55"/>'
             '<stop offset="1" stop-color="#4f9be6" stop-opacity="0"/></radialGradient>'
             '<radialGradient id="moon2" cx="0.5" cy="0.5" r="0.5">'
             '<stop offset="0" stop-color="#efe8cf"/><stop offset="1" stop-color="#b8b39c"/></radialGradient>'
             '</defs>')
    b.append(rect(0, 0, W, H, "url(#sky)"))
    b.append(circle(250, 150, 60, "url(#moon2)"))
    b.append(circle(232, 132, 70, "#04040a", extra='opacity="0"'))
    # stars, sparse
    import random
    rnd = random.Random(11)
    for _ in range(70):
        b.append(circle(rnd.uniform(0, W), rnd.uniform(0, 420), rnd.uniform(0.6, 1.6), "#d8d6cc",
                        extra=f'opacity="{rnd.uniform(0.3, 0.9):.2f}"'))
    # distant mall and strip lights on the horizon, painted light-on-black
    b += deco_skyline(0, W, 560, seed=21, col="#161c2a", col2="#101521")
    # the unfinished building: steel frame grid
    fx, fy, cols, rows, cw, rh = 860, 200, 7, 5, 92, 72
    frame_col = "#242c3d"
    for i in range(cols + 1):
        b.append(rect(fx + i * cw - 4, fy, 8, rows * rh, frame_col))
    for j in range(rows + 1):
        b.append(rect(fx - 6, fy + j * rh - 4, cols * cw + 12, 8, frame_col))
    # diagonal braces
    for i in range(0, cols, 2):
        b.append(pline([(fx + i * cw, fy + rows * rh), (fx + (i + 1) * cw, fy + (rows - 1) * rh)], frame_col, 5))
    # crane, top-left
    b.append(rect(560, 176, 10, 384, "#1d2433"))
    b.append(rect(300, 170, 420, 8, "#1d2433"))
    b.append(pline([(300, 170), (565, 136), (720, 170)], "#1d2433", 4))
    b.append(pline([(380, 178), (380, 330)], "#1d2433", 2))
    b.append(rect(368, 330, 24, 16, "#1d2433"))
    # ground: dirt lot
    b.append(rect(0, 560, W, 340, "#1a1b22"))
    b.append(path(smooth([(0, 600), (200, 585), (420, 600), (700, 580), (1000, 598), (1300, 582), (W, 596), (W, H), (0, H)],
                         True, 0.9), "#212229"))
    # dirt mounds, concrete pipes, cinder-block walls
    b.append(path(smooth([(60, 640), (160, 590), (300, 600), (400, 650), (60, 650)], True), "#2a2a30"))
    b.append(path(smooth([(1180, 660), (1300, 600), (1460, 612), (1600, 660), (1180, 670)], True), "#2a2a30"))
    for k in range(3):
        b.append(ellipse(1360 + k * 62, 700, 32, 32, "#2c2d35", "#111219", 3))
        b.append(ellipse(1360 + k * 62, 700, 20, 20, "#101119"))
    for r_ in range(4):
        for cix in range(6):
            b.append(rect(100 + cix * 52 + (26 if r_ % 2 else 0), 690 - r_ * 22, 48, 20, "#2e2f36", "#111219", 2))
    # ship and its glow
    b.append(ellipse(800, 680, 380, 130, "url(#shipglow)"))
    b += andalite_fighter(800, 590, 1.0)
    # the five, backs to us, small against the ship
    gy = 880
    for (x, h, hair) in [(290, 196, "short"), (372, 192, "long"), (450, 172, "chin"),
                         (520, 168, "short"), (598, 186, "shaggy")]:
        b += silhouette_kid(x, gy, 1.12, h, hair)
    # caption
    b += label_strip("EPISODE ONE  /  THE CONSTRUCTION SITE", "DARK DECO SCENE STUDY  -  LIGHT PAINTED ONTO BLACK, ONE COLOUR OF LIGHT",
                     "#e9e2c8", "#8f9bb3")
    b.append(text(W - 60, 860, "“It was a ship. It was an alien ship. And it was coming toward us.”",
                  18, "#8f9bb3", "Oswald", 500, "end", 'letter-spacing="1"'))
    return svg_doc("\n".join(b), bg)


# ------------------------------------------------------------ the aliens

def andalite(x, y, s, mode="dcau"):
    """Side view, facing left. Blue-and-tan centauroid: a deer-like lower
    body, a humanoid upper torso as tall as the body, no mouth, two stalk
    eyes, and a thick tail cocked forward over the back ending in a scythe.
    Coordinates are in a 0..420 x -90..300 box, ground at y=290."""
    st = STYLES[mode]
    line, lw, thin = st["line"], st["lw"] * 1.1, st["thin"]
    fur, fur_d, tan = "#4f7fc2", "#365d97", "#dccba0"
    eye = "#1d3a2d"
    T = lambda pts: [(x + px * s, y + py * s) for px, py in pts]
    out = []

    def leg(px, knee_dx, dark):
        c = fur_d if dark else fur
        return [shape(T([(px, 160), (px + 24, 160), (px + knee_dx + 16, 214), (px + knee_dx + 10, 252),
                         (px + knee_dx + 12, 286), (px + knee_dx - 2, 286), (px + knee_dx - 4, 252),
                         (px + knee_dx - 8, 214)]), mode, c, line, lw),
                shape(T([(px + knee_dx - 6, 280), (px + knee_dx + 14, 280), (px + knee_dx + 16, 291),
                         (px + knee_dx - 8, 291)]), mode, "#23232c", line, thin)]

    # far legs
    out += leg(266, 28, True)
    out += leg(122, -18, True)
    # tail, behind the body: thick root, rising, curling forward over the back
    piv = (290, 156)
    K = lambda pts, k=0.72: [(piv[0] + (px - piv[0]) * k, piv[1] + (py - piv[1]) * k) for px, py in pts]
    tail = K([(280, 140), (318, 112), (344, 66), (346, 20), (326, -14), (296, -28),
              (310, -52), (354, -30), (378, 14), (376, 72), (350, 130), (310, 172)])
    out.append(shape(T(tail), mode, fur, line, lw))
    out.append(shape(T(K([(318, 112), (344, 66), (346, 20), (326, -14), (340, -6), (360, 24), (360, 70),
                          (338, 118)])), mode, fur_d))
    # scythe: a thin crescent sweeping forward over the back, edge on the outside
    blade = K([(296, -28), (310, -52), (280, -84), (236, -104), (186, -102), (230, -92), (268, -70)])
    out.append(shape(T(blade), mode, "#d9d2bc", line, lw))
    out.append(shape(T(K([(268, -70), (280, -84), (236, -104), (186, -102), (230, -94)])), mode,
                     shade("#d9d2bc", 0.82)))
    # lower body
    body = [(104, 150), (130, 124), (200, 116), (262, 120), (300, 136), (312, 166), (298, 190), (250, 200),
            (180, 200), (126, 190), (104, 170)]
    out.append(shape(T(body), mode, fur, line, lw))
    out.append(shape(T([(112, 178), (180, 200), (250, 200), (298, 190), (310, 176), (256, 186), (180, 188),
                        (118, 174)]), mode, tan))
    out.append(shape(T([(150, 120), (200, 116), (262, 120), (298, 134), (302, 150), (250, 138), (180, 136)]),
                     mode, fur_d))
    # near legs
    out += leg(258, 20, False)
    out += leg(112, -26, False)
    # upper torso, as tall as the lower body
    torso = [(96, 152), (86, 96), (88, 44), (102, 26), (130, 20), (152, 30), (158, 62), (152, 104), (156, 152)]
    out.append(shape(T(torso), mode, fur, line, lw))
    out.append(shape(T([(88, 44), (102, 26), (122, 24), (110, 60), (104, 104), (98, 150), (86, 96)]), mode, tan))
    # near arm, thin, seven-fingered hand shown as a fan of four
    out.append(shape(T([(140, 36), (156, 44), (162, 84), (156, 126), (146, 126), (150, 86), (136, 50)]),
                     mode, fur, line, lw))
    for k in range(4):
        out.append(shape(T([(145 + k * 3.6, 126), (140 + k * 4.4, 146)]), mode, None, line, thin, closed=False))
    # neck, then a deer-like head angled forward and down
    out.append(shape(T([(104, 26), (98, -2), (118, -18), (142, -12), (146, 22)]), mode, fur, line, lw))
    head = [(146, -8), (134, -32), (108, -46), (78, -42), (48, -24), (22, 2), (26, 16), (56, 12), (90, 6),
            (120, 2), (142, 6)]
    out.append(shape(T(head), mode, fur, line, lw))
    out.append(shape(T([(48, -24), (22, 2), (26, 16), (56, 12), (90, 6), (72, -6), (56, -14)]), mode, tan))
    # large almond eye, no mouth anywhere
    out.append(shape(T([(88, -24), (102, -32), (116, -26), (102, -16)]), mode, eye, line, thin))
    out.append(circle(x + 103 * s, y - 25 * s, 3.2 * s, "#8fd1a8"))
    out.append(shape(T([(30, 4), (38, 6)]), mode, None, line, thin, closed=False))  # nostril slit
    # stalk eyes on the crown
    for (bx, tip) in (((96, -44), (74, -86)), ((118, -46), (130, -90))):
        out.append(shape(T([bx, ((bx[0] + tip[0]) / 2 - 4, (bx[1] + tip[1]) / 2), tip]), mode, None, line,
                         lw * 1.5, closed=False))
        out.append(circle(x + tip[0] * s, y + tip[1] * s, 6.5 * s, fur, line, thin))
        out.append(circle(x + tip[0] * s - 1.5 * s, y + tip[1] * s, 3.2 * s, eye))
    return out


def hork_bajir(x, y, s, mode="dcau"):
    """Side view facing left; seven-foot bladed reptilian, hunched, beaked."""
    st = STYLES[mode]
    line, lw, thin = st["line"], st["lw"] * 1.1, st["thin"]
    skin, skin_d, blade = "#3e5a43", "#25392b", "#c9c9b2"
    T = lambda pts: [(x + px * s, y + py * s) for px, py in pts]
    out = []
    # tail behind
    out.append(shape(T([(130, 170), (190, 190), (250, 230), (300, 232), (296, 214), (250, 206), (196, 172), (140, 150)]),
                     mode, skin_d, line, lw))
    out.append(shape(T([(296, 214), (300, 232), (330, 236), (350, 212), (326, 212)]), mode, blade, line, thin))
    # far leg
    out.append(shape(T([(126, 168), (154, 172), (176, 230), (168, 286), (150, 290), (152, 236), (128, 200)]),
                     mode, skin_d, line, lw))
    # body: hunched torso
    torso = [(70, 80), (100, 60), (130, 66), (150, 110), (140, 170), (100, 190), (68, 180), (50, 140), (52, 100)]
    out.append(shape(T(torso), mode, skin, line, lw))
    out.append(shape(T([(52, 100), (50, 140), (68, 180), (100, 190), (84, 160), (68, 120), (66, 92)]), mode, skin_d))
    # near leg with T-rex foot
    out.append(shape(T([(70, 178), (104, 188), (112, 240), (96, 286), (60, 292), (76, 284), (84, 240), (62, 210)]),
                     mode, skin, line, lw))
    out.append(shape(T([(60, 292), (96, 286), (108, 296), (52, 300)]), mode, skin_d, line, thin))
    for tx in (44, 56, 68):
        out.append(shape(T([(tx, 296), (tx - 6, 306), (tx + 4, 304)]), mode, blade, line, thin))
    # knee blade, shin blades
    out.append(shape(T([(112, 240), (140, 224), (122, 254)]), mode, blade, line, thin))
    out.append(shape(T([(96, 270), (128, 268), (100, 282)]), mode, blade, line, thin))
    # arm reaching forward with wrist and elbow blades
    out.append(shape(T([(64, 96), (78, 100), (40, 150), (10, 180), (0, 172), (30, 140)]), mode, skin, line, lw))
    out.append(shape(T([(30, 140), (10, 130), (6, 150)]), mode, blade, line, thin))
    out.append(shape(T([(10, 180), (-12, 188), (-8, 170), (0, 172)]), mode, blade, line, thin))
    for fx_ in ((-8, 176), (-4, 184), (2, 188)):
        out.append(shape(T([fx_, (fx_[0] - 14, fx_[1] + 8)]), mode, None, line, thin, closed=False))
    out.append(shape(T([(64, 96), (78, 100), (86, 78), (60, 76)]), mode, blade, line, thin))  # elbow blade
    # snake neck and beaked head
    out.append(shape(T([(78, 62), (104, 58), (110, 30), (98, 4), (78, 6), (70, 30)]), mode, skin, line, lw))
    head = [(70, 6), (80, -12), (104, -14), (118, -4), (110, 8), (78, 12)]
    out.append(shape(T(head), mode, skin, line, lw))
    beak = [(70, 6), (26, 22), (72, 14)]
    out.append(shape(T(beak), mode, blade, line, thin))
    # head blades
    for hb in ([(96, -14), (100, -40), (108, -12)], [(108, -12), (128, -30), (116, -4)]):
        out.append(shape(T(hb), mode, blade, line, thin))
    out.append(circle(x + 84 * s, y - 2 * s, 3.5 * s, "#e0b23c", line, thin))
    return out


def sheet_aliens():
    bg = "#07070a"
    b = []
    b.append('<defs><linearGradient id="haze3" x1="0" y1="0" x2="0" y2="1">'
             '<stop offset="0" stop-color="#07070a" stop-opacity="0"/>'
             '<stop offset="1" stop-color="#1c2740" stop-opacity="1"/></linearGradient></defs>')
    b.append(rect(0, 380, W, 520, "url(#haze3)"))
    b += deco_skyline(0, W, 900, seed=5)
    b += label_strip("ANIMORPHS  /  THE ALIENS", "DARK DECO MODEL SHEET  -  ANDALITE (AX) AND HORK-BAJIR CONTROLLER",
                     "#e9e2c8", "#8f9bb3")
    # scale bar: 6 ft human silhouette for reference between them
    b.append(rect(760, 230, 3, 560, "#3a4256"))
    b.append(rect(0, 790, W, 2, "#3a4256"))
    for k, lbl in enumerate(["7 FT", "6 FT", "5 FT", "4 FT"]):
        yy = 230 + k * 80
        b.append(rect(752, yy, 19, 3, "#3a4256"))
        b.append(text(786, yy + 5, lbl, 13, "#5a6580", "Oswald", 500, "start", 'letter-spacing="1"'))
    b += andalite(120, 370, 1.45)
    b += hork_bajir(960, 325, 1.55)
    b.append(rect(0, 808, W, 92, "#07070a", extra='opacity="0.82"'))
    b.append(text(60, 846, "ANDALITE (AX)", 20, "#e9e2c8", "Oswald", 700, "start", 'letter-spacing="2"'))
    b.append(text(60, 872, "blue and tan fur, four hooves, two stalk eyes, no mouth, a tail cocked forward ending in a scythe",
                  16, "#8f9bb3", "Oswald", 500, "start", 'letter-spacing="1"'))
    b.append(text(840, 846, "HORK-BAJIR CONTROLLER", 20, "#e9e2c8", "Oswald", 700, "start", 'letter-spacing="2"'))
    b.append(text(840, 872, "seven feet of green-black hide, blades at elbows, wrists, knees, head and tail",
                  16, "#8f9bb3", "Oswald", 500, "start", 'letter-spacing="1"'))
    return svg_doc("\n".join(b), bg)


# ----------------------------------------------------------- title card

def sheet_title():
    bg = "#050507"
    b = []
    # dark deco frame: stepped border
    for i, (inset, col) in enumerate([(40, "#2a2f3d"), (52, "#171a24"), (60, "#2a2f3d")]):
        b.append(rect(inset, inset, W - 2 * inset, H - 2 * inset, None, col, 3 if i != 1 else 8))
    # deco sunburst behind the wordmark
    for k in range(-9, 10):
        ang = math.radians(90 + k * 6)
        x2 = 800 + math.cos(ang) * 900
        y2 = 560 - math.sin(ang) * 900
        b.append(pline([(800, 560), (x2, y2)], "#12151f", 5))
    b.append(rect(0, 0, W, H, None))
    b.append(text(800, 420, "ANIMORPHS", 190, "#ece4c8", "Limelight", 400, "middle", 'letter-spacing="10"'))
    b.append(rect(420, 460, 760, 4, "#8f9bb3"))
    b.append(text(800, 545, "THE INVASION", 64, "#c9b26a", "Oswald", 700, "middle", 'letter-spacing="14"'))
    b.append(text(800, 600, "PART ONE", 26, "#8f9bb3", "Oswald", 500, "middle", 'letter-spacing="12"'))
    # small fighter silhouette
    b += [s_.replace('stroke="#0a0a0d"', 'stroke="#8f9bb3"') for s_ in andalite_fighter(800, 725, 0.36, glow=False)]
    b.append(text(800, 838, "A FAN ADAPTATION OF THE BOOKS BY K. A. APPLEGATE",
                  15, "#5a6580", "Oswald", 500, "middle", 'letter-spacing="4"'))
    return svg_doc("\n".join(b), bg)


# ------------------------------------------------------------------ main

SHEETS = [
    ("01-lineup-dark-deco", lambda: sheet_lineup("dcau")),
    ("02-lineup-grounded", lambda: sheet_lineup("yj")),
    ("03-scene-construction-site", sheet_scene),
    ("04-aliens-model-sheet", sheet_aliens),
    ("05-title-card", sheet_title),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, fn in SHEETS:
        p = os.path.join(OUT, name + ".svg")
        with open(p, "w") as f:
            f.write(fn())
        print("wrote", os.path.relpath(p, HERE))


if __name__ == "__main__":
    main()
