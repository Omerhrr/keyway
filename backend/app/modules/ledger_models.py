from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, utcnow


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    # ASSET | LIABILITY | EQUITY | REVENUE | EXPENSE
    type: Mapped[str] = mapped_column(String(20), index=True)
    # CASH | BANK | COD_CLEARING | VENDOR_PAYABLE | LOGISTICS_REVENUE | OPERATING_EXPENSE | ...
    subtype: Mapped[str] = mapped_column(String(40), default="")
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_cash: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    entry_no: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    entry_date: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    memo: Mapped[str] = mapped_column(String(255), default="")
    # COD_COLLECTION | CHARGE_RECOGNITION | SETTLEMENT_PAYOUT | EXPENSE | MANUAL | REVERSAL | OPENING
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # DRAFT | POSTED | REVERSED
    status: Mapped[str] = mapped_column(String(20), default="POSTED", index=True)
    reversal_of_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    posted_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class JournalLine(Base):
    __tablename__ = "journal_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("journal_entries.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    debit_kobo: Mapped[int] = mapped_column(Integer, default=0)
    credit_kobo: Mapped[int] = mapped_column(Integer, default=0)
    vendor_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    memo: Mapped[str] = mapped_column(String(255), default="")


class Expense(Base):
    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(60), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    amount_kobo: Mapped[int] = mapped_column(Integer, default=0)
    payment_method: Mapped[str] = mapped_column(String(30), default="CASH")
    paid_from_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    receipt_ref: Mapped[str] = mapped_column(String(255), default="")
    payee: Mapped[str] = mapped_column(String(160), default="")
    # PENDING_APPROVAL | APPROVED | REJECTED | PAID
    status: Mapped[str] = mapped_column(String(20), default="PENDING_APPROVAL", index=True)
    requested_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expense_date: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BankTransaction(Base):
    __tablename__ = "bank_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(Integer, index=True)
    txn_date: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    direction: Mapped[str] = mapped_column(String(10), default="CREDIT")  # CREDIT | DEBIT
    amount_kobo: Mapped[int] = mapped_column(Integer, default=0)
    bank_ref: Mapped[str] = mapped_column(String(80), default="")
    narration: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Reconciliation(Base):
    __tablename__ = "reconciliations"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), default="BANK")  # BANK | COD | CASH
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period_label: Mapped[str] = mapped_column(String(40), default="")
    # OPEN | CLOSED
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    opened_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    closed_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FinancialPeriod(Base):
    __tablename__ = "financial_periods"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # e.g. 2026-11
    start_date: Mapped[datetime] = mapped_column(DateTime)
    end_date: Mapped[datetime] = mapped_column(DateTime)
    # OPEN | CLOSED
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
