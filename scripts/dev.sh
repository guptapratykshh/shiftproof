#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python ]]; then
  python3.12 -m venv .venv
  .venv/bin/pip install -e './backend[dev]'
fi
if [[ ! -d frontend/node_modules ]]; then
  (cd frontend && npm ci)
fi
export SHIFTPROOF_DURABLE_JOBS=true
.venv/bin/uvicorn shiftproof.api:app --host 127.0.0.1 --port 8000 --no-access-log &
backend_pid=$!
.venv/bin/python -m shiftproof.worker &
worker_pid=$!
trap 'kill "$backend_pid" "$worker_pid" 2>/dev/null || true' EXIT INT TERM
(cd frontend && npm run dev)
