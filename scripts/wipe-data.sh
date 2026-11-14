#!/bin/bash
# Wipe all business data on the VPS (logins and passwords are kept).
#   cd /opt/keyway && bash scripts/wipe-data.sh            # asks you to type WIPE
#   bash scripts/wipe-data.sh --wipe-setup                 # also warehouses, zones, carriers, pricing rules
# A safety copy of the database is saved first (printed at the end of the run).
set -e
cd "$(dirname "$0")/.."
docker compose exec keyway-api python reset_data.py "$@"
