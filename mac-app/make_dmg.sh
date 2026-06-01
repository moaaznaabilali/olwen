#!/usr/bin/env bash
# Build branded Olwen-<version>.dmg using create-dmg.
set -euo pipefail
cd "$(dirname "$0")"

APP=dist/Olwen.app
VERSION="0.4.0"
FINAL="dist/Olwen-${VERSION}.dmg"
BG=resources/dmg-background.png

[[ -d "$APP" ]] || { echo "Run ./build.sh first" >&2; exit 1; }
command -v create-dmg >/dev/null 2>&1 || { echo "create-dmg missing — brew install create-dmg" >&2; exit 1; }

rm -f "$FINAL"

create-dmg \
  --volname "Olwen" \
  --background "$BG" \
  --window-pos 200 120 \
  --window-size 540 380 \
  --icon-size 128 \
  --icon "Olwen.app" 150 200 \
  --app-drop-link 390 200 \
  --hide-extension "Olwen.app" \
  --no-internet-enable \
  "$FINAL" \
  "$APP"

ls -lh "$FINAL"
