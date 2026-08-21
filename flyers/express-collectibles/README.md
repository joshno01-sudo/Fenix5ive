# Express Collectibles — "Video Games on Whatnot" flyer

A redraw of the hand-drawn marker flyer for the Express Collectibles
Whatnot stream, with the center portrait done as a proper Robin Williams
caricature (the wavy receding hair, heavy brows, crinkled smiling eyes, the
nose, and that grin) to match the Mrs. Doubtfire / Jumanji / Mork quote
bubbles around him.

## Files

| File | What it is |
| --- | --- |
| `robin-williams-whatnot-flyer.png` | 2960x2360 render — post this one |
| `robin-williams-whatnot-flyer.svg` | Vector master, fonts embedded, opens anywhere |
| `generate_flyer.py` | Rebuilds both from scratch (no dependencies) |

## Regenerating

```bash
python3 generate_flyer.py          # writes the SVG (+ poster.html preview)
```

The script needs only Python 3 and `curl` (it fetches its three Google
Fonts — Permanent Marker, Architects Daughter, Baloo 2 — into `fonts/` on
first run). Every line is drawn with seeded "hand wobble", so output is
reproducible. To change wording, prices, or bubble copy, edit the strings
in `svg_full()` and rerun.

To rasterize a PNG at print size:

```bash
chromium --headless --no-sandbox --hide-scrollbars \
    --window-size=1480,1180 --force-device-scale-factor=2 \
    --screenshot=robin-williams-whatnot-flyer.png \
    robin-williams-whatnot-flyer.svg
```

Like `FenixVault/`, this has nothing to do with the website — it just
lives in the repo too.
