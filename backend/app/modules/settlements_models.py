from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, utcnow


class Settlement(Base):
    __tablename__ = "settlements"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    vendor_id: Mapped[int] = mapped_column(Integer, index=True)
    period_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    gross_kobo: Mapped[int] = mapped_column(Integer, default=0)
    charges_kobo: Mapped[int] = mapped_column(Integer, default=0)
    deductions_kobo: Mapped[int] = mapped_column(Integer, default=0)
    adjustments_kobo: Mapped[int] = mapped_column(Integer, default=0)
    net_kobo: Mapped[int] = mapped_column(Integer, default=0)
    # PENDING_RECONCILIATION | READY_FOR_APPROVAL | APPROVED | PARTIALLY_PAID |
    # PAID | ON_HOLD | DISPUTED | REVERSED
    status: Mapped[str] = mapped_column(String(30), default="READY_FOR_APPROVAL", index=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_kobo: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SettlementItem(Base):
    __tablename__ = "settlement_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey("settlements.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    collection_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    charge_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # COLLECTION | CHARGE | ADJUSTMENT
    type: Mapped[str] = mapped_column(String(20))
    gross_kobo: Mapped[int] = mapped_column(Integer, default=0)
    deduction_kobo: Mapped[int] = mapped_column(Integer, default=0)
    net_kobo: Mapped[int] = mapped_column(Integer, default=0)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    settlement_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    vendor_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    direction: Mapped[str] = mapped_column(String(20), default="VENDOR_PAYOUT")
    amount_kobo: Mapped[int] = mapped_column(Integer, default=0)
    method: Mapped[str] = mapped_column(String(30), default="BANK_TRANSFER")
    bank_ref: Mapped[str] = mapped_column(String(80), default="")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recorded_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
