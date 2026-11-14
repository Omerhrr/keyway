#!/usr/bin/env python3
"""Wipe Keyway's business data so you can start with real data.

KEPT (so logins and the system keep working):
  users and their passwords, roles and permissions, chart of accounts, settings,
  message templates, notification rules, WhatsApp account, pricing rules, warehouses,
  delivery zones and carriers.

WIPED:
  vendors, products, stock, customers, orders, deliveries, riders, COD, settlements,
  payments, charges, journals, expenses, bank records, conversations, drafts,
  notifications and the audit trail. Vendor-portal logins are removed with their vendor.
  Order / settlement numbers start again from KW-1001, STL-1001 and so on.

A copy of the database is saved first, so a wipe can be undone (see the last line it prints).

Run (from the project folder on the VPS):
    docker compose exec keyway-api python reset_data.py            # asks you to type WIPE
    docker compose exec keyway-api python reset_data.py --yes      # no question asked

Run locally:
    cd backend && python3 reset_data.py

Options:
    --yes             do not ask for confirmation
    --wipe-setup      also remove warehouses, delivery zones, carriers and pricing rules
                      (a fresh "Main Warehouse" is created so you can receive stock)
    --keep-riders     keep the riders list
    --no-backup       skip the safety copy (not recommended)
"""
import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import text  # noqa: E402

import app.main  # noqa: E402,F401  (imports every model so the metadata is complete)
from app.core.db import Base, engine, SessionLocal  # noqa: E402
from app.core.config import settings  # noqa: E402

# Never touched (unless --wipe-setup, for the setup group)
KEEP_ALWAYS = {
    "users", "roles", "permissions", "role_permissions", "accounts", "app_settings",
    "financial_periods", "message_templates", "notification_rules", "whatsapp_accounts",
}
KEEP_SETUP = {"warehouses", "warehouse_locations", "delivery_zones", "carriers", "charge_rules"}


def db_file() -> Path | None:
    url = settings.DATABASE_URL
    if not url.startswith("sqlite:///"):
        return None
    return Path(url.replace("sqlite:///", "", 1))


def backup(path: Path) -> Path:
    dest = path.with_name(f"{path.stem}-before-wipe-{datetime.now():%Y%m%d-%H%M%S}.db")
    src = sqlite3.connect(str(path))
    dst = sqlite3.connect(str(dest))
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description="Wipe Keyway business data (users and passwords are kept).")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--wipe-setup", action="store_true")
    ap.add_argument("--keep-riders", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    a = ap.parse_args()

    path = db_file()
    if path is None:
        print("This script only handles the SQLite database. Aborting.")
        return 1

    keep = set(KEEP_ALWAYS)
    if not a.wipe_setup:
        keep |= KEEP_SETUP
    if a.keep_riders:
        keep.add("riders")

    wipe = [t for t in reversed(Base.metadata.sorted_tables) if t.name not in keep]
    with engine.connect() as c:
        counts = {t.name: c.execute(text(f'select count(*) from "{t.name}"')).scalar() for t in wipe}
        users = c.execute(text("select count(*) from users")).scalar()
        portal_users = c.execute(text("select count(*) from users where is_vendor = 1 or vendor_id is not null")).scalar()
    total = sum(counts.values())

    print(f"Database: {path}")
    print(f"Will delete {total} rows from {sum(1 for v in counts.values() if v)} tables, e.g.:")
    for name, n in sorted(counts.items(), key=lambda kv: -kv[1])[:8]:
        if n:
            print(f"   {name:<28}{n}")
    print(f"Keeps {users - portal_users} staff logins with their passwords"
          f"{f' (removes {portal_users} vendor-portal logins)' if portal_users else ''}.")

    if not a.yes:
        if input("\nType WIPE to continue: ").strip() != "WIPE":
            print("Cancelled. Nothing was changed.")
            return 1

    if not a.no_backup:
        print(f"Safety copy saved: {backup(path)}")

    with engine.begin() as c:
        c.execute(text("PRAGMA foreign_keys=OFF"))
    with engine.begin() as c:
        for t in wipe:
            c.execute(text(f'delete from "{t.name}"'))
        # vendor-portal logins belong to vendors that no longer exist
        c.execute(text("delete from users where is_vendor = 1 or vendor_id is not null"))
        # pricing rules tied to a vendor go with the vendor
        if "charge_rules" in keep:
            c.execute(text("delete from charge_rules where vendor_id is not null"))
        # staff are no longer tied to a removed warehouse
        if a.wipe_setup:
            c.execute(text("update users set warehouse_id = null"))
        # ids and reference numbers start again
        try:
            names = ",".join(f"'{t.name}'" for t in wipe)
            c.execute(text(f"delete from sqlite_sequence where name in ({names})"))
        except Exception:
            pass
    with engine.begin() as c:
        c.execute(text("PRAGMA foreign_keys=ON"))
        bad = c.execute(text("PRAGMA foreign_key_check")).fetchall()

    if a.wipe_setup:
        from app.modules.inventory_models import Warehouse
        with SessionLocal() as db:
            if not db.query(Warehouse).count():
                db.add(Warehouse(code="WH-MAIN", name="Main Warehouse", is_default=True))
                db.commit()
                print("Created a fresh Main Warehouse.")

    with engine.connect() as c:
        c.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
    if bad:
        print(f"WARNING: {len(bad)} leftover references found - restore the safety copy and tell support.")
        return 2
    print("Done. Logins and passwords are unchanged; all business data is gone.")
    print("Next: add your vendors, then products, then receive stock.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
