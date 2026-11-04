#!/bin/bash
# Keyway FastAPI backend bootstrap (used by mini-services runner and manually)
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PY=python3
if [ ! -d ".venv" ]; then
  echo "[keyway-api] creating venv..."
  "$PY" -m venv .venv
  .venv/bin/pip install --upgrade pip -q
fi
if [ ! -f ".venv/.deps-installed" ] || [ "requirements.txt" -nt ".venv/.deps-installed" ]; then
  echo "[keyway-api] installing python dependencies..."
  .venv/bin/pip install -r requirements.txt -q
  touch .venv/.deps-installed
fi

HOST="${KEYWAY_API_HOST:-0.0.0.0}"
PORT="${KEYWAY_API_PORT:-8000}"
echo "[keyway-api] starting uvicorn on $HOST:$PORT"
exec .venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT"
