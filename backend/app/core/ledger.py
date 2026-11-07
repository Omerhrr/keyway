"""Double-entry ledger posting service.

Rules enforced here (per PRD):
- Every posted journal must balance (sum debits == sum credits).
- Posted entries are immutable; corrections are reversals linking to the original.
- Every financial event carries a source reference (source_type + source_id).
"""
from app.core.db import utcnow
from app.core.ids import next_ref
from app.modules.ledger_models import Account, JournalEntry, JournalLine

# A reversed entry keeps its original lines; the reversal entry carries the mirror
# lines. Both must be counted together so the pair nets to zero in every report.
LIVE_ENTRY_STATUSES = ("POSTED", "REVERSED")


def post_journal(db, *, memo: str, source_type: str, source_id=None, lines: list[dict],
                 entry_date=None, posted_by=None, commit: bool = False) -> JournalEntry:
    """lines: [{account_id, debit_kobo, credit_kobo, vendor_id?, memo?}]"""
    account_ids = set()
    for l in lines:
        d, c = int(l.get("debit_kobo") or 0), int(l.get("credit_kobo") or 0)
        if d < 0 or c < 0:
            raise ValueError("Journal amounts cannot be negative")
        if d and c:
            raise ValueError("A journal line cannot carry both a debit and a credit")
        if not d and not c:
            raise ValueError("Every journal line needs a debit or a credit amount")
        if not l.get("account_id"):
            raise ValueError("Every journal line needs an account")
        account_ids.add(l["account_id"])
    known = {a for (a,) in db.query(Account.id).filter(Account.id.in_(account_ids),
                                                       Account.is_active.is_(True)).all()}
    if known != account_ids:
        raise ValueError(f"Unknown or inactive account id(s): {sorted(account_ids - known)}")
    total_d = sum(int(l.get("debit_kobo") or 0) for l in lines)
    total_c = sum(int(l.get("credit_kobo") or 0) for l in lines)
    if total_d == 0 and total_c == 0:
        raise ValueError("Journal has no amounts")
    if total_d != total_c:
        raise ValueError(f"Journal does not balance: debits={total_d} credits={total_c}")

    entry = JournalEntry(
        entry_no="PENDING",
        entry_date=entry_date or utcnow(),
        memo=memo,
        source_type=source_type,
        source_id=str(source_id) if source_id is not None else None,
        status="POSTED",
        posted_by_user_id=posted_by.id if posted_by else None,
        posted_at=utcnow(),
    )
    db.add(entry)
    db.flush()
    entry.entry_no = next_ref(db, JournalEntry, "entry_no", "JE")
    for l in lines:
        db.add(JournalLine(
            entry_id=entry.id,
            account_id=l["account_id"],
            debit_kobo=int(l.get("debit_kobo") or 0),
            credit_kobo=int(l.get("credit_kobo") or 0),
            vendor_id=l.get("vendor_id"),
            memo=l.get("memo"),
        ))
    if commit:
        db.commit()
    return entry


def reverse_journal(db, entry: JournalEntry, reason: str, posted_by=None) -> JournalEntry:
    if entry.status == "REVERSED":
        raise ValueError("Entry already reversed")
    if entry.status != "POSTED":
        raise ValueError(f"Only posted entries can be reversed (this one is {entry.status})")
    if entry.source_type == "REVERSAL" or entry.reversal_of_id:
        raise ValueError("A reversal entry cannot itself be reversed - post a new correcting entry instead")
    rev = JournalEntry(
        entry_no="PENDING",
        entry_date=utcnow(),
        memo=f"Reversal of {entry.entry_no}: {reason}",
        source_type="REVERSAL",
        source_id=str(entry.id),
        status="POSTED",
        reversal_of_id=entry.id,
        posted_by_user_id=posted_by.id if posted_by else None,
        posted_at=utcnow(),
    )
    db.add(rev)
    db.flush()
    rev.entry_no = next_ref(db, JournalEntry, "entry_no", "JE")
    for line in db.query(JournalLine).filter(JournalLine.entry_id == entry.id).all():
        db.add(JournalLine(
            entry_id=rev.id,
            account_id=line.account_id,
            debit_kobo=line.credit_kobo,
            credit_kobo=line.debit_kobo,
            vendor_id=line.vendor_id,
            memo=line.memo,
        ))
    entry.status = "REVERSED"
    return rev
