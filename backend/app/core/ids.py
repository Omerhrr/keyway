"""Human-readable reference generation, e.g. KW-1024, STL-1007, RCV-1003."""
_PREFIX_BASE = {"KW": 1000, "STL": 1000, "RCV": 1000, "DRF": 1000, "HDV": 1000, "JE": 5000, "WB": 500}


def next_ref(db, model, field, prefix: str) -> str:
    """Generate prefix-(base+sequence). Sequence = highest existing suffix + 1,
    so the first ref is prefix-1001 and refs increase by 1 (KW-1001, KW-1002, ...)."""
    base = _PREFIX_BASE.get(prefix, 1000)
    col = getattr(model, field)
    rows = db.query(col).all()
    max_n = base
    plen = len(prefix) + 1
    for (v,) in rows:
        if v and len(str(v)) > plen and str(v)[:plen] == f"{prefix}-":
            try:
                max_n = max(max_n, int(str(v)[plen:]))
            except ValueError:
                pass
    return f"{prefix}-{max_n + 1}"
