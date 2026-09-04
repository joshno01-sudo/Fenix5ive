#!/bin/sh
# Rasterize every renders/*.svg to a 3200x1800 PNG with the bundled chromium.
# Headless chromium reserves some window height, so we shoot a taller window
# and crop to the artboard.
cd "$(dirname "$0")/renders" || exit 1
CHROME="${CHROME:-$(command -v chromium || echo /opt/pw-browsers/chromium)}"
for f in ${1:-*.svg}; do
  "$CHROME" --headless --no-sandbox --hide-scrollbars --disable-gpu \
    --window-size=1600,1000 --force-device-scale-factor=2 \
    --screenshot="${f%.svg}.png" "file://$PWD/$f" 2>/dev/null
  python3 -c "
import sys
try:
    from PIL import Image
except ImportError:
    sys.exit(0)
im = Image.open('${f%.svg}.png'); im.crop((0, 0, 3200, 1800)).save('${f%.svg}.png')
"
  echo "rendered ${f%.svg}.png"
done
