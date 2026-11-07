#!/bin/bash
# Consistent online backup of the production SQLite DB (+ media) to ./backups on the host.
# Cron example (daily 02:30, keep 14 days):
#   30 2 * * * cd /opt/keyway && bash scripts/vps-backup.sh >> backups/backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
STAMP=$(date +%Y%m%d-%H%M%S)
docker compose exec -T api python - <<PY
import sqlite3
src = sqlite3.connect("/data/keyway.db")
dst = sqlite3.connect("/data/backup-$STAMP.db")
src.backup(dst); dst.close(); src.close()
PY
docker compose cp "api:/data/backup-$STAMP.db" "backups/keyway-$STAMP.db"
docker compose exec -T api rm -f "/data/backup-$STAMP.db"
docker compose cp api:/data/media "backups/media-$STAMP" 2>/dev/null || true
find backups -name 'keyway-*.db' -mtime +14 -delete
find backups -maxdepth 1 -name 'media-*' -mtime +14 -exec rm -rf {} +
echo "[backup] backups/keyway-$STAMP.db"
