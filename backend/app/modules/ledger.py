"""Chart of accounts, journals, financial statements, expenses, bank transactions."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.db import get_db, utcnow
from app.core.deps import require_staff, require_perm
from app.core.serialize import serialize, serialize_list
from app.core.audit import audit
from app.modules.identity_models import User
from app.modules.ledger_models import (Account, JournalEntry, JournalLine, Expense,
                                       BankTransaction, FinancialPeriod)
from app.core.ledger import post_journal, reverse_journal

router = APIRouter(prefix="/api/ledger", tags=["ledger"])

EXPENSE_CATEGORIES = ["Fuel", "Staff Salaries", "Warehouse Rent", "Utilities", "Vehicle Maintenance",
                      "Packaging", "Transport", "Communications", "Administrative", "Other"]


def get_account_by_subtype(db: Session, subtype: str) -> Account:
    acc = db.query(Account).filter(Account.subtype == subtype, Account.is_active.is_(True)).first()
    if not acc:
        raise HTTPException(500, f"Chart of accounts missing '{subtype}' - seed the ledger first")
    return acc


class AccountIn(BaseModel):
    code: str
    name: str
    type: str
    subtype: str = ""
    is_cash: bool = False


class JournalLineIn(BaseModel):
    account_id: int
    debit_kobo: int = 0
    credit_kobo: int = 0
    vendor_id: int | None = None
    memo: str = ""


class JournalIn(BaseModel):
    memo: str
    lines: list[JournalLineIn]


class ReverseIn(BaseModel):
    reason: str


class ExpenseIn(BaseModel):
    category: str
    description: str = ""
    amount_kobo: int
    payment_method: str = "CASH"
    paid_from_account_id: int | None = None
    receipt_ref: str = ""
    payee: str = ""
    expense_date: str | None = None


@router.get("/accounts")
def list_accounts(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return serialize_list(db.query(Account).order_by(Account.code).all())


@router.post("/accounts")
def create_account(body: AccountIn, user: User = Depends(require_perm("finance.manage")), db: Session = Depends(get_db)):
    if body.type not in ("ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE"):
        raise HTTPException(400, "Invalid account type")
    a = Account(**body.model_dump())
    db.add(a)
    db.commit()
    return serialize(a)


@router.get("/journals")
def list_journals(user: User = Depends(require_staff), db: Session = Depends(get_db),
                  source_type: str = "", limit: int = 100):
    query = db.query(JournalEntry)
    if source_type:
        query = query.filter(JournalEntry.source_type == source_type)
    entries = query.order_by(JournalEntry.id.desc()).limit(min(limit, 300)).all()
    out = []
    for e in entries:
        lines = (db.query(JournalLine, Account)
                 .join(Account, Account.id == JournalLine.account_id)
                 .filter(JournalLine.entry_id == e.id).all())
        out.append(serialize(e, lines=[{"account_code": a.code, "account_name": a.name,
                                        "debit_kobo": l.debit_kobo, "credit_kobo": l.credit_kobo,
                                        "vendor_id": l.vendor_id, "memo": l.memo}
                                       for l, a in lines]))
    return out


@router.post("/journals")
def create_journal(body: JournalIn, user: User = Depends(require_perm("finance.manage")), db: Session = Depends(get_db)):
    if len(body.lines) < 2:
        raise HTTPException(400, "A journal entry needs at least two lines")
    try:
        entry = post_journal(db, memo=body.memo, source_type="MANUAL",
                             lines=[l.model_dump() for l in body.lines], posted_by=user)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    audit(db, user, "post", "journal_entry", entry.id, f"Manual journal {entry.entry_no}: {body.memo}")
    db.commit()
    return serialize(entry)


@router.post("/journals/{entry_id}/reverse")
def reverse(entry_id: int, body: ReverseIn, user: User = Depends(require_perm("finance.manage")), db: Session = Depends(get_db)):
    e = db.get(JournalEntry, entry_id)
    if not e:
        raise HTTPException(404, "Entry not found")
    if not body.reason.strip():
        raise HTTPException(400, "A reason is required for every reversal")
    try:
        rev = reverse_journal(db, e, body.reason, user)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    db.commit()
    audit(db, user, "reverse", "journal_entry", e.id, f"Reversed {e.entry_no}: {body.reason}")
    db.commit()
    return serialize(rev)


@router.get("/trial-balance")
def trial_balance(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    rows = (db.query(Account,
                     func.coalesce(func.sum(JournalLine.debit_kobo), 0).label("debits"),
                     func.coalesce(func.sum(JournalLine.credit_kobo), 0).label("credits"))
            .outerjoin(JournalLine, JournalLine.account_id == Account.id)
            .outerjoin(JournalEntry, (JournalEntry.id == JournalLine.entry_id) & (JournalEntry.status == "POSTED"))
            .filter(Account.is_active.is_(True))
            .group_by(Account.id).order_by(Account.code).all())
    out = []
    total_d = total_c = 0
    for acc, d, c in rows:
        # Only count lines of POSTED entries: recompute precisely
        d2 = (db.query(func.coalesce(func.sum(JournalLine.debit_kobo), 0))
              .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
              .filter(JournalLine.account_id == acc.id, JournalEntry.status == "POSTED").scalar()) or 0
        c2 = (db.query(func.coalesce(func.sum(JournalLine.credit_kobo), 0))
              .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
              .filter(JournalLine.account_id == acc.id, JournalEntry.status == "POSTED").scalar()) or 0
        total_d += d2
        total_c += c2
        out.append(serialize(acc, debit_kobo=d2, credit_kobo=c2,
                             balance_kobo=(d2 - c2) if acc.type in ("ASSET", "EXPENSE") else (c2 - d2)))
    return {"lines": out, "total_debits_kobo": total_d, "total_credits_kobo": total_c,
            "balanced": total_d == total_c}


@router.get("/pnl")
def pnl(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    rows = (db.query(Account,
                     func.coalesce(func.sum(JournalLine.credit_kobo - JournalLine.debit_kobo), 0).label("net"))
            .outerjoin(JournalLine, JournalLine.account_id == Account.id)
            .outerjoin(JournalEntry, (JournalEntry.id == JournalLine.entry_id) & (JournalEntry.status == "POSTED"))
            .filter(Account.type.in_(["REVENUE", "EXPENSE"]))
            .group_by(Account.id).order_by(Account.code).all())
    revenue, expenses = [], []
    for acc, net in rows:
        item = serialize(acc, net_kobo=abs(net))
        (revenue if acc.type == "REVENUE" else expenses).append(item)
    total_rev = sum(r["net_kobo"] for r in revenue)
    total_exp = sum(e["net_kobo"] for e in expenses)
    return {"revenue": revenue, "expenses": expenses,
            "total_revenue_kobo": total_rev, "total_expenses_kobo": total_exp,
            "net_profit_kobo": total_rev - total_exp}


@router.get("/balance-sheet")
def balance_sheet(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    rows = (db.query(Account,
                     func.coalesce(func.sum(JournalLine.debit_kobo - JournalLine.credit_kobo), 0).label("net"))
            .outerjoin(JournalLine, JournalLine.account_id == Account.id)
            .outerjoin(JournalEntry, (JournalEntry.id == JournalLine.entry_id) & (JournalEntry.status == "POSTED"))
            .filter(Account.type.in_(["ASSET", "LIABILITY", "EQUITY"]))
            .group_by(Account.id).order_by(Account.code).all())
    assets, liabilities, equity = [], [], []
    for acc, net in rows:
        item = serialize(acc, net_kobo=net)
        {"ASSET": assets, "LIABILITY": liabilities, "EQUITY": equity}[acc.type].append(item)
    pnl_data = pnl(user=user, db=db)
    return {"assets": assets, "liabilities": liabilities, "equity": equity,
            "retained_income_kobo": pnl_data["net_profit_kobo"],
            "total_assets_kobo": sum(a["net_kobo"] for a in assets),
            "total_liabilities_kobo": sum(l["net_kobo"] for l in liabilities)}


@router.get("/expenses")
def list_expenses(user: User = Depends(require_staff), db: Session = Depends(get_db), status: str = ""):
    query = db.query(Expense)
    if status:
        query = query.filter(Expense.status == status)
    return serialize_list(query.order_by(Expense.id.desc()).limit(200).all())


@router.post("/expenses")
def create_expense(body: ExpenseIn, user: User = Depends(require_perm("finance.manage")), db: Session = Depends(get_db)):
    if body.amount_kobo <= 0:
        raise HTTPException(400, "Amount must be positive")
    e = Expense(category=body.category, description=body.description, amount_kobo=body.amount_kobo,
                payment_method=body.payment_method, paid_from_account_id=body.paid_from_account_id,
                receipt_ref=body.receipt_ref, payee=body.payee, requested_by_user_id=user.id,
                status="PENDING_APPROVAL")
    db.add(e)
    db.commit()
    audit(db, user, "create", "expense", e.id, f"Expense {body.category} {body.amount_kobo} requested")
    db.commit()
    return serialize(e)


@router.post("/expenses/{expense_id}/approve")
def approve_expense(expense_id: int, user: User = Depends(require_perm("finance.manage")), db: Session = Depends(get_db)):
    e = db.get(Expense, expense_id)
    if not e:
        raise HTTPException(404, "Expense not found")
    if e.status != "PENDING_APPROVAL":
        raise HTTPException(400, f"Expense already {e.status}")
    e.status = "APPROVED"
    e.approved_by_user_id = user.id
    expense_account = get_account_by_subtype(db, "OPERATING_EXPENSE")
    source = db.get(Account, e.paid_from_account_id) if e.paid_from_account_id else get_account_by_subtype(db, "CASH")
    post_journal(db, memo=f"Expense: {e.category} - {e.description[:60]}",
                 source_type="EXPENSE", source_id=e.id,
                 lines=[{"account_id": expense_account.id, "debit_kobo": e.amount_kobo},
                        {"account_id": source.id, "credit_kobo": e.amount_kobo}],
                 posted_by=user)
    db.commit()
    audit(db, user, "approve", "expense", e.id, f"Expense #{e.id} approved and posted")
    db.commit()
    return serialize(e)


@router.post("/expenses/{expense_id}/reject")
def reject_expense(expense_id: int, user: User = Depends(require_perm("finance.manage")), db: Session = Depends(get_db)):
    e = db.get(Expense, expense_id)
    if not e:
        raise HTTPException(404, "Expense not found")
    e.status = "REJECTED"
    e.approved_by_user_id = user.id
    db.commit()
    return serialize(e)


@router.get("/bank-transactions")
def list_bank_txns(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    rows = (db.query(BankTransaction, Account)
            .join(Account, Account.id == BankTransaction.account_id)
            .order_by(BankTransaction.id.desc()).limit(200).all())
    return [serialize(t, account_name=a.name) for t, a in rows]


class BankTxnIn(BaseModel):
    account_id: int
    direction: str = "CREDIT"
    amount_kobo: int
    bank_ref: str = ""
    narration: str = ""


@router.post("/bank-transactions")
def create_bank_txn(body: BankTxnIn, user: User = Depends(require_perm("finance.manage")), db: Session = Depends(get_db)):
    t = BankTransaction(**body.model_dump())
    db.add(t)
    db.commit()
    return serialize(t)


@router.get("/periods")
def list_periods(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return serialize_list(db.query(FinancialPeriod).order_by(FinancialPeriod.name.desc()).all())
