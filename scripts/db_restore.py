#!/usr/bin/env python3
"""Keyway SQLite restore: verify, snapshot current, atomic replace, re-verify.

Usage:
    python3 scripts/db_restore.py <backup-file.db>

Safety:
1. Refuses to run if the target database is in use? No - SQLite file replace
   requires the API to be STOPPED first. scripts/restore.sh does that for you;
   running this script directly while the API runs will corrupt state.
2. The current database is moved aside (pre-restore-<ts>.db) before the
   backup replaces it, so a bad restore can itself be rolled back.
3. Both the backup and the restored file must pass PRAGMA integrity_check.
"""
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def resolve_db_path() -> Path:
    env = ROOT / "backend" / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
                if url.startswith("sqlite:///"):
                    p = Path(url.removeprefix("sqlite:///"))
                    return p if p.is_absolute() else ROOT / p
                raise SystemExit(f"[restore] non-sqlite DATABASE_URL not supported here: {url}")
    return ROOT / "backend" / "db" / "keyway.db"


def integrity(path: Path) -> tuple[str, int]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        ok = con.execute("PRAGMA integrity_check").fetchone()[0]
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        core = ["orders", "journal_entries", "warehouse", "users"]
        counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in core if t in tables}
        return ok, counts
    finally:
        con.close()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    backup = Path(sys.argv[1]).resolve()
    if not backup.exists():
        raise SystemExit(f"[restore] backup not found: {backup}")

    ok, counts = integrity(backup)
    if ok != "ok":
        raise SystemExit(f"[restore] REFUSING: backup fails integrity_check ({ok})")
    print(f"[restore] backup verified: integrity=ok counts={counts}")

    db = resolve_db_path()
    db.parent.mkdir(parents=True, exist_ok=True)

    # WAL awareness: the live database may be in WAL journal mode. The -wal file
    # holds committed-but-not-checkpointed transactions, so it must travel WITH
    # the main file - both when moving the current db aside and when replacing
    # it. Leaving a stale -wal next to the restored file would let SQLite
    # replay pre-restore transactions over the fresh snapshot.
    stamp = time.strftime("%Y%m%d-%H%M%S")
    aside = db.parent / f"pre-restore-{stamp}.db"
    if db.exists():
        shutil.move(db, aside)
        print(f"[restore] current database moved aside -> {aside.name}")
    for side in ("-wal", "-shm"):
        stale = Path(str(db) + side)
        if stale.exists():
            # keep the sidecar with the moved-aside file so the pair stays consistent
            shutil.move(stale, Path(str(aside) + side))

    tmp = db.with_suffix(".db.restoring")
    shutil.copy(backup, tmp)
    ok2, counts2 = integrity(tmp)
    if ok2 != "ok":
        tmp.unlink(missing_ok=True)
        for side in ("-wal", "-shm"):
            Path(str(tmp) + side).unlink(missing_ok=True)
        if aside.exists():
            shutil.move(aside, db)  # roll back
            for side in ("-wal", "-shm"):
                prev = Path(str(aside) + side)
                if prev.exists():
                    shutil.move(prev, Path(str(db) + side))
        raise SystemExit("[restore] copy failed verification - original restored")
    # scrub sidecars from the verification copy, then move it into place
    for side in ("-wal", "-shm"):
        Path(str(tmp) + side).unlink(missing_ok=True)
    tmp.replace(db)
    # make sure no stale sidecars sit next to the restored database
    for side in ("-wal", "-shm"):
        Path(str(db) + side).unlink(missing_ok=True)
    print(f"[restore] database restored from {backup.name}: integrity=ok counts={counts2}")
    print(f"[restore] previous state kept as {aside.name} (delete it once verified)")
    print("[restore] start the API now: bash scripts/up.sh")


if __name__ == "__main__":
    main()
