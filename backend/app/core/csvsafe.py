"""CSV/Excel formula-injection guard for user-supplied text cells."""


def csv_safe(value):
    """Prefix risky leading characters so spreadsheet apps treat the cell as text.
    Only apply to free-text cells (names, memos, SKUs) - never to numeric columns."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value
