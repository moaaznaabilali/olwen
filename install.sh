#!/usr/bin/env bash
# Olwen — one-command installer.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/moaaznaabilali/olwen/main/install.sh | bash
#
# Or, if you've already cloned:
#   ./install.sh
#
# What it does:
#   1. Verifies prerequisites (python 3.11+, node 20+, pnpm, postgres)
#   2. Clones the repo (if run via curl)
#   3. Creates a Python venv + installs backend deps
#   4. Installs frontend deps with pnpm
#   5. Copies .env.example → .env, generates a JWT secret
#   6. Creates the `olwen` database (if missing)
#   7. Writes a `start.sh` you run to launch backend + frontend together
set -euo pipefail

# ---------- pretty print ----------
TEAL=$'\033[38;5;79m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; RED=$'\033[31m'; OFF=$'\033[0m'
step()  { printf "${TEAL}▸${OFF} %s\n" "$*"; }
ok()    { printf "${TEAL}✓${OFF} %s\n" "$*"; }
warn()  { printf "${RED}!${OFF} %s\n" "$*"; }
fail()  { printf "${RED}✗ %s${OFF}\n" "$*"; exit 1; }

cat <<BANNER
${TEAL}
       .
      ( )
     /─┴─\\         ${BOLD}Olwen${OFF}${TEAL}  ·  a calm AI companion
    ╱ ─ ─ ╲        ${DIM}reads your mail · writes your morning${OFF}${TEAL}
   ╱ ─ ─ ─ ╲       ${DIM}runs your terminal · stays out of your way${OFF}${TEAL}
    \\\\ | | //
     \\\\| |//
${OFF}
BANNER

# ---------- prereqs ----------
step "checking prerequisites…"
need() { command -v "$1" >/dev/null 2>&1 || fail "missing: $1 — install it first (see https://github.com/moaaznaabilali/olwen#install)"; }
need git; need python3; need node; need pnpm; need psql

PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info[0])')
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info[1])')
[[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 11 ]] || fail "python 3.11+ required (have $PY_MAJOR.$PY_MINOR)"

NODE_MAJOR=$(node -p 'process.versions.node.split(".")[0]')
[[ "$NODE_MAJOR" -ge 20 ]] || fail "node 20+ required (have $NODE_MAJOR)"

ok "python $PY_MAJOR.$PY_MINOR, node $NODE_MAJOR, pnpm $(pnpm --version)"

# ---------- clone if needed ----------
if [[ ! -f "backend/requirements.txt" ]]; then
  step "cloning repo…"
  if [[ -d "olwen" ]]; then
    fail "./olwen already exists — cd into it and re-run ./install.sh"
  fi
  git clone https://github.com/moaaznaabilali/olwen.git
  cd olwen
fi
ok "in $(pwd)"

# ---------- backend ----------
step "creating python venv (backend/.venv)…"
python3 -m venv backend/.venv
ok "venv ready"

step "installing backend deps (this takes ~1 min)…"
backend/.venv/bin/python -m pip install --quiet --upgrade pip
backend/.venv/bin/python -m pip install --quiet -r backend/requirements.txt
ok "backend deps installed"

# ---------- env ----------
step "writing backend/.env…"
if [[ -f backend/.env ]]; then
  warn "backend/.env exists — leaving it alone"
else
  cp backend/.env.example backend/.env
  # generate a real JWT secret so prod-grade tokens work out of the box
  JWT=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
  if [[ "$(uname)" == "Darwin" ]]; then
    sed -i '' "s|JWT_SECRET=.*|JWT_SECRET=$JWT|" backend/.env
  else
    sed -i "s|JWT_SECRET=.*|JWT_SECRET=$JWT|" backend/.env
  fi
  ok "backend/.env created with a random JWT_SECRET"
fi

# ---------- database ----------
step "ensuring postgres database 'olwen' exists…"
if psql -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw olwen; then
  ok "database 'olwen' already exists"
else
  if createdb olwen 2>/dev/null; then
    ok "created database 'olwen'"
  else
    warn "couldn't auto-create the database. If your postgres uses a non-default user,"
    warn "edit backend/.env → DATABASE_URL, then run: createdb olwen"
  fi
fi

# ---------- frontend ----------
step "installing frontend deps with pnpm (this takes ~2 min)…"
( cd frontend && pnpm install --silent )
ok "frontend deps installed"

# ---------- start script ----------
step "writing start.sh…"
cat > start.sh <<'START'
#!/usr/bin/env bash
# Launch Olwen — backend on :8000, frontend on :3100.
# Ctrl-C stops both.
set -euo pipefail

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "▸ starting backend  → http://localhost:8000"
( cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000 ) &

echo "▸ starting frontend → http://localhost:3100"
( cd frontend && pnpm dev --port 3100 ) &

wait
START
chmod +x start.sh
ok "start.sh ready"

# ---------- done ----------
cat <<DONE

${TEAL}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${OFF}
${BOLD}Olwen is installed.${OFF}

  ${TEAL}▸${OFF} start it:        ${BOLD}./start.sh${OFF}
  ${TEAL}▸${OFF} then open:       ${BOLD}http://localhost:3100${OFF}
  ${TEAL}▸${OFF} api docs:        ${BOLD}http://localhost:8000/docs${OFF}

${DIM}First-time login: sign up with any email — the OTP is printed in the
backend terminal (EMAIL_PROVIDER=console by default). Bring your own
Claude or Gemini key from Settings when you're ready.${OFF}
${TEAL}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${OFF}
DONE
