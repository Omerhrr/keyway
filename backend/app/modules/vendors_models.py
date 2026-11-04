from datetime import datetime
from sqlalchemy import String, Boolean, Integer, ForeignKey, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, utcnow


class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)  # vendor reference code
    name: Mapped[str] = mapped_column(String(160))
    business_name: Mapped[str] = mapped_column(String(160), default="")
    email: Mapped[str] = mapped_column(String(120), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    state: Mapped[str] = mapped_column(String(80), default="")
    # PENDING | ACTIVE | SUSPENDED | INACTIVE
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    auto_confirm_orders: Mapped[bool] = mapped_column(Boolean, default=False)
    # WEEKLY | BIWEEKLY | MONTHLY | ON_REQUEST
    settlement_frequency: Mapped[str] = mapped_column(String(20), default="WEEKLY")
    pricing_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class VendorContact(Base):
    __tablename__ = "vendor_contacts"
    __table_args__ = (UniqueConstraint("phone", name="uq_contact_phone"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(30), index=True)  # canonical +234...
    email: Mapped[str] = mapped_column(String(120), default="")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_whatsapp: Mapped[bool] = mapped_column(Boolean, default=True)
    wa_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    # PHONE_NUMBER | WHATSAPP_BUSINESS | VENDOR_CODE | STAFF_ASSISTED
    verification_method: Mapped[str] = mapped_column(String(30), default="")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class VendorAgreement(Base):
    __tablename__ = "vendor_agreements"
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    terms: Mapped[str] = mapped_column(Text, default="")
    effective_from: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    document_ref: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
