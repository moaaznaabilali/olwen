#!/usr/bin/env bash
# Generate resources/Olwen.icns from the creature SVG.
# Falls back gracefully if rsvg-convert or sips isn't available.
set -euo pipefail
cd "$(dirname "$0")"

SVG="../bridge/../site/public/creature.svg"
# When the site/ dir was moved out, look in resources/ as a fallback
[[ -f "$SVG" ]] || SVG="resources/creature.svg"
[[ -f "$SVG" ]] || { echo "no source SVG; skipping icon"; exit 0; }

OUT=resources/Olwen.icns
ICONSET=resources/Olwen.iconset
mkdir -p "$ICONSET"

command -v rsvg-convert >/dev/null 2>&1 || { echo "rsvg-convert missing — install with: brew install librsvg"; exit 0; }
command -v iconutil    >/dev/null 2>&1 || { echo "iconutil missing"; exit 0; }

for size in 16 32 64 128 256 512 1024; do
  rsvg-convert -w "$size" -h "$size" "$SVG" -o "$ICONSET/icon_${size}x${size}.png"
  if [[ "$size" -le 512 ]]; then
    dbl=$((size * 2))
    rsvg-convert -w "$dbl" -h "$dbl" "$SVG" -o "$ICONSET/icon_${size}x${size}@2x.png"
  fi
done

iconutil -c icns "$ICONSET" -o "$OUT"
rm -rf "$ICONSET"
echo "✓ wrote $OUT"
