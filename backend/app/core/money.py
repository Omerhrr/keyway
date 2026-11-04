"""Money helpers. All monetary amounts are stored as integer kobo (1 NGN = 100 kobo)."""


def naira_to_kobo(amount) -> int:
    if amount is None:
        return 0
    return int(round(float(amount) * 100))


def kobo_to_naira(kobo: int) -> float:
    return round((kobo or 0) / 100.0, 2)


def fmt_naira(kobo: int) -> str:
    value = (kobo or 0) / 100.0
    sign = "-" if value < 0 else ""
    s = f"{abs(value):,.2f}"
    if s.endswith(".00"):
        s = s[:-3]
    return f"{sign}\u20a6{s}"
