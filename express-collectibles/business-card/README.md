# Express Collectibles — Business Card

Retro 8-bit arcade business card for Express Collectibles (Neal Knebel, owner).
Front carries the full contact block and every selling/social handle; the back
is a "SCAN ME" vCard QR code, so a scan saves the complete contact card even
when it's the last physical card on the counter.

Editable design canvas (front + back artboards, click-to-edit):
https://claude.ai/code/artifact/33c1debb-1641-42bd-8e9c-effb24549dc6

## Print files (`print/`)

| File | Use |
| --- | --- |
| `express-collectibles-business-card-print.pdf` | Send this to the print shop — 2 pages (front/back) at exactly 3.625 × 2.125 in (full bleed) |
| `front-bleed…` / `back-bleed…` `.png` | Same thing as individual 300-dpi PNGs (1088 × 638) |
| `front-trimmed-preview…` / `back-trimmed-preview…` `.png` | What the card looks like after trimming to 3.5 × 2 in — for proofing, not for printing |

Specs: US standard 3.5 × 2 in trim, 1/16 in bleed on each side, text kept
≥ 1/8 in inside the trim line. Designed at 96 px/in (348 × 204 px artboards),
rendered at 300 dpi.

## What's on the card

- **Neal Knebel — Owner** · Express Collectibles
- 806 3rd St, Highland, IL 62249 · (618) 882-6660 · neal_knebel@yahoo.com
- expresscollectibles.com
- Whatnot / eBay / Facebook: **@expresscollectibles** · Instagram / TikTok: **@nealknebelofficial**
- Back QR: vCard 3.0 (v13, ECC L, 69×69 modules ≈ 0.41 mm/module at print size —
  machine-verified to decode from the 300-dpi render). Contains everything above
  plus a note with all handles.

### ⚠️ Verify before sending to print

- **eBay handle** is shown as `@expresscollectibles` to match the other
  platforms, but no public eBay store was found under that name — correct it
  (front line + `make_qr.py` NOTE) if the real handle differs.
- **Phone** (618) 882-6660 comes from the public listing for 806 3rd St
  (previously listed under Express Vapors at the same address).
- **Email** neal_knebel@yahoo.com comes from the Express Collectibles Facebook
  page. Swap in a neal@expresscollectibles.com address if one exists.

## Files

- `Main.dc.html` / `Back.dc.html` — front/back artboard sources (self-contained:
  fonts and QR inlined)
- `canvas.json` — canvas layout for the design artifact
- `make_qr.py` — builds the vCard (`qr/neal-knebel.vcf`) and its QR
  (`qr/express-collectibles-vcard.svg` + path data). Edit the contact details
  here, then re-run.
- `build_assets.py` — inlines fonts + fresh QR path into the artboards
  (placeholders `@@FONT_*@@` / `@@QR_PATH@@`; already-built files are left
  alone — to re-inject a new QR, restore the `@@QR_PATH@@` placeholder in
  `Back.dc.html` first)
- `fonts/` — Press Start 2P + IBM Plex Mono 400/600, latin woff2 subsets
  (Google Fonts, OFL license)
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

Design system: deep navy `#16122b`, marquee amber `#ffb424`, CRT teal
`#3ee0d2`, cream `#f2ead4`; Press Start 2P for display type, IBM Plex Mono for
contact text; full-bleed amber/teal cabinet-trim bands; pixel bolt mark.
