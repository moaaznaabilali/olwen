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
