#!/usr/bin/env bash
# Wrap dist/Olwen.app into dist/Olwen-0.1.0.dmg — the .dmg you double-click,
# drag Olwen onto the Applications shortcut, eject.
set -euo pipefail
cd "$(dirname "$0")"

APP=dist/Olwen.app
VERSION="0.1.0"
DMG="dist/Olwen-${VERSION}.dmg"
STAGING=dist/.dmg-stage

[[ -d "$APP" ]] || { echo "Run ./build.sh first — $APP not found" >&2; exit 1; }

rm -rf "$STAGING" "$DMG"
mkdir -p "$STAGING"
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

hdiutil create \
  -volname "Olwen" \
  -srcfolder "$STAGING" \
  -ov -format UDZO \
  "$DMG" >/dev/null

rm -rf "$STAGING"
echo "✓ $DMG"
echo
echo "Double-click it. Drag Olwen → Applications. Eject. Open from Applications."
