#!/bin/bash
# Keyway backup wrapper: safe to run any time (online snapshot).
#   bash scripts/backup.sh            -> snapshot with default retention (14)
#   bash scripts/backup.sh --keep 48  -> keep 48 snapshots
# Schedule with cron in real deployments (see scripts/db_backup.py header).
set -e
cd "$(dirname "$0")/.."
exec python3 scripts/db_backup.py "$@"
