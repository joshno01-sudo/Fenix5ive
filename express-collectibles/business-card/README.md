# Express Collectibles — Business Card

Neon-arcade business card for Express Collectibles (Neal Knebel, owner),
styled directly from www.expresscollectibles.com — same tokens as the site's
default "Miami Sunset" colorway: bg `#150f2e`, deep `#0b071a`, neon pink
`#ff3ea5`, electric cyan `#29e6ff`, arcade gold `#ffc857`, chrome-gradient
italic wordmark, category ticker bar, synthwave grid floor. Front carries the
full contact block and every selling/social handle; the back is a "SCAN ME"
vCard QR code, so a scan saves the complete contact card even when it's the
last physical card on the counter.

Editable design canvas (front + back artboards, click-to-edit):
https://claude.ai/code/artifact/33c1debb-1641-42bd-8e9c-effb24549dc6

## Print files (`print/`)

| File | Use |
| --- | --- |
| `express-collectibles-business-card-print.pdf` | Send this to the print shop — 2 pages (front/back) at exactly 3.625 × 2.125 in (full bleed) |
| `front-bleed…` / `back-bleed…` `.png` | Same thing as individual 300-dpi PNGs (1088 × 638) |
| `front-trimmed-preview…` / `back-trimmed-preview…` `.png` | What the card looks like after trimming to 3.5 × 2 in — for proofing, not for printing |

Specs: US standard 3.5 × 2 in trim, 1/16 in bleed on each side, text kept
inside the safe zone. Designed at 96 px/in (348 × 204 px artboards), rendered
at 300 dpi. Fonts are the site's own stack (Roboto / Roboto Mono, embedded
OFL latin subsets).

## What's on the card

- Ticker: **Video Games ◆ Consoles ▲ Accessories ◆ TCG ▲ Collectibles**
- **Neal Knebel — Owner** · Express Collectibles · Buy / Sell / Trade
- (618) 882-1041 · neal@expresscollectibles.com · 906 Broadway, Highland, IL 62249
- www.expresscollectibles.com
- Whatnot / Facebook: **@expresscollectibles** · eBay: **neal_knebel** (the
  seller username behind the "Highland Express Collectibles" store the site
  footer links at ebay.com/str/expressplug) · Instagram / TikTok:
  **@nealknebelofficial**
- Back QR: vCard 3.0 (v15, ECC L — machine-verified to decode from the
  300-dpi render with every field intact)

### ⚠️ Before sending to print

- The bare domain `expresscollectibles.com` still shows the Squarespace
  "coming soon" page — the card prints the working `WWW.` form. Point the
  apex domain at the live site when possible.
- `neal@expresscollectibles.com` must exist — set up the mailbox or an alias
  forwarding to Neal's Gmail (Google Workspace admin for the domain).

## Black steel / xTool version (`engrave/`)

Same design translated for laser engraving on a black-coated stainless blank
(standard 86 × 54 mm metal business card). A laser is binary, so the neon
glows/gradients become solid silver marks and line work; text rows sit on
un-engraved keep-out panels so the grid never crosses the type; the QR area
engraves as a solid silver plate with the modules left black steel (normal
dark-on-light polarity — machine-verified to decode straight from the mask).

- `engrave/front-engrave-shaded.png` / `back-engrave-shaded.png` —
  **recommended**: 8-bit grayscale, 600 dpi, exactly 86 × 54 mm, black =
  engrave. Carries the depth layers (echo shadows under the big type, halos
  behind the wordmark/QR plate, grid horizon fade) as mid-gray tones — run it
  in xTool Creative Space's **grayscale/dither** mode so grays engrave as fine
  dot patterns (dimmer silver).
- `engrave/front-engrave-mask.png` / `back-engrave-mask.png` — flat 1-bit
  line-art fallback (no shading) for plain black/white engrave mode.
- In xTool Creative Space: import the PNG, set size to 86 × 54 mm, pick the
  processing mode above, use your coated-stainless preset. Engrave a test
  card and scan the QR before running the batch.
- `SteelFront.dc.html` / `SteelBack.dc.html` are the on-screen previews
  (brushed-steel mockup); `make_masks.py` regenerates the masks from them
  after any contact edit (run `make_qr.py` + `build_assets.py` first).

## Files

- `Main.dc.html` / `Back.dc.html` — front/back artboard sources (self-contained:
  fonts and QR inlined)
- `canvas.json` — canvas layout for the design artifact
- `make_qr.py` — builds the vCard (`qr/neal-knebel.vcf`) and its QR
  (`qr/express-collectibles-vcard.svg` + path data). Edit the contact details
  here, then re-run.
- `build_assets.py` — inlines fonts + fresh QR path/viewBox into the artboards
  (placeholders `@@FONT_*@@` / `@@QR_PATH@@` / `@@QR_VB@@`; already-built
  files are left alone — to re-inject a new QR, restore the placeholders in
  `Back.dc.html` first)
- `fonts/` — Roboto (variable, normal + 900 italic) and Roboto Mono latin
  woff2 subsets (Google Fonts, OFL license)
- `qr/neal-knebel.vcf` — the vCard itself; also usable on its own (email
  signatures, AirDrop, website download link)

## Regenerating the print files

```bash
python3 make_qr.py && python3 build_assets.py   # after editing contact info
# then render Main.dc.html / Back.dc.html at device scale 3.125 (Playwright or
# any Chromium), crop to 1088×638, and rebuild the PDF with img2pdf:
python3 -m img2pdf print/front-bleed-3.625x2.125in-300dpi.png \
  print/back-bleed-3.625x2.125in-300dpi.png \
  --imgsize 3.625inx2.125in -o print/express-collectibles-business-card-print.pdf
```

The site also ships four alternate colorways (Tron Grid, Toxic CRT, Outrun
Heat, Arcade Royale) — the card can be re-tokened to any of them on request.
