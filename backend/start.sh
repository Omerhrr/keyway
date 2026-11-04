#!/bin/bash
# Keyway FastAPI backend bootstrap (used by mini-services runner and manually)
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

HOST="${KEYWAY_API_HOST:-0.0.0.0}"
PORT="${KEYWAY_API_PORT:-8000}"

# Prefer a dedicated backend venv; fall back to the sandbox Python when
# python3-venv/ensurepip is unavailable in the container.
PY=python3
if [ ! -x ".venv/bin/uvicorn" ] || ! .venv/bin/python -c "import sqlalchemy, fastapi" >/dev/null 2>&1; then
  if command -v pip >/dev/null 2>&1 && python3 -c "import sqlalchemy, fastapi, uvicorn" >/dev/null 2>&1; then
    echo "[keyway-api] using sandbox python (backend/.venv unusable)"
    echo "[keyway-api] starting uvicorn on $HOST:$PORT"
    exec python3 -m uvicorn app.main:app --host "$HOST" --port "$PORT"
  fi
  # last resort: build the venv from scratch
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
fi

echo "[keyway-api] starting uvicorn on $HOST:$PORT"
exec .venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT"
