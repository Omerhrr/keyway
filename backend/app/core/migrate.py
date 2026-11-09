"""Tiny additive migration: add columns that new code expects but an older database lacks."""
import logging
from sqlalchemy import inspect, text

log = logging.getLogger("keyway")


def add_missing_columns(engine, Base):
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                typ = col.type.compile(engine.dialect)
                default = ""
                if col.default is not None and getattr(col.default, "is_scalar", False):
                    v = col.default.arg
                    default = f" DEFAULT {int(v) if isinstance(v, bool) else (repr(v) if isinstance(v, str) else v)}"
                elif not col.nullable:
                    default = " DEFAULT 0" if "INT" in typ.upper() else " DEFAULT ''"
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {typ}{default}'))
                log.info("Added column %s.%s", table.name, col.name)
