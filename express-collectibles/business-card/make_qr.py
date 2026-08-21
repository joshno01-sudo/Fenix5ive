#!/usr/bin/env python3
"""Generate the Express Collectibles vCard QR code.

Encodes Neal Knebel's full contact card (everything printed on the
business card) so a scan saves the contact even if this was the last
card on the counter. Outputs:
  qr/neal-knebel.vcf                  - the vCard itself
  qr/express-collectibles-vcard.svg   - standalone QR (dark modules on white)
  qr/qr_path.txt                      - SVG path data + matrix size, for
                                        inlining into the card artwork
"""
import re
import segno

LINES = [
    "BEGIN:VCARD",
    "VERSION:3.0",
    "N:Knebel;Neal;;;",
    "FN:Neal Knebel",
    "ORG:Express Collectibles",
    "TITLE:Owner",
    "TEL;TYPE=WORK,VOICE:+16188826660",
    "ADR;TYPE=WORK:;;806 3rd St;Highland;IL;62249;USA",
    "EMAIL;TYPE=INTERNET:neal_knebel@yahoo.com",
    "URL:https://expresscollectibles.com",
    "NOTE:TCG / Sports Cards / Video Games - Buy / Sell / Trade. "
    "Whatnot + eBay + Facebook: @expresscollectibles. "
    "Instagram + TikTok: @nealknebelofficial.",
    "END:VCARD",
]
VCARD = "\r\n".join(LINES) + "\r\n"

with open("qr/neal-knebel.vcf", "w", newline="") as f:
    f.write(VCARD)

print(f"vCard bytes: {len(VCARD.encode('utf-8'))}")
for ecc in ("m", "l"):
    q = segno.make(VCARD, error=ecc)
    n = q.symbol_size(scale=1, border=0)[0]
    print(f"  error={ecc}: version {q.version}, {n}x{n} modules")

# Module size wins over redundancy at business-card scale: pick L so the
# code stays coarse enough to scan from worn print (segno still boosts
# ECC within the version when there is room).
qr = segno.make(VCARD, error="l")
qr.save("qr/express-collectibles-vcard.svg", scale=10, border=4,
        dark="#16122b", light="#ffffff")

svg = open("qr/express-collectibles-vcard.svg").read()
d = re.search(r'<path class="qrline"[^>]* d="([^"]+)"', svg).group(1)
size = qr.symbol_size(scale=1, border=0)[0]
with open("qr/qr_path.txt", "w") as f:
    f.write(f"{size}\n{d}\n")
chosen = qr.error
print(f"chosen: version {qr.version} ecc {chosen}, {size}x{size} modules, "
      f"path chars {len(d)}")
