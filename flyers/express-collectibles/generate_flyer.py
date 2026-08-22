#!/usr/bin/env python3
"""Generator for the Express Collectibles 'Video Games on Whatnot' flyer.

Rebuilds the hand-drawn marker poster as an SVG, with a Robin Williams
caricature in the middle. Every line is wobbled so it reads as hand-inked
marker rather than clean vector art.

Usage:
    python3 generate_flyer.py            # the full poster
    python3 generate_flyer.py face       # portrait test sheet only

Writes robin-williams-whatnot-flyer.svg (fonts embedded, fully standalone)
plus poster.svg / poster.html previews. Fonts are fetched from Google Fonts
into ./fonts/ on first run (Permanent Marker, Architects Daughter, Baloo 2).

To rasterize, open the SVG in any browser, or:
    chromium --headless --no-sandbox --hide-scrollbars \
        --window-size=1480,1180 --force-device-scale-factor=2 \
        --screenshot=flyer.png robin-williams-whatnot-flyer.svg
"""
import math, random, sys, os, subprocess

FONT_FILES = {
    "PermanentMarker.ttf":
        "https://fonts.gstatic.com/s/permanentmarker/v16/"
        "Fh4uPib9Iyv2ucM6pGQMWimMp004Hao.ttf",
    "ArchitectsDaughter.ttf":
        "https://fonts.gstatic.com/s/architectsdaughter/v20/"
        "KtkxAKiDZI_td1Lkx62xHZHDtgO_Y-bvfY4.ttf",
    "Baloo2-800.woff2":
        "https://fonts.gstatic.com/s/baloo2/v23/"
        "wXK0E3kTposypRydzVT08TS3JnAmtdiayppo_lc.woff2",
}


def font_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (os.path.join(here, "fonts"), os.path.join(here, "..", "fonts")):
        if all(os.path.isfile(os.path.join(d, n)) for n in FONT_FILES):
            return d
    d = os.path.join(here, "fonts")
    os.makedirs(d, exist_ok=True)
    for name, url in FONT_FILES.items():
        path = os.path.join(d, name)
        if not os.path.isfile(path):
            print(f"fetching {name} ...")
            subprocess.run(["curl", "-sS", "-o", path, url], check=True)
    return d

INK = "#231a12"        # warm marker black
SKIN = "#f2c79e"
SKIN_SHADE = "#d99f72"
HAIR = "#6e4423"
HAIR_DK = "#472a12"
RED = "#c62f2b"
BLUE = "#2456a6"
GREEN = "#2e7d32"
YELLOW = "#e8b62a"
ORANGE = "#e07f20"
SHIRT = "#2f6fb3"
SHIRT_DK = "#245c96"
GRASS = "#3f9142"
PAPER = "#fbf7ee"

# ---------------------------------------------------------------- primitives

def _smooth(pts, closed=False):
    """Catmull-Rom through pts -> cubic bezier path string."""
    if len(pts) < 3:
        (x1, y1), (x2, y2) = pts[0], pts[-1]
        return f"M {x1:.1f},{y1:.1f} L {x2:.1f},{y2:.1f}"
    if closed:
        p = [pts[-1]] + list(pts) + [pts[0], pts[1]]
    else:
        p = [pts[0]] + list(pts) + [pts[-1]]
    d = f"M {p[1][0]:.1f},{p[1][1]:.1f} "
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        d += (f"C {c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} "
              f"{p2[0]:.1f},{p2[1]:.1f} ")
    if closed:
        d += "Z"
    return d


def _sample(pts, closed=False, step=9.0):
    """Sample the smooth curve through pts every ~step px (poly approx)."""
    if closed:
        p = [pts[-1]] + list(pts) + [pts[0], pts[1]]
    else:
        p = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        seg = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        n = max(2, int(seg / step))
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t +
                       (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                       (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t +
                       (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                       (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    if not closed:
        out.append(p[-2])
    return out


_seed_counter = [0]

def hand(pts, amp=1.6, seed=None, closed=False):
    """Path string through pts with hand-drawn perpendicular jitter."""
    if seed is None:
        _seed_counter[0] += 1
        seed = _seed_counter[0]
    r = random.Random(seed)
    sm = _sample(pts, closed)
    out = []
    n = len(sm)
    for i, (x, y) in enumerate(sm):
        if 0 < i < n - 1 or closed:
            x2, y2 = sm[(i + 1) % n]
            x1, y1 = sm[i - 1]
            dx, dy = x2 - x1, y2 - y1
            d = math.hypot(dx, dy) or 1.0
            j = (r.random() * 2 - 1) * amp
            x, y = x - dy / d * j, y + dx / d * j
        out.append((x, y))
    return _smooth(out, closed)


def st(d, color=INK, w=3.4, fill="none", op=1.0, extra=""):
    o = f' opacity="{op}"' if op != 1.0 else ""
    return (f'<path d="{d}" fill="{fill}" stroke="{color}" stroke-width="{w}"'
            f' stroke-linecap="round" stroke-linejoin="round"{o} {extra}/>\n')


def ink(pts, color=INK, w=3.4, amp=1.6, closed=False, fill="none",
        double=True, op=1.0):
    """Marker stroke: main pass + a lighter re-ink pass."""
    s = st(hand(pts, amp, None, closed), color, w, fill, op)
    if double:
        s += st(hand(pts, amp * 0.8, None, closed), color, w * 0.5, "none",
                0.4 * op)
    return s


def blob(pts, fill, amp=1.5, closed=True, op=1.0):
    """Filled wobbly shape, no stroke."""
    return st(hand(pts, amp, None, closed), "none", 0, fill, op)


def squig(x1, x2, y, color=RED, w=4.0, ampl=2.6, per=15):
    pts, x = [], x1
    up = True
    while x < x2:
        pts.append((x, y + (-ampl if up else ampl)))
        up = not up
        x += per
    pts.append((x2, y))
    return st(hand(pts, 0.8), color, w)


def scribble(pts_region, color, angle_deg=35, gap=8.0, w=5.0, op=0.4,
             pad=2.0):
    """Serpentine marker-fill texture clipped to a region."""
    _seed_counter[0] += 1
    cid = f"scr{_seed_counter[0]}"
    d_clip = hand(pts_region, 1.0, None, True)
    xs = [p[0] for p in pts_region]
    ys = [p[1] for p in pts_region]
    x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    diag = math.hypot(x1 - x0, y1 - y0)
    r = random.Random(_seed_counter[0])
    lines = []
    t = -diag / 2
    flip = False
    while t < diag / 2:
        a, b = (-diag / 2, t), (diag / 2, t + r.uniform(-3, 3))
        if flip:
            a, b = b, a
        lines += [a, b]
        flip = not flip
        t += gap * r.uniform(0.85, 1.2)
    th = math.radians(angle_deg)
    rot = []
    for (px, py) in lines:
        rot.append((cx + px * math.cos(th) - py * math.sin(th),
                    cy + px * math.sin(th) + py * math.cos(th)))
    path = hand(rot, 1.2)
    return (f'<clipPath id="{cid}"><path d="{d_clip}"/></clipPath>'
            f'<g clip-path="url(#{cid})">' +
            st(path, color, w, "none", op) + "</g>\n")


def ellipse_pts(cx, cy, rx, ry, n=22, rot=0.0):
    th = math.radians(rot)
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        x, y = rx * math.cos(a), ry * math.sin(a)
        pts.append((cx + x * math.cos(th) - y * math.sin(th),
                    cy + x * math.sin(th) + y * math.cos(th)))
    return pts


def starburst(cx, cy, r_out, r_in, spikes, color, seed=7, rot=0.0):
    r = random.Random(seed)
    pts = []
    for i in range(spikes * 2):
        a = math.pi * i / spikes + math.radians(rot)
        rad = (r_out if i % 2 == 0 else r_in) * r.uniform(0.92, 1.08)
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    d = _smooth([p for p in pts], True)  # keep spikes sharp: use raw polygon
    poly = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"
    out = st(poly, color, 4.2, "#ffffff", 0.97)
    out += st("M " + " L ".join(
        f"{x + r.uniform(-2, 2):.1f},{y + r.uniform(-2, 2):.1f}"
        for x, y in pts) + " Z", color, 1.8, "none", 0.45)
    return out


def bubble(cx, cy, rx, ry, tail=None, color=INK, w=3.6):
    """White speech bubble. tail=(tip_x, tip_y)."""
    body = ellipse_pts(cx, cy, rx, ry, 26)
    out = st(hand(body, 3.2, None, True), color, w, "#ffffff", 0.97)
    if tail:
        tx, ty = tail
        a = math.atan2(ty - cy, tx - cx)
        ex = cx + rx * 0.92 * math.cos(a)
        ey = cy + ry * 0.92 * math.sin(a)
        perp = a + math.pi / 2
        w2 = 14
        p1 = (ex + w2 * math.cos(perp), ey + w2 * math.sin(perp))
        p2 = (ex - w2 * math.cos(perp), ey - w2 * math.sin(perp))
        d = (f"M {p1[0]:.1f},{p1[1]:.1f} Q "
             f"{(p1[0] + tx) / 2:.1f},{(p1[1] + ty) / 2:.1f} {tx:.1f},{ty:.1f} "
             f"Q {(p2[0] + tx) / 2:.1f},{(p2[1] + ty) / 2:.1f} "
             f"{p2[0]:.1f},{p2[1]:.1f}")
        out += st(d, color, w, "#ffffff")
    return out


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def T(x, y, s, size, font="AD", color=INK, rot=0.0, anchor="middle",
      ls=0.0, weight=None, op=1.0):
    fam = {"PM": "Permanent Marker", "AD": "Architects Daughter",
           "B2": "Baloo 2", "GH": "Gochi Hand"}[font]
    a = [f'x="{x}" y="{y}"', f"font-family=\"'{fam}'\"", f'font-size="{size}"',
         f'fill="{color}"', f'text-anchor="{anchor}"']
    if ls:
        a.append(f'letter-spacing="{ls}"')
    if weight:
        a.append(f'font-weight="{weight}"')
    if op != 1.0:
        a.append(f'opacity="{op}"')
    if rot:
        a.append(f'transform="rotate({rot} {x} {y})"')
    return f'<text {" ".join(a)}>{esc(s)}</text>\n'


# ------------------------------------------------------------------ the head

def head(cx, cy, s=1.0):
    """Robin Williams caricature. cx,cy = eye line center. Local units
    assume face half-width ~85 at s=1."""
    def P(pairs):  # local -> global
        return [(cx + x * s, cy + y * s) for (x, y) in pairs]

    o = f'<g>\n'

    # neck (behind face)
    o += blob(P([(-34, 85), (-42, 122), (-46, 162), (50, 162), (46, 120),
                 (38, 85)]), SKIN)
    o += ink(P([(-36, 100), (-42, 126), (-45, 158)]), INK, 3.2 * s)
    o += ink(P([(40, 98), (45, 124), (49, 158)]), INK, 3.2 * s)

    # ears (mostly behind hair/face edges)
    for sd in (-1, 1):
        o += blob(P([(sd * 82, -6), (sd * 98, 0), (sd * 96, 24),
                     (sd * 82, 30)]), SKIN)
        o += ink(P([(sd * 83, -4), (sd * 98, 2), (sd * 94, 24),
                    (sd * 82, 30)]), INK, 3.0 * s)
        o += ink(P([(sd * 90, 8), (sd * 87, 18)]), INK, 2.2 * s,
                 double=False)

    # face: broad, strong jaw, big rounded chin
    face = [(-84, -10), (-87, 20), (-81, 50), (-64, 78), (-34, 102),
            (0, 112), (32, 100), (63, 76), (80, 48), (87, 16), (84, -12),
            (76, -42), (60, -66), (30, -82), (0, -86), (-32, -82),
            (-62, -64), (-77, -40)]
    o += blob(P(face), SKIN)
    o += ink(P(face), INK, 3.6 * s, amp=1.4, closed=True)

    # under-chin / neck shadow
    o += scribble(P([(-22, 114), (24, 110), (30, 140), (-26, 142)]),
                  SKIN_SHADE, 30, 6.5, 4.0, 0.32)

    # forehead creases (brows-up joy)
    o += ink(P([(-26, -52), (0, -57), (26, -52)]), INK, 2.0 * s,
             double=False, op=0.45)
    o += ink(P([(-18, -63), (0, -67), (18, -63)]), INK, 1.7 * s,
             double=False, op=0.32)

    # ---- eyes (narrow, crinkled smile, heavy lids, blue iris)
    for sd, dy in ((-1, 0), (1, -2)):
        ecx = sd * 31
        up = [(ecx - 13, -4 + dy), (ecx, -12 + dy), (ecx + 13, -5 + dy)]
        lo = [(ecx - 13, 0 + dy), (ecx, 4 + dy), (ecx + 13, -1 + dy)]
        # iris clip lens
        _seed_counter[0] += 1
        cid = f"eye{_seed_counter[0]}"
        lens = P(up) + P(list(reversed(lo)))
        o += (f'<clipPath id="{cid}"><path d="{_smooth(lens, True)}"/>'
              f'</clipPath><g clip-path="url(#{cid})">')
        # iris sits low so lids clip it into a smiling crescent
        ix, iy = cx + (ecx + sd * 1) * s, cy + (-4 + dy) * s
        o += (f'<circle cx="{ix:.1f}" cy="{iy:.1f}" r="{7.2 * s:.1f}" '
              f'fill="#4a7fb5"/>')
        o += (f'<circle cx="{ix:.1f}" cy="{iy:.1f}" r="{3.2 * s:.1f}" '
              f'fill="{INK}"/>')
        o += (f'<circle cx="{ix + 2.4 * s:.1f}" cy="{iy - 2.4 * s:.1f}" '
              f'r="{1.7 * s:.1f}" fill="#fff"/>')
        o += "</g>\n"
        # lids
        o += ink(P(up), INK, 3.6 * s, amp=0.6)
        o += ink(P(lo), INK, 2.6 * s, amp=0.6, double=False)
        # heavy upper lid line
        o += ink(P([(ecx - 12, -9 + dy), (ecx, -16 + dy),
                    (ecx + 12, -10 + dy)]), INK, 2.0 * s, amp=0.5,
                 double=False, op=0.6)
        # under-eye smile bag (one strong, one faint)
        o += ink(P([(ecx - 11, 8 + dy), (ecx, 12 + dy),
                    (ecx + 10, 8 + dy)]), INK, 1.9 * s, amp=0.5,
                 double=False, op=0.5)
        o += ink(P([(ecx - 7, 15 + dy), (ecx + 3, 17 + dy)]), INK,
                 1.5 * s, amp=0.5, double=False, op=0.28)
        # crow's feet: two short rays fanning from the outer corner
        xo = ecx + sd * 15
        o += ink(P([(xo, -4 + dy), (xo + sd * 7, -8 + dy)]), INK,
                 1.7 * s, amp=0.3, double=False, op=0.45)
        o += ink(P([(xo, 0 + dy), (xo + sd * 8, 3 + dy)]), INK,
                 1.7 * s, amp=0.3, double=False, op=0.45)

    # brows: thick, bushy, expressive; right raised higher
    o += ink(P([(-54, -16), (-36, -26), (-13, -21)]), "#3a2414", 7.4 * s,
             amp=0.8)
    o += ink(P([(-46, -14), (-34, -21), (-22, -19)]), "#3a2414", 2.8 * s,
             amp=0.8, double=False, op=0.6)
    o += ink(P([(11, -24), (34, -35), (56, -22)]), "#3a2414", 7.4 * s,
             amp=0.8)
    o += ink(P([(16, -21), (34, -29), (50, -19)]), "#3a2414", 2.8 * s,
             amp=0.8, double=False, op=0.6)

    # ---- nose: one continuous outline — long bridge into big round ball
    o += ink(P([(-8, -22), (-11, -2), (-17, 12), (-24, 22), (-22, 33),
                (-12, 42), (0, 44), (12, 42), (22, 32), (24, 21),
                (17, 11), (11, 0)]), INK, 3.5 * s, amp=0.8)
    # nostril wings: small open C-arcs outside the ball
    o += ink(P([(-25, 29), (-31, 35), (-25, 43)]), INK, 2.8 * s, amp=0.5,
             double=False)
    o += ink(P([(25, 29), (31, 35), (26, 43)]), INK, 2.8 * s, amp=0.5,
             double=False)
    # nostrils: two short dark dabs under the ball
    o += ink(P([(-10, 40), (-14, 41)]), INK, 4.2 * s, double=False)
    o += ink(P([(10, 40), (14, 41)]), INK, 4.2 * s, double=False)

    # nasolabial folds: deep parentheses sweeping OUTSIDE the grin corners
    o += ink(P([(-30, 30), (-46, 39), (-59, 50), (-64, 60)]), INK,
             2.6 * s, amp=0.7, double=False, op=0.75)
    o += ink(P([(30, 30), (46, 38), (57, 47), (60, 53)]), INK, 2.6 * s,
             amp=0.7, double=False, op=0.75)

    # ---- mouth: wide open grin (compact, chin stays visible)
    upper = [(-56, 60), (-28, 54), (0, 52), (30, 51), (58, 56)]
    teeth_bot = [(-51, 72), (-17, 78), (17, 77), (52, 67)]
    inner_lo = [(-46, 80), (0, 88), (48, 74)]
    outer_lo = [(-52, 85), (0, 97), (54, 80)]
    # mouth interior (between teeth and lower lip)
    o += blob(P(teeth_bot + list(reversed(inner_lo))), "#5a2020")
    # teeth band
    o += blob(P(upper + list(reversed(teeth_bot))), "#f8f2e0")
    # teeth separators
    for tx in (-38, -19, 0, 19, 38):
        o += ink(P([(tx, 53 + abs(tx) * 0.12), (tx, 75 - abs(tx) * 0.10)]),
                 INK, 1.3 * s, amp=0.3, double=False, op=0.4)
    o += ink(P(teeth_bot), INK, 2.2 * s, amp=0.5, double=False, op=0.85)
    # lower lip
    o += blob(P(inner_lo + list(reversed(outer_lo))), "#e8a583")
    o += ink(P(outer_lo), INK, 3.2 * s, amp=0.7)
    # upper lip line
    o += ink(P(upper), INK, 3.9 * s, amp=0.7)
    # grin corner brackets tucking into cheeks
    o += ink(P([(-58, 52), (-63, 61), (-59, 71)]), INK, 2.5 * s, amp=0.5,
             double=False)
    o += ink(P([(60, 48), (65, 56), (61, 66)]), INK, 2.5 * s, amp=0.5,
             double=False)
    # jowl hints below mouth corners
    o += ink(P([(-54, 79), (-47, 90)]), INK, 1.8 * s, amp=0.4,
             double=False, op=0.5)
    o += ink(P([(56, 74), (50, 84)]), INK, 1.8 * s, amp=0.4,
             double=False, op=0.5)

    # chin crease
    o += ink(P([(-14, 98), (0, 103), (14, 97)]), INK, 2.0 * s,
             double=False, op=0.5)

    # cheeks
    o += blob(P(ellipse_pts(-64, 30, 13, 7, 14, -15)), "#e2937a", op=0.10)
    o += blob(P(ellipse_pts(66, 27, 13, 7, 14, 15)), "#e2937a", op=0.10)

    # ---- hair: thick dark-brown waves, high receding temples, soft peak
    hair_sil = [(-88, 24), (-90, -14), (-99, -44), (-96, -78), (-74, -104),
                (-42, -122), (-10, -128), (22, -126), (54, -114), (82, -94),
                (95, -64), (97, -32), (90, -8), (86, 22),
                # inner hairline (right -> left): high temples, soft peak
                (79, 0), (72, -34), (62, -58), (40, -80), (14, -66),
                (0, -63), (-16, -67), (-42, -82), (-64, -60), (-72, -36),
                (-80, -2)]
    o += blob(P(hair_sil), HAIR)
    o += ink(P(hair_sil), HAIR_DK, 3.0 * s, amp=2.0, closed=True)
    # flowing wave strokes
    waves = [
        [(-58, -66), (-76, -84), (-88, -62)],
        [(-28, -76), (-48, -102), (-76, -96)],
        [(-2, -66), (-16, -98), (-42, -112)],
        [(4, -94), (-10, -114), (-30, -120)],
        [(24, -76), (18, -106), (-2, -120)],
        [(48, -80), (54, -102), (34, -114)],
        [(66, -60), (82, -82), (66, -102)],
        [(80, -44), (92, -58), (88, -78)],
        [(-80, -24), (-91, -44), (-88, -64)],
        [(82, -14), (91, -28), (92, -48)],
    ]
    for wv in waves:
        o += ink(P(wv), HAIR_DK, 2.5 * s, amp=1.4, double=False, op=0.75)
    # sideburns
    o += scribble(P([(-88, 0), (-80, 0), (-82, 28), (-89, 26)]), HAIR_DK,
                  80, 4, 2.5, 0.7)
    o += scribble(P([(80, -2), (88, -2), (88, 26), (82, 26)]), HAIR_DK,
                  80, 4, 2.5, 0.7)

    o += "</g>\n"
    return o


# --------------------------------------------------------------- assembly

def svg_face_test():
    b = [f'<rect width="900" height="1000" fill="{PAPER}"/>']
    b.append(head(450, 430, 3.0))
    return wrap("".join(b), 900, 1000)


def wrap(body, w, h):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" '
            f'height="{h}" viewBox="0 0 {w} {h}">\n{body}</svg>\n')


def emit(svg, w, h, name="poster"):
    here = os.path.dirname(os.path.abspath(__file__))
    fd = os.path.relpath(font_dir(), here).replace(os.sep, "/")
    css = (
        f"@font-face {{ font-family:'Permanent Marker'; "
        f"src:url('{fd}/PermanentMarker.ttf'); }}\n"
        f"@font-face {{ font-family:'Architects Daughter'; "
        f"src:url('{fd}/ArchitectsDaughter.ttf'); }}\n"
        f"@font-face {{ font-family:'Baloo 2'; font-weight:800; "
        f"src:url('{fd}/Baloo2-800.woff2') format('woff2'); }}\n")
    with open(os.path.join(here, f"{name}.svg"), "w") as f:
        f.write(svg)
    html = (f"<!doctype html><html><head><meta charset='utf-8'><style>"
            f"{css} html,body{{margin:0;padding:0}}</style>"
            f"</head><body>{svg}</body></html>")
    with open(os.path.join(here, f"{name}.html"), "w") as f:
        f.write(html)
    print(f"wrote {name}.svg / {name}.html ({w}x{h})")


# ------------------------------------------------------------ poster pieces

def G(cx, cy, rot, inner):
    return (f'<g transform="translate({cx},{cy}) rotate({rot})">'
            f'{inner}</g>\n')


def case_xbox():
    o = ""
    body = [(-72, -102), (72, -102), (72, 102), (-72, 102)]
    o += blob(body, "#3f7d28", amp=2)
    o += ink(body, INK, 4.0, amp=2, closed=True)
    o += blob([(-72, -102), (72, -102), (72, -76), (-72, -76)], "#1b3517")
    o += ink([(-72, -76), (72, -76)], INK, 2.6, double=False)
    # X orb logo + XBOX
    o += f'<circle cx="-48" cy="-89" r="10" fill="#8ec63f"/>'
    o += ink([(-54, -95), (-42, -83)], INK, 3.0, double=False)
    o += ink([(-42, -95), (-54, -83)], INK, 3.0, double=False)
    o += T(8, -81, "XBOX", 21, "PM", "#ffffff", -1)
    # art: murky scene with vague armored soldier
    art = [(-60, -64), (60, -64), (60, 90), (-60, 90)]
    o += blob(art, "#2a481f")
    o += scribble(art, "#1c3313", 30, 10, 6, 0.5)
    o += blob(ellipse_pts(-16, -8, 22, 20, 16), "#3d5233")   # helmet
    o += ink(ellipse_pts(-16, -8, 22, 20, 16), INK, 2.6, closed=True,
             double=False)
    o += ink([(-29, -8), (-3, -8)], "#d98a2b", 6.0, double=False)  # visor
    o += blob([(-50, 12), (20, 12), (28, 56), (-56, 56)], "#22381a")
    o += ink([(-50, 12), (20, 12), (28, 56), (-56, 56)], INK, 2.4,
             closed=True, double=False)
    o += ink([(-30, 66), (30, 66)], "#1c3313", 5, double=False, op=0.8)
    return o


def case_gow():
    o = ""
    body = [(-72, -102), (72, -102), (72, 102), (-72, 102)]
    o += blob(body, "#d9c9a8", amp=2)
    o += ink(body, INK, 4.0, amp=2, closed=True)
    o += blob([(-72, -102), (72, -102), (72, -80), (-72, -80)], "#f5f2ea")
    o += ink([(-72, -80), (72, -80)], INK, 2.6, double=False)
    o += T(0, -87, "PlayStation.2", 15, "AD", INK)
    o += scribble([(-68, -74), (68, -74), (68, 98), (-68, 98)],
                  "#b8a480", 40, 12, 5, 0.35)
    # GOD (omega) WAR
    o += T(-34, -42, "GOD", 26, "PM", RED, -2)
    o += T(40, -42, "WAR", 26, "PM", RED, 2)
    om = ellipse_pts(2, -50, 9, 9, 12)[2:11]      # open-bottom omega arc
    o += ink(om, RED, 3.2, double=False)
    o += ink([(-8, -42), (-2, -42)], RED, 3.2, double=False)
    o += ink([(6, -42), (12, -42)], RED, 3.2, double=False)
    # Kratos: bald, red stripe, chained blades
    o += blob(ellipse_pts(0, -8, 13, 14, 14), "#e8dcc8")
    o += ink(ellipse_pts(0, -8, 13, 14, 14), INK, 2.4, closed=True,
             double=False)
    o += ink([(-3, -21), (-8, -12), (-9, -2)], RED, 4.5, double=False)
    o += ink([(-8, -10), (-2, -12)], INK, 2.0, double=False)   # brow
    o += ink([(3, -12), (9, -10)], INK, 2.0, double=False)
    o += ink([(-3, 1), (0, 3), (3, 1)], INK, 2.0, double=False)  # goatee
    o += blob([(-26, 8), (26, 8), (15, 56), (-15, 56)], "#e0d2ba")
    o += ink([(-26, 8), (26, 8), (15, 56), (-15, 56)], INK, 2.4,
             closed=True, double=False)
    o += ink([(-14, 12), (-6, 20), (-12, 30)], RED, 3.5, double=False)
    o += ink([(-26, 10), (-42, 24), (-46, 36)], INK, 2.6, double=False)
    o += ink([(26, 10), (42, 22), (45, 34)], INK, 2.6, double=False)
    o += ink([(-52, 34), (-44, 42), (-50, 48)], "#8a8f96", 3.5,
             double=False)
    o += ink([(52, 32), (44, 40), (50, 46)], "#8a8f96", 3.5, double=False)
    o += blob([(-15, 56), (15, 56), (13, 76), (-13, 76)], "#5a4632")
    o += ink([(-30, 84), (30, 84)], "#b8a480", 5, double=False, op=0.7)
    return o


def case_ssb():
    o = ""
    body = [(-72, -102), (72, -102), (72, 102), (-72, 102)]
    o += blob(body, "#181820", amp=2)
    o += ink(body, INK, 4.0, amp=2, closed=True)
    o += blob([(-72, -102), (72, -102), (72, -82), (-72, -82)], "#4a3d68")
    o += ink([(-72, -82), (72, -82)], INK, 2.4, double=False)
    o += T(0, -88, "NINTENDO GAMECUBE", 12.5, "AD", "#ffffff", 0, ls=1)
    # smash cross logo
    o += f'<circle cx="52" cy="-62" r="11" fill="none" stroke="#ffffff" stroke-width="2.6"/>'
    o += ink([(41, -62), (63, -62)], "#ffffff", 2.4, double=False)
    o += ink([(52, -73), (52, -51)], "#ffffff", 2.4, double=False)
    # title with red drop shadow
    o += T(2, -52, "SUPER", 25, "PM", RED, -2)
    o += T(0, -54, "SUPER", 25, "PM", "#f5b81e", -2)
    o += T(2, -22, "SMASH BROS", 24, "PM", RED, -1)
    o += T(0, -24, "SMASH BROS", 24, "PM", "#f5b81e", -1)
    # Mario face
    o += blob(ellipse_pts(0, 46, 27, 24, 18), "#f2c79e")       # face
    o += ink(ellipse_pts(0, 46, 27, 24, 18), INK, 2.6, closed=True,
             double=False)
    o += blob([(-30, 26), (-18, 6), (8, 0), (28, 10), (32, 26),
               (-32, 30)], RED)                                # cap
    o += ink([(-30, 26), (-18, 6), (8, 0), (28, 10), (32, 26)], INK, 2.6,
             double=False)
    o += ink([(-34, 28), (34, 28)], INK, 3.0, double=False)    # brim
    o += f'<circle cx="0" cy="14" r="8" fill="#ffffff" stroke="{INK}" stroke-width="2"/>'
    o += T(0, 19, "M", 13, "PM", RED)
    o += f'<circle cx="-9" cy="40" r="3.4" fill="{BLUE}"/>'
    o += f'<circle cx="9" cy="40" r="3.4" fill="{BLUE}"/>'
    o += blob(ellipse_pts(0, 50, 8, 6, 12), "#e8a583")         # nose
    o += ink(ellipse_pts(0, 50, 8, 6, 12), INK, 2.2, closed=True,
             double=False)
    o += ink([(-16, 56), (-8, 60), (0, 58), (8, 60), (16, 56)], INK, 4.5,
             double=False)                                     # mustache
    o += ink([(-10, 66), (0, 69), (10, 66)], INK, 2.0, double=False)
    # sparkle stars
    for (sx, sy) in ((-52, -66), (-40, 60), (52, 40), (40, 80)):
        o += ink([(sx - 4, sy), (sx + 4, sy)], "#ffffff", 2, double=False,
                 op=0.8)
        o += ink([(sx, sy - 4), (sx, sy + 4)], "#ffffff", 2, double=False,
                 op=0.8)
    return o


def case_crash():
    o = ""
    body = [(-72, -102), (72, -102), (72, 102), (-72, 102)]
    o += blob(body, "#141414", amp=2)
    o += ink(body, INK, 4.0, amp=2, closed=True)
    # spine
    o += blob([(-72, -102), (-52, -102), (-52, 102), (-72, 102)], "#2a2a2a")
    o += ink([(-52, -102), (-52, 102)], INK, 2.2, double=False)
    o += (f'<text x="-58" y="0" font-family="Architects Daughter" '
          f'font-size="12" fill="#ffffff" text-anchor="middle" '
          f'transform="rotate(-90 -58 0)">PlayStation</text>\n')
    # sunburst art
    art = [(-50, -100), (70, -100), (70, 100), (-50, 100)]
    _seed_counter[0] += 1
    cid = f"crash{_seed_counter[0]}"
    o += (f'<clipPath id="{cid}"><path d="{hand(art, 1.5, None, True)}"/>'
          f'</clipPath><g clip-path="url(#{cid})">')
    o += blob(art, "#b05816")
    for k in range(8):
        a1 = math.pi * 2 * k / 8 + 0.12
        a2 = a1 + 0.26
        o += blob([(10, 25),
                   (10 + 190 * math.cos(a1), 25 + 190 * math.sin(a1)),
                   (10 + 190 * math.cos(a2), 25 + 190 * math.sin(a2))],
                  "#e8892c", op=0.85)
    o += "</g>\n"
    # title
    o += T(12, -56, "CRASH", 30, "PM", "#3a1c08", -2)
    o += T(10, -58, "CRASH", 30, "PM", "#f7c832", -2)
    o += T(10, -34, "BANDICOOT", 15, "PM", "#f7c832", -1)
    # Crash face
    o += blob([(-14, -4), (8, -10), (30, -4), (44, 14), (46, 34),
               (34, 58), (8, 70), (-18, 58), (-28, 34), (-26, 14)],
              "#e88024")
    o += ink([(-14, -4), (8, -10), (30, -4), (44, 14), (46, 34),
              (34, 58), (8, 70), (-18, 58), (-28, 34), (-26, 14)],
             INK, 2.8, closed=True, double=False)
    # ears
    o += blob([(-22, 0), (-34, -22), (-14, -8)], "#e88024")
    o += ink([(-22, 0), (-34, -22), (-14, -8)], INK, 2.4, double=False)
    o += blob([(28, -4), (44, -24), (40, -2)], "#e88024")
    o += ink([(28, -4), (44, -24), (40, -2)], INK, 2.4, double=False)
    # hair spikes
    o += blob([(-10, -8), (-4, -22), (2, -8), (8, -24), (16, -8),
               (24, -18), (26, -6)], "#6b3410")
    o += ink([(-10, -8), (-4, -22), (2, -8), (8, -24), (16, -8),
              (24, -18), (26, -6)], INK, 2.2, double=False)
    # brows + green eyes
    o += ink([(-19, 11), (-4, 7)], INK, 3.2, double=False)
    o += ink([(11, 6), (26, 9)], INK, 3.2, double=False)
    o += blob(ellipse_pts(-9, 23, 7, 9.5, 12), "#eef7dc")
    o += blob(ellipse_pts(17, 22, 7, 9.5, 12), "#eef7dc")
    o += ink(ellipse_pts(-9, 23, 7, 9.5, 12), INK, 1.8, closed=True,
             double=False)
    o += ink(ellipse_pts(17, 22, 7, 9.5, 12), INK, 1.8, closed=True,
             double=False)
    o += f'<circle cx="-8" cy="25" r="3.4" fill="#4a8028"/>'
    o += f'<circle cx="18" cy="24" r="3.4" fill="#4a8028"/>'
    o += f'<circle cx="-8" cy="25" r="1.6" fill="{INK}"/>'
    o += f'<circle cx="18" cy="24" r="1.6" fill="{INK}"/>'
    # muzzle + nose + big grin with tongue
    o += blob(ellipse_pts(7, 50, 28, 19, 16), "#f5c890")
    o += ink(ellipse_pts(7, 50, 28, 19, 16), INK, 2.2, closed=True,
             double=False)
    o += blob(ellipse_pts(7, 36, 7, 5, 10), INK)
    o += blob([(-14, 46), (28, 43), (24, 58), (-4, 61)], "#8a2020")
    o += ink([(-14, 46), (28, 43), (24, 58), (-4, 61)], INK, 2.2,
             closed=True, double=False)
    o += ink([(-11, 48), (26, 45)], "#ffffff", 4.5, double=False)
    o += blob(ellipse_pts(10, 58, 9, 5, 10), "#d04848")
    return o


def n64_controller(cx, cy, rot):
    o = ""
    body = [(-98, -8), (-112, 40), (-86, 84), (-58, 50), (-38, 38),
            (-24, 32), (-16, 76), (0, 92), (16, 76), (24, 32), (38, 38),
            (58, 50), (86, 84), (112, 40), (98, -8), (58, -34), (0, -42),
            (-58, -34)]
    o += blob(body, "#9aa0a8", amp=2)
    o += ink(body, INK, 3.8, amp=1.8, closed=True)
    # d-pad
    o += ink([(-72, 4), (-46, 4)], "#3c4046", 10, double=False)
    o += ink([(-59, -9), (-59, 17)], "#3c4046", 10, double=False)
    # start
    o += f'<circle cx="0" cy="2" r="8" fill="{RED}" stroke="{INK}" stroke-width="2"/>'
    # analog stick
    o += f'<circle cx="0" cy="44" r="12" fill="#6e747c" stroke="{INK}" stroke-width="2.4"/>'
    o += f'<circle cx="0" cy="44" r="5" fill="#3c4046"/>'
    # buttons
    o += f'<circle cx="50" cy="22" r="10" fill="{BLUE}" stroke="{INK}" stroke-width="2"/>'
    o += f'<circle cx="34" cy="4" r="9" fill="{GREEN}" stroke="{INK}" stroke-width="2"/>'
    for (bx, by) in ((66, -18), (54, -4), (78, -4), (66, 10)):
        o += (f'<circle cx="{bx}" cy="{by}" r="5.5" fill="{YELLOW}" '
              f'stroke="{INK}" stroke-width="1.8"/>')
    # cable
    o += ink([(0, -42), (-16, -60), (-4, -78), (-20, -96)], "#3c4046",
             3.5, double=False)
    return G(cx, cy, rot, o)


def gameboy(cx, cy, rot):
    o = ""
    body = [(-54, -84), (54, -84), (54, 56), (32, 84), (-54, 84)]
    o += blob(body, "#c2c6cc", amp=1.5)
    o += ink(body, INK, 3.6, amp=1.5, closed=True)
    o += blob([(-42, -74), (42, -74), (42, -8), (-42, -8)], "#565a64")
    o += ink([(-42, -74), (42, -74), (42, -8), (-42, -8)], INK, 2.6,
             closed=True, double=False)
    o += blob([(-26, -62), (28, -62), (28, -18), (-26, -18)], "#9aa86b")
    o += ink([(-26, -62), (28, -62), (28, -18), (-26, -18)], INK, 2.0,
             closed=True, double=False)
    o += blob([(-12, -50), (14, -50), (14, -30), (-12, -30)], "#6e7a4a")
    o += f'<circle cx="-35" cy="-40" r="3" fill="{RED}"/>'
    o += T(0, 6, "GAME BOY", 12, "AD", "#33363c", 0, ls=1)
    # d-pad
    o += ink([(-38, 34), (-14, 34)], "#33363c", 9, double=False)
    o += ink([(-26, 22), (-26, 46)], "#33363c", 9, double=False)
    # A/B
    o += f'<circle cx="30" cy="26" r="8" fill="#a83a6e" stroke="{INK}" stroke-width="2"/>'
    o += f'<circle cx="10" cy="36" r="8" fill="#a83a6e" stroke="{INK}" stroke-width="2"/>'
    # start/select
    o += ink([(-14, 64), (-2, 60)], "#6e747c", 5, double=False)
    o += ink([(4, 62), (16, 58)], "#6e747c", 5, double=False)
    # speaker
    for k in range(5):
        o += ink([(24 + k * 5, 78 - k * 3 - 6), (30 + k * 5, 78 - k * 3)],
                 "#8a8f96", 2.5, double=False)
    return G(cx, cy, rot, o)


def flower(x, y, r, rot=0):
    o = ""
    for k in range(5):
        a = math.radians(rot + k * 72)
        px, py = x + r * 0.85 * math.cos(a), y + r * 0.85 * math.sin(a)
        o += blob(ellipse_pts(px, py, r * 0.55, r * 0.38, 10,
                              rot + k * 72), "#f4eee0", op=0.95)
        o += ink(ellipse_pts(px, py, r * 0.55, r * 0.38, 10,
                             rot + k * 72), "#d8c8a8", 1.4, closed=True,
                 double=False, op=0.8)
    o += f'<circle cx="{x}" cy="{y}" r="{r * 0.2:.1f}" fill="{RED}"/>'
    return o


def hand_fingers(x, y, sd):
    """Four fingers curling over a case edge + thumb. sd=1 fingers point
    right (left hand), sd=-1 mirrored."""
    o = ""
    for k in range(4):
        fy = y + k * 13
        fl = 34 - abs(k - 1.5) * 3
        pts = [(x, fy), (x + sd * fl, fy + 3), (x + sd * fl, fy + 11),
               (x, fy + 12)]
        o += blob(pts, SKIN)
        o += ink([(x, fy), (x + sd * fl, fy + 3),
                  (x + sd * fl * 0.98, fy + 11), (x, fy + 12)], INK, 2.8,
                 amp=0.8, double=False)
    # thumb hooks up the side
    o += blob([(x - sd * 4, y + 50), (x - sd * 16, y + 30),
               (x - sd * 10, y + 12), (x + sd * 2, y + 16),
               (x + sd * 2, y + 48)], SKIN)
    o += ink([(x - sd * 4, y + 52), (x - sd * 16, y + 30),
              (x - sd * 10, y + 12), (x + sd * 2, y + 16)], INK, 2.8,
             amp=0.8, double=False)
    return o


def svg_full():
    W, H = 1480, 1180
    b = [f'<rect width="{W}" height="{H}" fill="{PAPER}"/>']
    r = random.Random(9)
    for _ in range(5):  # subtle paper mottling
        b.append(blob(ellipse_pts(r.uniform(100, 1380), r.uniform(100, 1080),
                                  r.uniform(80, 200), r.uniform(60, 140),
                                  14), "#f2e9d6", op=0.35))

    # ---------------- header
    b.append(T(740, 94, "VIDEO GAMES!", 82, "PM", INK, -0.5, ls=3))
    b.append(squig(420, 700, 114, RED, 4.5))
    b.append(squig(735, 1065, 114, RED, 4.5))
    b.append(T(740, 156, "ON", 34, "PM", INK, 0, ls=4))
    b.append(T(740, 244, "whatnot", 92, "B2", "#111111", -1.5,
               weight=800))
    # yellow rays around the logo
    for (ax, ay, bx2, by2) in ((618, 206, 596, 184), (648, 190, 634, 164),
                               (688, 178, 680, 152), (740, 172, 740, 146),
                               (792, 178, 800, 152), (832, 190, 846, 164),
                               (862, 206, 884, 184), (600, 236, 572, 228),
                               (880, 236, 908, 228)):
        b.append(ink([(ax, ay), (bx2, by2)], YELLOW, 5.5, amp=0.5,
                     double=False))

    # ---------------- corner starbursts
    b.append(starburst(152, 148, 112, 82, 13, RED, 3))
    b.append(T(152, 140, "GAMES!", 33, "PM", RED, -5))
    b.append(T(152, 176, "So many!", 24, "AD", INK, -3))
    b.append(squig(108, 196, 186, RED, 3.2))
    b.append(starburst(1292, 138, 106, 78, 12, RED, 5))
    b.append(T(1292, 130, "PLAY!", 35, "PM", RED, 4))
    b.append(T(1292, 166, "So good!", 23, "AD", INK, 2))
    b.append(squig(1248, 1336, 186, RED, 3.2))

    # ---------------- speech bubbles
    b.append(bubble(300, 330, 138, 108, (540, 380), GREEN))
    for i, ln in enumerate(["JUMANJI!", "NINTENDO!", "CHAOS!", "GENESIS",
                            "DOES!"]):
        b.append(T(300, 268 + i * 32, ln, 26, "AD", INK, -1))

    b.append(bubble(180, 560, 145, 102, (395, 600), BLUE))
    b.append(T(180, 522, "IT'S A", 25, "AD", INK, -1))
    b.append(T(180, 554, "GAME-TASTROPHE!", 24, "AD", INK, -1))
    b.append(squig(72, 288, 562, RED, 3))
    b.append(T(180, 586, "BUT IN A GOOD", 24, "AD", INK, -1))
    b.append(T(180, 618, "WAY!!!", 25, "AD", INK, -1))
    b.append(squig(138, 224, 626, BLUE, 3))

    b.append(bubble(1150, 292, 162, 148, (945, 400), BLUE))
    quotes = ["CARPE DIEM!", "SEIZE THE CONTROLLER!", "YOU'RE ONLY A",
              "HIGH BID AWAY", "FROM GREATNESS!", "OOH BANANA!",
              "FLY, YOU FOOLS!", "BID NOW!!"]
    for i, ln in enumerate(quotes):
        b.append(T(1150, 190 + i * 31, ln, 23, "AD", INK, 0.5))
    b.append(squig(1096, 1204, 416, RED, 3))
    b.append(squig(1108, 1192, 424, BLUE, 2.6))

    b.append(bubble(1352, 548, 104, 112, (1210, 572), GREEN))
    green_lines = [("MAKE", None), ("YOUR LIFE", None), ("EXTRA!", GREEN),
                   ("EXTRA!", GREEN), ("LEVEL!", GREEN)]
    for i, (ln, ul) in enumerate(green_lines):
        yy = 486 + i * 33
        b.append(T(1352, yy, ln, 25, "AD", INK, 1))
        if ul:
            b.append(squig(1352 - 40, 1352 + 40, yy + 8, GREEN, 3))

    b.append(bubble(1330, 736, 84, 64, (1300, 812), YELLOW))
    b.append(T(1330, 726, "NANU", 26, "AD", INK, 1))
    b.append(T(1330, 760, "NANU!", 26, "AD", INK, 1))
    b.append(squig(1290, 1372, 768, RED, 3))

    # ---------------- yellow $1 starburst
    b.append(starburst(162, 806, 128, 94, 12, ORANGE, 11))
    b.append(starburst(162, 806, 116, 86, 12, YELLOW, 12))
    b.append(T(162, 756, "EVERYTHING", 25, "AD", BLUE, -2))
    b.append(T(162, 786, "STARTS AT", 25, "AD", BLUE, -1))
    b.append(T(120, 864, "$", 62, "PM", RED, -4))
    b.append(T(176, 864, "1", 78, "PM", BLUE, 2))
    b.append(ink([(157, 830), (172, 810)], BLUE, 6, amp=0.5,
                 double=False))
    b.append(ink([(156, 866), (196, 864)], BLUE, 6, amp=0.5,
                 double=False))
    b.append(T(162, 902, "BUCK!", 27, "PM", RED, -2))

    # ---------------- the man himself
    HX, HY, S = 730, 398, 0.92
    b.append(head(HX, HY, S))

    # torso + collar
    torso = [(692, 532), (640, 546), (582, 574), (556, 622), (546, 692),
             (540, 800), (925, 800), (918, 690), (908, 620), (884, 572),
             (830, 544), (776, 530), (735, 545)]
    b.append(blob(torso, SHIRT, amp=2))
    # sleeves
    slv_l = [(600, 556), (640, 590), (540, 706), (497, 668)]
    slv_r = [(866, 588), (906, 553), (972, 665), (930, 702)]
    b.append(blob(slv_l, SHIRT, amp=2))
    b.append(blob(slv_r, SHIRT, amp=2))
    # flowers clipped to shirt
    _seed_counter[0] += 1
    cid = f"shirt{_seed_counter[0]}"
    b.append(f'<clipPath id="{cid}">'
             f'<path d="{hand(torso, 1.5, None, True)}"/>'
             f'<path d="{hand(slv_l, 1.5, None, True)}"/>'
             f'<path d="{hand(slv_r, 1.5, None, True)}"/></clipPath>')
    fl = f'<g clip-path="url(#{cid})">'
    fl += scribble(torso, SHIRT_DK, 25, 14, 7, 0.25)
    for (fx, fy, fr, frot) in ((606, 626, 18, 10), (688, 706, 20, 40),
                               (772, 648, 17, 70), (852, 726, 19, 20),
                               (700, 778, 17, 55), (870, 610, 15, 0),
                               (612, 762, 16, 30), (570, 690, 14, 60),
                               (940, 660, 15, 45), (520, 660, 13, 15)):
        fl += flower(fx, fy, fr, frot)
        fl += ink([(fx + fr, fy + fr), (fx + fr + 12, fy + fr + 8)],
                  "#1d4a73", 3, double=False, op=0.8)
    for (dx, dy) in ((650, 660), (740, 620), (820, 690), (600, 730),
                     (890, 760), (750, 740), (560, 620), (950, 620)):
        fl += f'<circle cx="{dx}" cy="{dy}" r="3.4" fill="{RED}" opacity="0.85"/>'
    fl += "</g>\n"
    b.append(fl)
    # outlines after pattern
    b.append(ink(torso, INK, 4.0, amp=1.8, closed=True))
    b.append(ink(slv_l, INK, 3.8, amp=1.5, closed=True))
    b.append(ink(slv_r, INK, 3.8, amp=1.5, closed=True))
    # sleeve hems
    b.append(ink([(532, 694), (497, 662)], INK, 3.0, double=False))
    b.append(ink([(938, 694), (975, 662)], INK, 3.0, double=False))
    # collar flaps + V + chest hair
    b.append(blob([(694, 528), (656, 556), (680, 594), (718, 570)], SHIRT))
    b.append(ink([(694, 528), (656, 556), (680, 594), (718, 570),
                  (700, 546)], INK, 3.4, amp=1, closed=True))
    b.append(blob([(774, 526), (812, 550), (792, 590), (754, 566)], SHIRT))
    b.append(ink([(774, 526), (812, 550), (792, 590), (754, 566),
                  (766, 544)], INK, 3.4, amp=1, closed=True))
    b.append(blob([(718, 570), (736, 540), (754, 566), (737, 604)], SKIN))
    b.append(ink([(718, 570), (737, 604), (754, 566)], INK, 3.0,
                 double=False))
    for (hx2, hy2) in ((728, 578), (738, 588), (730, 594)):
        b.append(ink([(hx2, hy2), (hx2 + 5, hy2 - 4), (hx2 + 8, hy2 + 2)],
                     "#5a3418", 2.0, double=False))
    # placket + buttons
    b.append(ink([(737, 604), (741, 700), (743, 798)], INK, 3.0,
                 double=False))
    for byy in (650, 706, 762):
        b.append(f'<circle cx="{740}" cy="{byy}" r="4" fill="#f4eee0" '
                 f'stroke="{INK}" stroke-width="1.6"/>')

    # forearms poking from sleeves (hairy!)
    arm_l = [(516, 688), (543, 712), (492, 730), (470, 700)]
    arm_r = [(925, 690), (960, 666), (1004, 700), (955, 724)]
    b.append(blob(arm_l, SKIN))
    b.append(ink(arm_l, INK, 3.2, amp=1, closed=True))
    b.append(blob(arm_r, SKIN))
    b.append(ink(arm_r, INK, 3.2, amp=1, closed=True))
    for (ax, ay) in ((500, 700), (512, 706), (524, 700), (492, 712),
                     (506, 716)):
        b.append(ink([(ax, ay), (ax + 6, ay - 5)], "#6b4423", 1.8,
                     double=False))
    for (ax, ay) in ((944, 690), (956, 686), (968, 692), (950, 702),
                     (964, 704)):
        b.append(ink([(ax, ay), (ax + 6, ay - 4)], "#6b4423", 1.8,
                     double=False))

    # ---------------- game cases
    b.append(G(392, 572, -12, case_xbox()))
    b.append(G(500, 596, -4, case_gow()))
    b.append(G(936, 572, 3, case_ssb()))
    b.append(G(1090, 608, 14, case_crash()))

    # hands gripping the front cases
    b.append(hand_fingers(432, 668, 1))
    b.append(hand_fingers(1054, 674, -1))

    # ---------------- grass
    gr = random.Random(17)
    for gx in range(360, 1125, 38):
        base = 802 + gr.uniform(-6, 8)
        for k in range(5):
            bx2 = gx + gr.uniform(-16, 16)
            hh = gr.uniform(28, 54)
            lean = gr.uniform(-12, 12)
            b.append(ink([(bx2, base), (bx2 + lean * 0.4, base - hh * 0.6),
                          (bx2 + lean, base - hh)], GRASS, 3.2, amp=0.8,
                         double=False))
        b.append(ink([(gx - 18, base + 6), (gx + 18, base + 4)], GRASS,
                     2.6, amp=1.2, double=False, op=0.7))

    # ---------------- bottom lockup
    b.append(T(705, 868, "JOIN US ON", 40, "PM", INK, 0, ls=8))
    b.append(T(705, 936, "WHATNOT!", 64, "PM", RED, -1, ls=4))
    b.append(squig(560, 850, 952, RED, 4.5))
    b.append(T(700, 1022, "EXPRESS COLLECTIBLES", 56, "PM", INK, 0, ls=2))
    b.append(squig(405, 995, 1040, RED, 4.5))
    b.append(squig(425, 975, 1052, RED, 4.0))
    words = [("BUY", 480), ("SELL", 600), ("TRADE", 732), ("REPEAT!", 892)]
    for wtext, wx in words:
        b.append(T(wx, 1098, wtext, 38, "PM", INK, -1))
    for dx in (540, 666, 812):
        b.append(f'<circle cx="{dx}" cy="1086" r="5.5" fill="{RED}"/>')
    b.append(T(685, 1148, "FOLLOW & SAVE - YOU NEVER KNOW WHAT WE'LL PULL!",
               26, "AD", INK, 0))
    smx, smy = 1088, 1140
    b.append(f'<circle cx="{smx}" cy="{smy}" r="13" fill="none" '
             f'stroke="{INK}" stroke-width="2.6"/>')
    b.append(f'<circle cx="{smx - 4.5}" cy="{smy - 4}" r="1.8" fill="{INK}"/>')
    b.append(f'<circle cx="{smx + 4.5}" cy="{smy - 4}" r="1.8" fill="{INK}"/>')
    b.append(ink([(smx - 6, smy + 3), (smx, smy + 8), (smx + 6, smy + 3)],
                 INK, 2.4, double=False))

    # ---------------- N64 controller + Game Boy + arrow
    b.append(n64_controller(148, 1042, -7))
    b.append(gameboy(1296, 890, 7))

    arrow = [(1075, 1042), (1192, 978), (1192, 1008), (1452, 1008),
             (1452, 1078), (1192, 1078), (1192, 1108)]
    b.append(blob(arrow, "#ffffff", amp=2))
    b.append(ink(arrow, RED, 5.0, amp=2, closed=True))
    b.append(T(1310, 1032, "USER:", 26, "AD", INK, -1))
    b.append(T(1310, 1062, "EXPRESS", 27, "AD", INK, -1))
    b.append(T(1310, 1076 + 14, "COLLECTIBLES", 24, "AD", INK, -1))

    return wrap("".join(b), W, H)


def embed_fonts(svg):
    """Return the SVG with the three used fonts embedded as data URIs so
    the file renders anywhere on its own."""
    import base64
    fdir = font_dir()

    def b64(name):
        with open(os.path.join(fdir, name), "rb") as f:
            return base64.b64encode(f.read()).decode()

    css = (
        "<defs><style>"
        "@font-face{font-family:'Permanent Marker';"
        f"src:url(data:font/ttf;base64,{b64('PermanentMarker.ttf')}) "
        "format('truetype');}"
        "@font-face{font-family:'Architects Daughter';"
        f"src:url(data:font/ttf;base64,{b64('ArchitectsDaughter.ttf')}) "
        "format('truetype');}"
        "@font-face{font-family:'Baloo 2';font-weight:800;"
        f"src:url(data:font/woff2;base64,{b64('Baloo2-800.woff2')}) "
        "format('woff2');}"
        "</style></defs>\n")
    i = svg.index(">", svg.index("<svg")) + 1
    return svg[:i] + "\n" + css + svg[i:]


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    random.seed(42)
    if mode == "face":
        emit(svg_face_test(), 900, 1000, "face")
    else:
        svg = svg_full()
        emit(svg, 1480, 1180, "poster")
        here = os.path.dirname(os.path.abspath(__file__))
        out = os.path.join(here, "robin-williams-whatnot-flyer.svg")
        with open(out, "w") as f:
            f.write(embed_fonts(svg))
        print(f"wrote {out} (fonts embedded)")
