"""Chart of accounts, journals, financial statements, expenses, bank transactions."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.db import get_db, utcnow
from app.core.deps import require_perm, require_any_perm
from app.core.serialize import serialize, serialize_list
from app.core.audit import audit
from app.modules.identity_models import User
from app.modules.ledger_models import (Account, JournalEntry, JournalLine, Expense,
                                       BankTransaction, FinancialPeriod)
from app.core.ledger import post_journal, reverse_journal, LIVE_ENTRY_STATUSES

router = APIRouter(prefix="/api/ledger", tags=["ledger"])

# Anyone who legitimately works with money (or audits it) may read the books.
require_books = require_any_perm("finance.manage", "audit.view")
PAYMENT_METHODS = ("CASH", "BANK_TRANSFER", "DIGITAL", "CARD", "POS", "CHEQUE", "OTHER")


def _live_entry_filter():
    """A line counts when it belongs to no entry (outer-join miss) or a live entry."""
    return or_(JournalEntry.id.is_(None), JournalEntry.status.in_(LIVE_ENTRY_STATUSES))

EXPENSE_CATEGORIES = ["Fuel", "Staff Salaries", "Warehouse Rent", "Utilities", "Vehicle Maintenance",
                      "Packaging", "Transport", "Communications", "Administrative", "Other"]


def get_account_by_subtype(db: Session, subtype: str) -> Account:
    acc = db.query(Account).filter(Account.subtype == subtype, Account.is_active.is_(True)).first()
    if not acc:
        raise HTTPException(500, f"Chart of accounts missing '{subtype}' - seed the ledger first")
    return acc


class AccountIn(BaseModel):
    code: str = ""
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
def list_accounts(user: User = Depends(require_books), db: Session = Depends(get_db)):
    return serialize_list(db.query(Account).order_by(Account.code).all())


@router.post("/accounts")
def create_account(body: AccountIn, user: User = Depends(require_perm("finance.manage")), db: Session = Depends(get_db)):
    if body.type not in ("ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE"):
        raise HTTPException(400, "Invalid account type")
    if not body.name.strip():
        raise HTTPException(400, "Account name is required")
    code = body.code.strip()
    if not code:
        base = {"ASSET": 1000, "LIABILITY": 2000, "EQUITY": 3000, "REVENUE": 4000, "EXPENSE": 5000}[body.type]
        used = {a.code for a in db.query(Account).filter(Account.type == body.type).all()}
        n = base + 10
        while str(n) in used or db.query(Account).filter(Account.code == str(n)).first():
            n += 1
        code = str(n)
    if db.query(Account).filter(Account.code == code).first():
        raise HTTPException(400, f"Account code {code} already exists")
    data = body.model_dump()
    data["code"] = code
    a = Account(**data)
    db.add(a)
    db.commit()
    return serialize(a)


@router.get("/journals")
def list_journals(user: User = Depends(require_books), db: Session = Depends(get_db),
                  source_type: str = "", limit: int = 100):
    limit = max(1, min(limit, 300))
    query = db.query(JournalEntry)
    if source_type:
        query = query.filter(JournalEntry.source_type == source_type)
    entries = query.order_by(JournalEntry.id.desc()).limit(limit).all()
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
    if not body.memo.strip():
        raise HTTPException(400, "A memo is required for a manual journal")
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
def trial_balance(user: User = Depends(require_books), db: Session = Depends(get_db)):
    rows = (db.query(Account,
                     func.coalesce(func.sum(JournalLine.debit_kobo), 0),
                     func.coalesce(func.sum(JournalLine.credit_kobo), 0))
            .outerjoin(JournalLine, JournalLine.account_id == Account.id)
            .outerjoin(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .filter(Account.is_active.is_(True), _live_entry_filter())
            .group_by(Account.id).order_by(Account.code).all())
    out = []
    total_d = total_c = 0
    for acc, d, c in rows:
        d, c = int(d or 0), int(c or 0)
        total_d += d
        total_c += c
        out.append(serialize(acc, debit_kobo=d, credit_kobo=c,
                             balance_kobo=(d - c) if acc.type in ("ASSET", "EXPENSE") else (c - d)))
    return {"lines": out, "total_debits_kobo": total_d, "total_credits_kobo": total_c,
            "balanced": total_d == total_c}


def _net_by_account(db: Session, types: list[str]):
    """(Account, debits - credits) for live entries, accounts of the given types."""
    return (db.query(Account,
                     func.coalesce(func.sum(JournalLine.debit_kobo - JournalLine.credit_kobo), 0))
            .outerjoin(JournalLine, JournalLine.account_id == Account.id)
            .outerjoin(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .filter(Account.type.in_(types), _live_entry_filter())
            .group_by(Account.id).order_by(Account.code).all())


@router.get("/pnl")
def pnl(user: User = Depends(require_books), db: Session = Depends(get_db)):
    revenue, expenses = [], []
    for acc, net_dc in _net_by_account(db, ["REVENUE", "EXPENSE"]):
        net_dc = int(net_dc or 0)
        if acc.type == "REVENUE":      # credit-normal: positive = income earned
            revenue.append(serialize(acc, net_kobo=-net_dc))
        else:                          # debit-normal: positive = cost incurred
            expenses.append(serialize(acc, net_kobo=net_dc))
    total_rev = sum(r["net_kobo"] for r in revenue)
    total_exp = sum(e["net_kobo"] for e in expenses)
    return {"revenue": revenue, "expenses": expenses,
            "total_revenue_kobo": total_rev, "total_expenses_kobo": total_exp,
            "net_profit_kobo": total_rev - total_exp}


@router.get("/balance-sheet")
def balance_sheet(user: User = Depends(require_books), db: Session = Depends(get_db)):
    assets, liabilities, equity = [], [], []
    for acc, net_dc in _net_by_account(db, ["ASSET", "LIABILITY", "EQUITY"]):
        net_dc = int(net_dc or 0)
        if acc.type == "ASSET":        # debit-normal
            assets.append(serialize(acc, net_kobo=net_dc))
        elif acc.type == "LIABILITY":  # credit-normal: show positive amounts owed
            liabilities.append(serialize(acc, net_kobo=-net_dc))
        else:
            equity.append(serialize(acc, net_kobo=-net_dc))
    retained = pnl(user=user, db=db)["net_profit_kobo"]
    total_assets = sum(a["net_kobo"] for a in assets)
    total_liabilities = sum(l["net_kobo"] for l in liabilities)
    total_equity = sum(e["net_kobo"] for e in equity) + retained
    return {"assets": assets, "liabilities": liabilities, "equity": equity,
            "retained_income_kobo": retained,
            "total_assets_kobo": total_assets,
            "total_liabilities_kobo": total_liabilities,
            "total_equity_kobo": total_equity,
            "balanced": total_assets == total_liabilities + total_equity}


@router.get("/expenses")
def list_expenses(user: User = Depends(require_books), db: Session = Depends(get_db), status: str = ""):
    query = db.query(Expense)
    if status:
        query = query.filter(Expense.status == status)
    return serialize_list(query.order_by(Expense.id.desc()).limit(200).all())


@router.post("/expenses")
def create_expense(body: ExpenseIn, user: User = Depends(require_perm("finance.manage")), db: Session = Depends(get_db)):
    if body.amount_kobo <= 0:
        raise HTTPException(400, "Amount must be positive")
    if body.category not in EXPENSE_CATEGORIES:
        raise HTTPException(400, f"Unknown expense category. Valid: {', '.join(EXPENSE_CATEGORIES)}")
    if body.payment_method not in PAYMENT_METHODS:
        raise HTTPException(400, f"Unknown payment method. Valid: {', '.join(PAYMENT_METHODS)}")
    if body.paid_from_account_id:
        src = db.get(Account, body.paid_from_account_id)
        if not src or src.type != "ASSET" or not src.is_active:
            raise HTTPException(400, "paid_from_account_id must be an active asset (cash/bank) account")
    when = utcnow()
    if body.expense_date:
        try:
            when = datetime.fromisoformat(body.expense_date.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            raise HTTPException(400, "expense_date must be an ISO date, e.g. 2026-11-07")
    e = Expense(category=body.category, description=body.description, amount_kobo=body.amount_kobo,
                payment_method=body.payment_method, paid_from_account_id=body.paid_from_account_id,
                receipt_ref=body.receipt_ref, payee=body.payee, requested_by_user_id=user.id,
                expense_date=when, status="PENDING_APPROVAL")
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
    if e.requested_by_user_id == user.id and not user.is_superuser:
        raise HTTPException(403, "Segregation of duties: you cannot approve an expense you requested yourself")
    expense_account = get_account_by_subtype(db, "OPERATING_EXPENSE")
    source = db.get(Account, e.paid_from_account_id) if e.paid_from_account_id else get_account_by_subtype(db, "CASH")
    if not source or not source.is_active:
        raise HTTPException(400, "The account this expense is paid from no longer exists or is inactive")
    try:
        post_journal(db, memo=f"Expense: {e.category} - {(e.description or '')[:60]}",
                     source_type="EXPENSE", source_id=e.id,
                     lines=[{"account_id": expense_account.id, "debit_kobo": e.amount_kobo},
                            {"account_id": source.id, "credit_kobo": e.amount_kobo}],
                     posted_by=user)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    e.status = "APPROVED"
    e.approved_by_user_id = user.id
    db.commit()
    audit(db, user, "approve", "expense", e.id, f"Expense #{e.id} approved and posted")
    db.commit()
    return serialize(e)


@router.post("/expenses/{expense_id}/reject")
def reject_expense(expense_id: int, user: User = Depends(require_perm("finance.manage")), db: Session = Depends(get_db)):
    e = db.get(Expense, expense_id)
    if not e:
        raise HTTPException(404, "Expense not found")
    if e.status != "PENDING_APPROVAL":
        raise HTTPException(400, f"Only pending expenses can be rejected (this one is {e.status})")
    e.status = "REJECTED"
    e.approved_by_user_id = user.id
    db.commit()
    audit(db, user, "reject", "expense", e.id, f"Expense #{e.id} rejected")
    db.commit()
    return serialize(e)


@router.get("/bank-transactions")
def list_bank_txns(user: User = Depends(require_books), db: Session = Depends(get_db)):
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
    if body.amount_kobo <= 0:
        raise HTTPException(400, "Amount must be positive")
    if body.direction not in ("CREDIT", "DEBIT"):
        raise HTTPException(400, "direction must be CREDIT or DEBIT")
    acct = db.get(Account, body.account_id)
    if not acct or acct.type != "ASSET":
        raise HTTPException(400, "account_id must be an existing bank/cash asset account")
    t = BankTransaction(**body.model_dump())
    db.add(t)
    db.commit()
    return serialize(t)


@router.get("/periods")
def list_periods(user: User = Depends(require_books), db: Session = Depends(get_db)):
    return serialize_list(db.query(FinancialPeriod).order_by(FinancialPeriod.name.desc()).all())
