def _iso(v):
    from datetime import datetime, date
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def serialize(obj, fields: list[str] | None = None, **extra) -> dict | None:
    """Generic ORM -> dict serializer. Datetimes become ISO strings."""
    if obj is None:
        return None
    if fields:
        d = {f: _iso(getattr(obj, f, None)) for f in fields}
    else:
        d = {c.name: _iso(getattr(obj, c.name)) for c in obj.__table__.columns}
    for k, v in extra.items():
        d[k] = _iso(v) if not isinstance(v, (dict, list)) else v
    return d


def serialize_list(rows, fields: list[str] | None = None, **extra) -> list[dict]:
    return [serialize(r, fields, **extra) for r in rows]
