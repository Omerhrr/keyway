from datetime import datetime
from sqlalchemy import BigInteger, String, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, utcnow


class CODCollection(Base):
    __tablename__ = "cod_collections"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer, index=True)
    delivery_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    collected_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    # CASH | BANK_TRANSFER | DIGITAL
    method: Mapped[str] = mapped_column(String(20), default="CASH")
    collected_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rider_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # PENDING_VERIFICATION | VERIFIED | DISCREPANCY | UNVERIFIED
    status: Mapped[str] = mapped_column(String(30), default="PENDING_VERIFICATION", index=True)
    discrepancy_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    handover_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verified_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CashHandover(Base):
    __tablename__ = "cash_handovers"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    rider_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # who hands over
    handed_to_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_expected_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    amount_counted_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    # PENDING | CONFIRMED | DISCREPANCY
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    handed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
