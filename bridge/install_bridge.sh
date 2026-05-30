#!/usr/bin/env bash
# Install Olwen Bridge as a per-user LaunchAgent on macOS.
#
# Usage:
#   ./install_bridge.sh           # install + start
#   ./install_bridge.sh --uninstall
set -euo pipefail

TEAL=$'\033[38;5;79m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; RED=$'\033[31m'; OFF=$'\033[0m'
say()  { printf "${TEAL}▸${OFF} %s\n" "$*"; }
ok()   { printf "${TEAL}✓${OFF} %s\n" "$*"; }
warn() { printf "${RED}!${OFF} %s\n" "$*"; }
fail() { printf "${RED}✗ %s${OFF}\n" "$*"; exit 1; }

PREFIX="${HOME}/.olwen/bridge"
PLIST_PATH="${HOME}/Library/LaunchAgents/com.olwen.bridge.plist"
LABEL="com.olwen.bridge"
LOG_DIR="${HOME}/.olwen/logs"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

uninstall() {
  say "uninstalling…"
  launchctl unload "$PLIST_PATH" 2>/dev/null || true
  rm -f "$PLIST_PATH"
  rm -rf "$PREFIX"
  ok "removed $PREFIX and $PLIST_PATH"
  warn "your token file at ~/.olwen/bridge.token is kept — delete by hand if you want it gone"
  exit 0
}

[[ "${1-}" == "--uninstall" ]] && uninstall

[[ "$(uname)" == "Darwin" ]] || fail "macOS installer (Linux/Windows installers come later)"
command -v python3 >/dev/null 2>&1 || fail "python3 not found"

PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info[0])')
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info[1])')
[[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 11 ]] || fail "python 3.11+ required (have $PY_MAJOR.$PY_MINOR)"

say "installing to $PREFIX"
mkdir -p "$PREFIX" "$LOG_DIR"
cp "$SRC_DIR/olwen_bridge.py" "$PREFIX/olwen_bridge.py"
cp "$SRC_DIR/ax_control.py" "$PREFIX/ax_control.py"   # AX module the bridge imports

say "creating venv + installing deps (this takes ~30s)"
python3 -m venv "$PREFIX/.venv"
"$PREFIX/.venv/bin/pip" install --quiet --upgrade pip
"$PREFIX/.venv/bin/pip" install --quiet \
  fastapi==0.115.* uvicorn==0.32.* pydantic==2.* \
  pyautogui==0.9.* mss==9.* pillow==11.* \
  pyobjc-framework-ApplicationServices==12.* pyobjc-framework-Cocoa==12.*
ok "deps installed"

# ── LaunchAgent plist ────────────────────────────────────────────────
say "writing LaunchAgent $PLIST_PATH"
mkdir -p "$(dirname "$PLIST_PATH")"
cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>           <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PREFIX}/.venv/bin/python</string>
    <string>${PREFIX}/olwen_bridge.py</string>
  </array>
  <key>RunAtLoad</key>       <true/>
  <key>KeepAlive</key>       <true/>
  <key>ProcessType</key>     <string>Background</string>
  <key>StandardOutPath</key> <string>${LOG_DIR}/bridge.out.log</string>
  <key>StandardErrorPath</key><string>${LOG_DIR}/bridge.err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/usr/local/bin:/usr/bin:/bin</string>
  </dict>
</dict>
</plist>
PLIST

# Reload to pick up changes if it was already loaded
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load -w "$PLIST_PATH"
ok "LaunchAgent loaded — bridge runs at login from now on"

# Wait briefly for it to come up
sleep 1.5
if curl -sf "http://127.0.0.1:8765/health" \
    -H "Authorization: Bearer $(cat "${HOME}/.olwen/bridge.token")" >/dev/null 2>&1; then
  ok "bridge is alive on http://127.0.0.1:8765"
else
  warn "bridge didn't answer health check yet. Check ${LOG_DIR}/bridge.err.log"
fi

cat <<DONE

${TEAL}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${OFF}
${BOLD}Olwen Bridge is installed.${OFF}

  ${TEAL}▸${OFF} Endpoint:    ${BOLD}http://127.0.0.1:8765${OFF} (localhost only)
  ${TEAL}▸${OFF} Token:       ${BOLD}~/.olwen/bridge.token${OFF}
  ${TEAL}▸${OFF} Logs:        ${BOLD}${LOG_DIR}/bridge.{out,err}.log${OFF}
  ${TEAL}▸${OFF} Uninstall:   ${BOLD}./install_bridge.sh --uninstall${OFF}

${BOLD}⚠ One more step — grant macOS Accessibility permission:${OFF}

  ${DIM}System Settings → Privacy & Security → Accessibility${OFF}
  ${DIM}→ click '+' → add:${OFF}
  ${BOLD}${PREFIX}/.venv/bin/python${OFF}
  ${DIM}→ toggle the switch ON${OFF}

Without this, pyautogui can read your screen but cannot move the
cursor or send keystrokes (macOS will silently swallow them).

Then in Olwen → Settings → Computer Use, paste the token from
~/.olwen/bridge.token so the backend can talk to the bridge.
${TEAL}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${OFF}
DONE
