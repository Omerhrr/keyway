"""Double-entry ledger posting service.

Rules enforced here (per PRD):
- Every posted journal must balance (sum debits == sum credits).
- Posted entries are immutable; corrections are reversals linking to the original.
- Every financial event carries a source reference (source_type + source_id).
"""
from app.core.db import utcnow
from app.core.ids import next_ref
from app.modules.ledger_models import JournalEntry, JournalLine


def post_journal(db, *, memo: str, source_type: str, source_id=None, lines: list[dict],
                 entry_date=None, posted_by=None, commit: bool = False) -> JournalEntry:
    """lines: [{account_id, debit_kobo, credit_kobo, vendor_id?, memo?}]"""
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
