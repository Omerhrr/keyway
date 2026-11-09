"""Auto-generated codes, so nobody has to invent SKUs or location codes."""
import re


def _letters(text: str, n: int = 3, fallback: str = "ITM") -> str:
    s = re.sub(r"[^A-Za-z]", "", text or "").upper()
    return (s[:n] or fallback).ljust(n, "X") if s else fallback


def next_code(db, model, field: str, prefix: str, *, width: int = 3, **scope) -> str:
    """prefix-001, prefix-002 ... the first number not already used inside the scope."""
    col = getattr(model, field)
    q = db.query(col).filter(col.like(f"{prefix}-%"))
    for k, v in scope.items():
        q = q.filter(getattr(model, k) == v)
    used = {r[0] for r in q.all()}
    n = len(used) + 1
    while f"{prefix}-{n:0{width}d}" in used:
        n += 1
    return f"{prefix}-{n:0{width}d}"


def product_prefix(name: str) -> str:
    return _letters(name)
