from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, utcnow


class ChargeRule(Base):
    __tablename__ = "charge_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    # ORDER_PROCESSING | LOCAL_DELIVERY | INTERSTATE_DISPATCH | WAYBILL | STORAGE |
    # COD_HANDLING | RETURN_HANDLING | SPECIAL_HANDLING | OTHER
    charge_type: Mapped[str] = mapped_column(String(40), index=True)
    # GLOBAL | VENDOR | ZONE
    scope: Mapped[str] = mapped_column(String(20), default="GLOBAL", index=True)
    vendor_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    zone_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # FIXED | PERCENT | PER_QTY | PER_KG
    basis: Mapped[str] = mapped_column(String(20), default="FIXED")
    amount_kobo: Mapped[int] = mapped_column(Integer, default=0)
    percent: Mapped[float] = mapped_column(Float, default=0.0)
    effective_from: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Charge(Base):
    __tablename__ = "charges"
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(Integer, index=True)
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    settlement_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    charge_type: Mapped[str] = mapped_column(String(40))
    basis: Mapped[str] = mapped_column(String(20), default="FIXED")
    amount_kobo: Mapped[int] = mapped_column(Integer, default=0)
    rule_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rule_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(String(255), default="")
    # APPLIED | ADJUSTED | REVERSED
    status: Mapped[str] = mapped_column(String(20), default="APPLIED", index=True)
    applied_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
