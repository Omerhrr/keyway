#!/bin/bash
# Keyway restore wrapper: stops the API, restores, brings the stack back up.
#   bash scripts/restore.sh backups/keyway-20260101-090000.db
set -e
ZDIR="/home/z/my-project/.zscripts"
cd "$(dirname "$0")/.."

echo "[restore] stopping API..."
if [ -f "$ZDIR/daemon-keyway-api.pid" ]; then
  kill "$(cat "$ZDIR/daemon-keyway-api.pid")" 2>/dev/null || true
  rm -f "$ZDIR/daemon-keyway-api.pid"
fi
# also free the port in case the pidfile was stale
PIDS=$(fuser -n tcp 8000 2>/dev/null | tr -s ' ')
[ -n "$PIDS" ] && kill $PIDS 2>/dev/null || true
sleep 1

python3 scripts/db_restore.py "$1"

echo "[restore] restarting stack..."
bash scripts/up.sh
