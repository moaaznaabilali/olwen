#!/usr/bin/env bash
# Build Olwen.app from olwen_app.py. Drops the .app into ./dist/Olwen.app
# and (optionally) copies it to /Applications.
set -euo pipefail

TEAL=$'\033[38;5;79m'; BOLD=$'\033[1m'; OFF=$'\033[0m'
say() { printf "${TEAL}▸${OFF} %s\n" "$*"; }

cd "$(dirname "$0")"

say "creating build venv"
python3 -m venv .build-venv
.build-venv/bin/pip install --quiet --upgrade pip wheel setuptools
.build-venv/bin/pip install --quiet \
  py2app pyobjc-core pyobjc-framework-Cocoa \
  fastapi 'uvicorn[standard]' pydantic \
  pyautogui mss pillow

say "generating icon (resources/Olwen.icns) from creature SVG"
./make_icon.sh || say "icon generation skipped (rsvg-convert/sips not available) — app will use a default icon"

say "cleaning previous build"
rm -rf build dist

say "running py2app"
.build-venv/bin/python setup.py py2app 2>&1 | tail -15

if [[ -d dist/Olwen.app ]]; then
  say "✓ built ${BOLD}dist/Olwen.app${OFF}"
  echo
  echo "Next:"
  echo "  1. Drag dist/Olwen.app to /Applications"
  echo "  2. Launch Olwen from Spotlight or the Applications folder"
  echo "  3. macOS will ask for Accessibility permission — say yes"
  echo "  4. The window stays running; close it to hide, ⌘Q to quit"
else
  echo "build failed — check the log above" >&2
  exit 1
fi
