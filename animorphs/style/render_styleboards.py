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

LINE = "#0b0b0e"
LW = 2.1        # one uniform outline weight, in head units (head = 100 tall)
THIN = 1.5
STYLES = {"dcau": dict(line=LINE, lw=LW, thin=THIN)}


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
# Timm construction. Heads are drawn in three-quarter view, face turned to
# the viewer's left, in a coordinate system 100 units tall (top of skull at
# y=0, chin at y=100). The nose breaks the far-side silhouette; the near jaw
# runs as a straight diagonal from under the ear to a broad squared chin on
# the boys and a small pointed chin on the girls. Small eyes, dot pupils,
# wedge brows, one-line mouth, flat colour, no face shading. Bodies for the
# full-figure lineup are in the same units (1 head = 100).

CHARS = [
    dict(key="jake", name="JAKE", tag="the reluctant leader", g="m", heads=7.0, build="m",
         skin="#e6b892", hair="#5a3a22", hair_hi="#7c5636", lip=None,
         top="#4d6478", top2="#3a4d5e", pants="#3a4a63", shoes="#2a2a30",
         outfit="tee", brow="flat", mouth="flat"),
    dict(key="rachel", name="RACHEL", tag="Xena, warrior princess", g="f", heads=6.9, build="f",
         skin="#ecc4a4", hair="#d8b86a", hair_hi="#ecd48f", lip="#b7676a",
         top="#6f3f66", top2="#4c5e80", pants="#46577a", shoes="#26262c",
         outfit="jacket", brow="arch", mouth="smirk"),
    dict(key="marco", name="MARCO", tag="the wise guy", g="m", heads=6.0, build="s",
         skin="#cfa176", hair="#1f1a1c", hair_hi="#3b3f5a", lip=None,
         top="#6b7061", top2="#4f5347", pants="#2f333c", shoes="#1e1e22",
         outfit="hoodie", brow="raised", mouth="smirk"),
    dict(key="cassie", name="CASSIE", tag="the heart", g="f", heads=6.1, build="f",
         skin="#7d4f33", hair="#171214", hair_hi="#33343f", lip="#8e4c46",
         top="#c9a94a", top2="#4a5f86", pants="#4a5f86", shoes="#5a3f2b",
         outfit="overalls", brow="soft", mouth="smile"),
    dict(key="tobias", name="TOBIAS", tag="the outsider", g="m", heads=6.6, build="s",
         skin="#e9c3a1", hair="#b89a5c", hair_hi="#d2b87c", lip=None,
         top="#7a3b33", top2="#8c8a86", pants="#3f4a5e", shoes="#3a3a3e",
         outfit="flannel", brow="worried", mouth="flat"),
    dict(key="ax", name="AX", tag="Aximili, in human morph", g="m", heads=6.8, build="m",
         skin="#c2966c", hair="#74563a", hair_hi="#a37d4e", lip=None,
         top="#d9d3c6", top2="#b3ada0", pants="#5a5a5e", shoes="#2c2c30",
         outfit="tee", brow="curious", mouth="open"),
]


def head_outline(g):
    if g == "m":
        return [(2, 0), (26, 3), (42, 14), (47, 32), (45, 50), (42, 62), (37, 70), (14, 94), (6, 99),
                (-8, 100), (-14, 96), (-16, 90), (-15, 85), (-17, 80), (-20, 74), (-22, 71), (-32, 66),
                (-23, 46), (-24, 30), (-18, 14), (-6, 3)]
    return [(2, 0), (24, 3), (40, 14), (44, 32), (43, 48), (38, 64), (28, 80), (14, 92), (2, 100),
            (-8, 97), (-13, 90), (-15, 84), (-17, 80), (-18, 75), (-20, 71), (-27, 67), (-21, 48),
            (-22, 28), (-16, 12), (-6, 3)]


def neck_pts(g):
    return [(-10, 96), (-8, 126), (34, 126), (36, 84)] if g == "m" else [(-8, 96), (-6, 126), (22, 126), (24, 86)]


def draw_neck(c):
    g = c["g"]
    out = [poly(neck_pts(g), c["skin"], LINE, LW)]
    # the one shadow Timm keeps: under the jaw, on the neck
    if g == "m":
        out.append(poly([(-9, 101), (6, 100), (14, 95), (36, 72), (36, 110), (-9, 114)], shade(c["skin"], 0.74)))
    else:
        out.append(poly([(-7, 99), (2, 101), (14, 93), (24, 84), (24, 108), (-7, 110)], shade(c["skin"], 0.74)))
    return out


def draw_ear(c):
    g = c["g"]
    pts = ([(41, 49), (49, 46), (53, 55), (50, 65), (43, 67)] if g == "m"
           else [(38, 50), (46, 47), (50, 56), (47, 65), (40, 66)])
    inner = [(46, 52), (48, 58), (45, 62)] if g == "m" else [(43, 53), (45, 58), (42, 62)]
    return [poly(pts, c["skin"], LINE, LW), pline(inner, LINE, THIN)]


def draw_eyes(c):
    g = c["g"]
    white = "#efece4"
    out = []
    if g == "m":
        near = [(2, 47), (18, 45.5), (17, 50), (11, 54), (4, 52.5)]
        far = [(-21, 47.5), (-8, 46.5), (-8, 50), (-13, 53.5), (-19, 52)]
        out += [poly(near, white, LINE, THIN), poly(far, white, LINE, THIN)]
        out += [circle(10, 49.3, 2.4, LINE), circle(-13.5, 49.6, 2.1, LINE)]
        out += [pline([(2, 47), (18, 45.5)], LINE, LW * 1.4), pline([(-21, 47.5), (-8, 46.5)], LINE, LW * 1.4)]
    else:
        near = [(0, 46), (19, 44.5), (18, 50), (12, 55), (3, 53)]
        far = [(-21, 46.5), (-8, 45.5), (-8, 50), (-14, 54.5), (-20, 52)]
        out += [poly(near, white, LINE, THIN), poly(far, white, LINE, THIN)]
        out += [circle(10, 49.6, 3.0, LINE), circle(-13.5, 50, 2.7, LINE)]
        out += [pline([(0, 46), (19, 44.5)], LINE, LW * 1.6), pline([(-21, 46.5), (-8, 45.5)], LINE, LW * 1.6)]
        # lash flicks at the outer corners
        out += [pline([(19, 44.5), (24.5, 41.5)], LINE, LW * 1.3), pline([(-21, 46.5), (-25.5, 44)], LINE, LW * 1.2)]
    return out


def draw_brows(c):
    g, kind = c["g"], c["brow"]
    if g == "m":
        near = [(0, 44.5), (20, 42), (21, 45), (2, 47.5)]
        far = [(-23, 45.5), (-10, 43.5), (-9, 46.5), (-22, 48.5)]
        if kind == "raised":        # Marco: one brow up
            near = [(x, y - 3.5) for x, y in near]
        elif kind == "worried":     # Tobias: inner ends lifted
            near = [(0, 41.5), (20, 41.5), (21, 44.5), (2, 44.5)]
            far = [(-23, 44.5), (-10, 41), (-9, 44), (-22, 47.5)]
        elif kind == "curious":     # Ax: both up
            near = [(x, y - 2.5) for x, y in near]
            far = [(x, y - 2.5) for x, y in far]
        return [poly(near, LINE), poly(far, LINE)]
    # girls: thin arched strokes
    lift = 1.5 if kind == "arch" else 0
    near = [(0, 42), (9, 38.5 - lift), (20, 40.5)]
    far = [(-22, 43), (-15, 40 - lift), (-9, 41.5)]
    return [path(smooth(near, False), None, LINE, LW * 1.15), path(smooth(far, False), None, LINE, LW * 1.05)]


def draw_nose(c):
    # the nose is already the far-side silhouette; add the nostril
    return [pline([(-26, 69.5), (-20, 70.5)], LINE, THIN)] if c["g"] == "m" else [pline([(-22, 69.5), (-18, 70.5)], LINE, THIN)]


def draw_mouth(c):
    g, kind = c["g"], c["mouth"]
    out = []
    if g == "m":
        pts = {"flat": [(-15, 81), (-5, 82), (4, 81.5)],
               "smirk": [(-15, 81.5), (-4, 82), (6, 79.5)],
               "grin": [(-15, 80), (-5, 83.5), (6, 79)],
               "open": [(-14, 80), (-5, 80.5), (4, 80.5)]}.get(kind, [(-15, 81), (4, 81.5)])
        if kind == "open":
            out.append(poly([(-13, 80.5), (2, 80.5), (0, 85), (-9, 85)], "#3a1a1c", LINE, THIN))
        out.append(path(smooth(pts, False), None, LINE, LW))
        out.append(pline([(-9, 89), (-2, 89.5)], LINE, THIN))   # chin crease
    else:
        lips = [(-15, 79.5), (-9, 78), (0, 79), (2, 80.5), (-3, 83), (-12, 82.5)]
        if kind == "smile":
            lips = [(-15, 79), (-9, 78), (0, 78.5), (3, 78.5), (-3, 82.5), (-12, 82.5)]
        out.append(poly(lips, c["lip"] or shade(c["skin"], 0.8), LINE, THIN))
        mid = [(-15, 79.5), (-6, 80.5), (2, 80.5)] if kind != "smile" else [(-15, 79), (-6, 80.5), (3, 78.5)]
        out.append(path(smooth(mid, False), None, LINE, THIN * 1.2))
    return out


# hair: returns (behind, in_front) lists. Solid silhouettes, sharp points.

def hair_jake(c):
    front = [(-32, 24), (-28, 10), (-16, 1), (0, -4), (20, -3), (38, 4), (49, 18), (50, 38), (46, 50), (41, 49),
             (40, 44), (36, 32), (30, 22), (20, 18), (10, 20), (0, 16), (-8, 22), (-18, 18), (-26, 26)]
    return [], [poly(front, c["hair"], LINE, LW), poly([(-6, 4), (14, 0), (30, 6), (20, 10), (4, 10)], c["hair_hi"])]


def hair_rachel(c):
    back = [(-30, 20), (-22, 4), (-4, -6), (18, -6), (38, 2), (48, 18), (52, 40), (56, 80), (60, 130), (62, 200),
            (-46, 200), (-44, 130), (-40, 80), (-34, 44)]
    front = [(-26, 22), (-20, 8), (-6, -2), (14, -4), (34, 2), (46, 16), (48, 34), (44, 46), (40, 50), (36, 40),
             (28, 26), (16, 20), (2, 22), (-10, 18), (-20, 26), (-24, 36)]
    lock = [(44, 44), (52, 70), (56, 120), (50, 162), (40, 150), (44, 110), (40, 70)]
    return ([poly(back, c["hair"], LINE, LW)],
            [poly(front, c["hair"], LINE, LW), poly(lock, c["hair"], LINE, LW),
             poly([(-10, 4), (10, -1), (30, 6), (20, 12), (0, 12)], c["hair_hi"])])


def hair_marco(c):
    back = [(-34, 26), (-26, 6), (-6, -6), (16, -6), (36, 2), (48, 20), (52, 50), (54, 92), (44, 102), (32, 94),
            (-30, 94), (-38, 84), (-40, 60)]
    front = [(-30, 30), (-26, 10), (-8, -2), (14, -4), (34, 2), (46, 16), (50, 34), (50, 52), (52, 92), (44, 100),
             (40, 86), (40, 60), (38, 40), (30, 26), (22, 30), (14, 22), (6, 30), (-4, 22), (-12, 30), (-20, 24),
             (-24, 40), (-28, 60), (-30, 90), (-36, 90), (-38, 60), (-34, 44)]
    return ([poly(back, c["hair"], LINE, LW)],
            [poly(front, c["hair"], LINE, LW), poly([(-14, 2), (6, -3), (26, 4), (16, 10), (-2, 10)], c["hair_hi"])])


def hair_cassie(c):
    cap = [(-28, 22), (-26, 8), (-14, 0), (2, -4), (22, -3), (40, 4), (48, 18), (48, 36), (44, 48), (40, 50), (38, 38),
           (32, 26), (22, 20), (10, 18), (-2, 20), (-12, 16), (-20, 20), (-24, 30)]
    return [], [poly(cap, c["hair"], LINE, LW), poly([(-8, 6), (8, 1), (24, 6), (16, 10), (0, 10)], c["hair_hi"])]


def hair_tobias(c):
    front = [(-34, 30), (-30, 10), (-16, -2), (2, -6), (22, -4), (40, 4), (50, 20), (52, 42), (48, 54), (42, 50),
             (40, 42), (36, 50), (32, 34), (26, 44), (20, 30), (12, 42), (6, 28), (-2, 40), (-8, 26), (-16, 38),
             (-22, 26), (-28, 40)]
    return [], [poly(front, c["hair"], LINE, LW), poly([(-14, 4), (4, -2), (24, 2), (14, 8), (-4, 10)], c["hair_hi"])]


def hair_ax(c):
    front = [(-30, 26), (-28, 10), (-16, 0), (0, -6), (20, -5), (38, 2), (50, 16), (54, 36), (56, 60), (52, 74),
             (44, 70), (42, 52), (40, 48), (38, 36), (30, 24), (20, 20), (8, 22), (-4, 16), (-14, 22), (-22, 18),
             (-28, 30), (-32, 44), (-36, 62), (-30, 66), (-26, 50), (-24, 40)]
    out = [poly(front, c["hair"], LINE, LW), poly([(-12, 4), (8, -2), (28, 4), (18, 10), (0, 10)], c["hair_hi"])]
    # a few curl strokes along the silhouette
    for (x, y) in [(52, 30), (54, 56), (-34, 56), (-30, 16)]:
        out.append(path(f"M {x - 4},{y} q 5,-5 6,2", None, LINE, THIN))
    return [], out


HAIR = dict(jake=hair_jake, rachel=hair_rachel, marco=hair_marco, cassie=hair_cassie,
            tobias=hair_tobias, ax=hair_ax)


def head(c):
    """Head, neck and hair in head units. Bust clothing / body are separate."""
    parts = []
    back_hair, front_hair = HAIR[c["key"]](c)
    parts += back_hair
    parts += draw_neck(c)
    parts += draw_ear(c)
    parts.append(poly(head_outline(c["g"]), c["skin"], LINE, LW))
    parts += draw_brows(c)
    parts += draw_eyes(c)
    parts += draw_nose(c)
    parts += draw_mouth(c)
    parts += front_hair
    return parts


# ---------------------------------------------------------------- bodies

def body_dims(c):
    """Landmark table in head units for a standing figure, y=0 at top of head."""
    T = c["heads"] * 100
    b = c["build"]
    S = {"m": 92, "s": 82, "f": 70}[b]     # shoulder half-width
    Wt = {"m": 52, "s": 48, "f": 38}[b]    # waist
    Hp = {"m": 60, "s": 56, "f": 58}[b]    # hips
    y_s = 130
    y_w = y_s + (T - 100) * 0.30
    y_h = y_w + (T - 100) * 0.10
    y_c = y_h + 24
    y_k = y_c + (T - y_c) * 0.5
    y_a = T - 22
    return dict(T=T, S=S, W=Wt, H=Hp, y_s=y_s, y_w=y_w, y_h=y_h, y_c=y_c, y_k=y_k, y_a=y_a)


def figure(c):
    """Full standing figure, face three-quarter, body square to camera."""
    d = body_dims(c)
    T, S, Wt, Hp = d["T"], d["S"], d["W"], d["H"]
    y_s, y_w, y_h, y_c, y_k, y_a = d["y_s"], d["y_w"], d["y_h"], d["y_c"], d["y_k"], d["y_a"]
    skin, top, top2, pants, shoes = c["skin"], c["top"], c["top2"], c["pants"], c["shoes"]
    fem = c["build"] == "f"
    kind = c["outfit"]
    parts = []
    # neck extends under the collar; drawn first
    parts.append(poly([(-10, 96), (-12, y_s + 6), (36, y_s + 6), (36, 84)] if not fem else
                      [(-8, 96), (-10, y_s + 6), (24, y_s + 6), (24, 86)], skin, LINE, LW))
    # legs: thigh tapers to the knee, calf swells a little, narrow ankle
    kw = 40 if not fem else 36
    for sgn in (-1, 1):
        y_cf = y_k + (y_a - y_k) * 0.4
        leg = [(sgn * Hp, y_h), (sgn * 5, y_c), (sgn * 10, y_k), (sgn * 8, y_cf), (sgn * 10, y_a), (sgn * 30, y_a),
               (sgn * kw, y_cf), (sgn * kw, y_k), (sgn * (Hp + 2), y_h + 26)]
        parts.append(poly(leg, pants, LINE, LW))
        parts.append(poly([(sgn * 8, y_a), (sgn * 32, y_a), (sgn * 44, y_a + 10), (sgn * 46, T - 4), (sgn * 38, T),
                           (sgn * 4, T), (sgn * 2, y_a + 8)], shoes, LINE, LW))
    # arms: wrist at the crotch line, fingertips mid-thigh; sleeve over the skin
    long_sleeve = kind in ("hoodie", "jacket", "flannel")
    sleeve_col = {"jacket": top2, "flannel": top}.get(kind, top)
    for sgn in (-1, 1):
        sh = (sgn * (S - 6), y_s + 4)
        el = (sgn * (S + 6), y_w + 6)
        wr = (sgn * (S + 2), y_c + 6)
        pit = (sgn * (S - 30), y_s + 2)
        upper = [pit, sh, (el[0] + sgn * 11, el[1]), (el[0] - sgn * 11, el[1] + 4)]
        fore = [(el[0] + sgn * 11, el[1]), (wr[0] + sgn * 8, wr[1]), (wr[0] - sgn * 8, wr[1]), (el[0] - sgn * 11, el[1] + 4)]
        parts.append(poly(upper, skin, LINE, LW))
        parts.append(poly(fore, skin, LINE, LW))
        if long_sleeve:
            sleeve = [pit, sh, (el[0] + sgn * 12, el[1]), (wr[0] + sgn * 10, wr[1] - 6), (wr[0] - sgn * 10, wr[1] - 6),
                      (el[0] - sgn * 12, el[1] + 4)]
        else:
            t = 0.45
            o = (sh[0] + (el[0] + sgn * 11 - sh[0]) * t, sh[1] + (el[1] - sh[1]) * t)
            i_ = (pit[0] + (el[0] - sgn * 11 - pit[0]) * t, pit[1] + (el[1] + 4 - pit[1]) * t)
            sleeve = [pit, sh, (o[0] + sgn * 2, o[1] + 4), (i_[0] - sgn * 2, i_[1] + 6)]
        parts.append(poly(sleeve, sleeve_col, LINE, LW))
        parts.append(poly([(wr[0] - sgn * 8, wr[1]), (wr[0] + sgn * 8, wr[1]), (wr[0] + sgn * 12, wr[1] + 26),
                           (wr[0] + sgn * 4, wr[1] + 44), (wr[0] - sgn * 7, wr[1] + 40), (wr[0] - sgn * 10, wr[1] + 18)],
                          skin, LINE, LW))
        parts.append(pline([(wr[0] + sgn * 7, wr[1] + 22), (wr[0] + sgn * 9, wr[1] + 30)], LINE, THIN))
    # torso garment
    hem = y_h + (8 if fem else 14)
    torso = [(-(S - 12), y_s), (S + 2, y_s), (S - 14, y_s + 30), (Wt + 4, y_w), (Hp + 2, hem), (-(Hp - 6), hem),
             (-(Wt - 4), y_w), (-(S - 26), y_s + 30)]
    parts.append(poly(torso, top, LINE, LW))
    if kind == "tee":
        parts.append(poly([(-8, y_s - 8), (30, y_s - 8), (26, y_s + 2), (12, y_s + 8), (-4, y_s + 2)], shade(top, 0.75), LINE, LW))
    elif kind == "hoodie":
        parts.append(poly([(-24, y_s - 12), (44, y_s - 12), (50, y_s + 10), (12, y_s + 22), (-30, y_s + 10)], shade(top, 0.75), LINE, LW))
        parts.append(poly([(-Wt - 4, y_w + 20), (Wt + 4, y_w + 20), (Wt + 4, hem - 8), (-Wt - 4, hem - 8)], None, LINE, THIN))
        for sgn in (-1, 1):
            parts.append(pline([(sgn * 10, y_s + 18), (sgn * 12, y_w + 10)], LINE, THIN))
    elif kind == "jacket":
        parts.append(poly([(-4, y_s - 6), (22, y_s - 6), (20, y_s + 4), (10, y_s + 10), (-2, y_s + 4)], shade(top, 0.75), LINE, LW))
        for sgn in (-1, 1):
            lapel = [(sgn * (S - 4), y_s), (sgn * 16, y_s - 6), (sgn * 14, y_s + 60), (sgn * 20, hem - 10),
                     (sgn * (Hp - 2), hem - 10), (sgn * Wt, y_w), (sgn * (S - 20), y_s + 30)]
            parts.append(poly(lapel, top2, LINE, LW))
            parts.append(poly([(sgn * 16, y_s - 6), (sgn * 34, y_s - 2), (sgn * 30, y_s + 26), (sgn * 15, y_s + 20)],
                              shade(top2, 0.8), LINE, LW))
    elif kind == "overalls":
        parts.append(poly([(-8, y_s - 8), (30, y_s - 8), (26, y_s + 2), (12, y_s + 8), (-4, y_s + 2)], shade(top, 0.75), LINE, LW))
        bib_top = y_s + 44
        for sgn in (-1, 1):
            parts.append(poly([(sgn * 22, bib_top), (sgn * 28, y_s), (sgn * 38, y_s), (sgn * 32, bib_top)], top2, LINE, LW))
        parts.append(poly([(-30, bib_top), (30, bib_top), (Wt + 4, y_w), (Hp, hem + 6), (-Hp, hem + 6), (-Wt - 4, y_w)],
                          top2, LINE, LW))
        for sgn in (-1, 1):
            parts.append(circle(sgn * 24, bib_top + 5, 3.4, "#c9b46a", LINE, THIN))
        parts.append(poly([(-16, bib_top + 18), (16, bib_top + 18), (16, bib_top + 42), (-16, bib_top + 42)], None, LINE, THIN))
    elif kind == "flannel":
        # grey tee, flannel open over it
        parts.append(poly([(-Wt, y_s), (Wt, y_s), (Wt, hem), (-Wt, hem)], top2, LINE, LW))
        parts.append(poly([(-6, y_s - 6), (28, y_s - 6), (24, y_s + 2), (12, y_s + 8), (-2, y_s + 2)], shade(top2, 0.75), LINE, LW))
        for sgn in (-1, 1):
            panel = [(sgn * (S - 4), y_s), (sgn * 18, y_s - 6), (sgn * 20, hem + 4), (sgn * (Hp + 4), hem + 4),
                     (sgn * Wt, y_w), (sgn * (S - 20), y_s + 30)]
            pid = f"fl{c['key']}{int(sgn > 0)}"
            parts.append(f'<clipPath id="{pid}">{poly(panel)}</clipPath>')
            parts.append(poly(panel, top, LINE, LW))
            grid = []
            for x in range(-120, 121, 18):
                grid.append(rect(x, y_s - 10, 5, hem - y_s + 20, shade(top, 0.72)))
            for y in range(int(y_s) - 10, int(hem) + 20, 20):
                grid.append(rect(-120, y, 240, 5, shade(top, 0.72)))
            parts.append(group(grid, extra=f'clip-path="url(#{pid})" opacity="0.9"'))
            parts.append(poly(panel, None, LINE, LW))
    # head over everything
    parts += head(c)
    return parts


def bust(c, mode="dcau"):
    """Head and shoulders, cropped at y~200 for the heads board."""
    d = body_dims(c)
    S, y_s = d["S"], d["y_s"]
    top = c["top"]
    parts = [poly([(-10, 96), (-12, y_s + 6), (36, y_s + 6), (36, 84)] if c["build"] != "f" else
                  [(-8, 96), (-10, y_s + 6), (24, y_s + 6), (24, 86)], c["skin"], LINE, LW)]
    torso = [(-(S - 12), y_s), (S + 2, y_s), (S + 12, y_s + 40), (S + 14, 230), (-(S + 2), 230), (-(S), y_s + 40)]
    parts.append(poly(torso, top, LINE, LW))
    kind = c["outfit"]
    if kind in ("tee", "overalls"):
        parts.append(poly([(-8, y_s - 8), (30, y_s - 8), (26, y_s + 2), (12, y_s + 8), (-4, y_s + 2)], shade(top, 0.75), LINE, LW))
        if kind == "overalls":
            for sgn in (-1, 1):
                parts.append(poly([(sgn * 22, 230), (sgn * 28, y_s), (sgn * 38, y_s), (sgn * 32, 230)], c["top2"], LINE, LW))
    elif kind == "hoodie":
        parts.append(poly([(-24, y_s - 12), (44, y_s - 12), (50, y_s + 10), (12, y_s + 22), (-30, y_s + 10)], shade(top, 0.75), LINE, LW))
        for sgn in (-1, 1):
            parts.append(pline([(sgn * 10, y_s + 18), (sgn * 12, 230)], LINE, THIN))
    elif kind in ("jacket", "flannel"):
        under = c["top2"] if kind == "flannel" else top
        over = top if kind == "flannel" else c["top2"]
        parts.append(poly([(-40, y_s - 4), (40, y_s - 4), (40, 230), (-40, 230)], under, LINE, LW))
        parts.append(poly([(-4, y_s - 6), (24, y_s - 6), (20, y_s + 4), (10, y_s + 10), (-2, y_s + 4)], shade(under, 0.75), LINE, LW))
        for sgn in (-1, 1):
            panel = [(sgn * (S - 4), y_s), (sgn * 16, y_s - 6), (sgn * 18, 230), (sgn * (S + 8), 230), (sgn * (S + 6), y_s + 40)]
            parts.append(poly(panel, over, LINE, LW))
            if kind == "jacket":
                parts.append(poly([(sgn * 16, y_s - 6), (sgn * 34, y_s - 2), (sgn * 30, y_s + 26), (sgn * 15, y_s + 20)],
                                  shade(over, 0.8), LINE, LW))
    parts += head(c)
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

def deco_ground(body, seed=7, haze_id="haze"):
    body.append(f'<defs><linearGradient id="{haze_id}" x1="0" y1="0" x2="0" y2="1">'
                '<stop offset="0" stop-color="#07070a" stop-opacity="0"/>'
                '<stop offset="1" stop-color="#1c2740" stop-opacity="1"/></linearGradient></defs>')
    body.append(rect(0, 400, W, 500, f"url(#{haze_id})"))
    body += deco_skyline(0, W, 900, seed=seed)


def sheet_heads():
    bg = "#07070a"
    body = []
    deco_ground(body, seed=7)
    body += label_strip("ANIMORPHS  /  HEADS", "TIMM CONSTRUCTION, THREE-QUARTER  -  BATMAN & SUPERMAN ADVENTURES",
                        "#e9e2c8", "#8f9bb3")
    notes = ["three-quarter view, nose breaks the far silhouette", "boys: straight jaw to a squared chin, thick neck",
             "girls: heart face, pointed chin, lash flicks, full lips", "small eyes, dot pupils, wedge brows, one-line mouth",
             "one thin uniform outline, flat colour, no face shading"]
    for j, n_ in enumerate(notes):
        body.append(text(W - 60, 58 + j * 21, n_, 14.5, "#8f9bb3", "Oswald", 500, "end", 'letter-spacing="1"'))
    n = len(CHARS)
    slot = (W - 120) / n
    scale = 1.55
    top = 262
    for i, c in enumerate(CHARS):
        cx = 60 + slot * (i + 0.5)
        clip_id = f"crop{i}"
        ph = 200 * scale + 40
        body.append(f'<clipPath id="{clip_id}"><rect x="{f1(cx - slot/2 + 8)}" y="{top - 70}" '
                    f'width="{f1(slot - 16)}" height="{f1(ph)}"/></clipPath>')
        body.append(rect(cx - slot / 2 + 8, top - 70, slot - 16, ph, "#0d0f16", extra='opacity="0.6"'))
        inner = group(bust(c), f"translate({f1(cx - 8)},{f1(top)}) scale({scale})")
        body.append(f'<g clip-path="url(#{clip_id})">{inner}</g>')
        body.append(text(cx, top - 70 + ph + 40, c["name"], 30, "#e9e2c8", "Big Shoulders Display", 900,
                         extra='letter-spacing="3"'))
        body.append(text(cx, top - 70 + ph + 66, c["tag"], 16, "#8f9bb3", "Oswald", 500, extra='letter-spacing="1"'))
    return svg_doc("\n".join(body), bg)


def sheet_figures():
    bg = "#07070a"
    body = []
    deco_ground(body, seed=9, haze_id="haze2")
    body += label_strip("ANIMORPHS  /  FULL FIGURE LINEUP", "TIMM PROPORTIONS AT TEEN HEIGHTS  -  JAKE 7 HEADS, MARCO 6",
                        "#e9e2c8", "#8f9bb3")
    # floor line and height ticks
    floor = 820
    body.append(rect(60, floor, W - 120, 2, "#3a4256"))
    px_per_head = 80.0
    for k in range(1, 8):
        yy = floor - k * px_per_head
        body.append(rect(60, yy, 14, 2, "#3a4256"))
        body.append(text(84, yy + 5, f"{k}", 13, "#5a6580", "Oswald", 500, "start"))
    n = len(CHARS)
    slot = (W - 200) / n
    for i, c in enumerate(CHARS):
        cx = 140 + slot * (i + 0.5)
        sc = px_per_head / 100.0
        T = c["heads"] * 100
        inner = group(figure(c), f"translate({f1(cx)},{f1(floor - T * sc)}) scale({sc})")
        body.append(inner)
        body.append(text(cx, floor + 36, c["name"], 26, "#e9e2c8", "Big Shoulders Display", 900, extra='letter-spacing="3"'))
        body.append(text(cx, floor + 58, f"{c['heads']:.1f} heads", 14, "#8f9bb3", "Oswald", 500, extra='letter-spacing="1"'))
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
    ("01-heads", sheet_heads),
    ("02-figures", sheet_figures),
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
