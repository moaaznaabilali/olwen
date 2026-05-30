#!/usr/bin/env bash
# Build Olwen.app with pyinstaller.
set -euo pipefail

TEAL=$'\033[38;5;79m'; BOLD=$'\033[1m'; OFF=$'\033[0m'
say() { printf "${TEAL}▸${OFF} %s\n" "$*"; }

cd "$(dirname "$0")"

say "creating build venv"
python3 -m venv .build-venv
.build-venv/bin/pip install --quiet --upgrade pip wheel setuptools
.build-venv/bin/pip install --quiet \
  pyinstaller \
  pyobjc-core pyobjc-framework-Cocoa pyobjc-framework-WebKit \
  pyobjc-framework-ApplicationServices \
  fastapi 'uvicorn[standard]' pydantic \
  pyautogui mss pillow

say "cleaning previous build"
rm -rf build dist Olwen.spec

ICON_ARG=""
if [[ -f resources/Olwen.icns ]]; then
  ICON_ARG="--icon=resources/Olwen.icns"
fi

say "running pyinstaller (this takes ~1 min)"
.build-venv/bin/pyinstaller \
  --windowed \
  --name Olwen \
  --osx-bundle-identifier com.olwen.app \
  $ICON_ARG \
  --noconfirm \
  --clean \
  --hidden-import=pyobjc \
  --hidden-import=AppKit \
  --hidden-import=Foundation \
  --hidden-import=PyObjCTools.AppHelper \
  --hidden-import=WebKit \
  --hidden-import=ApplicationServices \
  --hidden-import=Quartz \
  olwen_app.py 2>&1 | tail -8

# Patch the Info.plist with our usage descriptions + LSUIElement=false
PLIST="dist/Olwen.app/Contents/Info.plist"
if [[ -f "$PLIST" ]]; then
  /usr/libexec/PlistBuddy -c "Add :NSAccessibilityUsageDescription string 'Olwen needs Accessibility access to move the cursor and send keystrokes when you ask him to.'" "$PLIST" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Set :NSAccessibilityUsageDescription 'Olwen needs Accessibility access to move the cursor and send keystrokes when you ask him to.'" "$PLIST"
  /usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string '11.0'" "$PLIST" 2>/dev/null || true
  /usr/libexec/PlistBuddy -c "Add :NSHighResolutionCapable bool true" "$PLIST" 2>/dev/null || true
fi

if [[ -d dist/Olwen.app ]]; then
  say "✓ built ${BOLD}dist/Olwen.app${OFF}"
else
  echo "build failed — check the log above" >&2
  exit 1
fi
