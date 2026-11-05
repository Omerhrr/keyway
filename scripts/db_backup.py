#!/usr/bin/env python3
"""Keyway SQLite backup: online-safe, verified, with retention.

Uses the sqlite3 online backup API, so it produces a consistent snapshot
even while the FastAPI backend is running and writing.

Usage:
    python3 scripts/db_backup.py [--keep N] [--dir DIR]

Output: $BACKUP_DIR/keyway-YYYYmmdd-HHMMSS.db (+ .meta sidecar with sha256)
Default dir: /home/z/my-project/backups  (override with --dir or BACKUP_DIR)

Cron example (real deployment, adjust paths):
    15 * * * * cd /srv/keyway && python3 scripts/db_backup.py --keep 48 >> /var/log/keyway-backup.log 2>&1
"""
import argparse
import hashlib
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "backend" / "db" / "keyway.db"
DEFAULT_DIR = ROOT / "backups"


def resolve_db_path() -> Path:
    """Mirror backend/app/core/config.py: .env DATABASE_URL wins over default."""
    env = ROOT / "backend" / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
                if url.startswith("sqlite:///"):
                    p = Path(url.removeprefix("sqlite:///"))
                    return p if p.is_absolute() else ROOT / p
                raise SystemExit(f"[backup] non-sqlite DATABASE_URL not supported here: {url}")
    return DEFAULT_DB


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=14, help="backups to retain (default 14)")
    ap.add_argument("--dir", default=None, help="backup directory")
    args = ap.parse_args()

    import sqlite3

    db = resolve_db_path()
    if not db.exists():
        raise SystemExit(f"[backup] database not found: {db}")

    out_dir = Path(args.dir or __import__("os").environ.get("BACKUP_DIR") or DEFAULT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = out_dir / f"keyway-{stamp}.db"

    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    dst = sqlite3.connect(dest)
    try:
        #Online backup API: consistent snapshot taken page-by-page; safe while in use.
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()

    # verify the snapshot opens cleanly and holds the expected core tables
    chk = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
    try:
        integrity = chk.execute("PRAGMA integrity_check").fetchone()[0]
        tables = {r[0] for r in chk.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        counts = {t: chk.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in {"orders", "journal_entries", "warehouse"} & tables}
    finally:
        chk.close()
    # WAL sidecars belong to the live database, never to a closed snapshot
    for side in ("-wal", "-shm"):
        Path(str(dest) + side).unlink(missing_ok=True)
    if integrity != "ok":
        dest.unlink(missing_ok=True)
        raise SystemExit(f"[backup] FAILED integrity_check={integrity} - snapshot deleted")

    meta = dest.with_suffix(".db.meta")
    meta.write_text(
        f"file={dest.name}\nsource={db}\ncreated={time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"sha256={sha256(dest)}\nbytes={dest.stat().st_size}\nintegrity=ok\ncounts={counts}\n"
    )

    # retention: newest N keyway-*.db survive, older ones (and metas) removed
    backups = sorted(out_dir.glob("keyway-*.db"))
    for old in backups[:-args.keep] if args.keep > 0 else []:
        old.unlink(missing_ok=True)
        old.with_suffix(".db.meta").unlink(missing_ok=True)

    print(f"[backup] {dest} ({dest.stat().st_size // 1024} KiB) integrity=ok counts={counts}")
    print(f"[backup] retained {min(len(backups), args.keep)} snapshot(s) in {out_dir}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # pragma: no cover
        print(f"[backup] ERROR: {e}", file=sys.stderr)
        sys.exit(1)
