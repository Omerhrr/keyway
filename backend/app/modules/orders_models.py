from datetime import datetime
from sqlalchemy import BigInteger, String, Boolean, Integer, ForeignKey, DateTime, Text, JSON, UniqueConstraint, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, utcnow


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("vendor_id", "phone", name="uq_vendor_customer_phone"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str] = mapped_column(String(30), index=True)
    alt_phone: Mapped[str] = mapped_column(String(30), default="")
    email: Mapped[str] = mapped_column(String(120), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CustomerAddress(Base):
    __tablename__ = "customer_addresses"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    label: Mapped[str] = mapped_column(String(60), default="Home")
    state: Mapped[str] = mapped_column(String(80), default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    area: Mapped[str] = mapped_column(String(120), default="")
    street: Mapped[str] = mapped_column(String(255), default="")
    landmark: Mapped[str] = mapped_column(String(255), default="")
    gps_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OrderDraft(Base):
    __tablename__ = "order_drafts"
    id: Mapped[int] = mapped_column(primary_key=True)
    draft_ref: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    vendor_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # WHATSAPP | PORTAL | MANUAL | CSV | EXCEL | API
    source: Mapped[str] = mapped_column(String(20), default="WHATSAPP")
    # PENDING_REVIEW | AWAITING_VENDOR | CONFIRMED | CONVERTED | DISCARDED
    status: Mapped[str] = mapped_column(String(30), default="PENDING_REVIEW", index=True)
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)
    product_candidates: Mapped[list] = mapped_column(JSON, default=list)
    missing_fields: Mapped[list] = mapped_column(JSON, default=list)
    duplicate_of_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    review_notes: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    converted_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    vendor_id: Mapped[int] = mapped_column(Integer, index=True)
    customer_id: Mapped[int] = mapped_column(Integer, index=True)
    warehouse_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # see PRD order_statuses: DRAFT ... CANCELLED
    status: Mapped[str] = mapped_column(String(40), default="CONFIRMED", index=True)
    # COD | BANK_TRANSFER | OTHER
    payment_method: Mapped[str] = mapped_column(String(30), default="COD")
    source: Mapped[str] = mapped_column(String(20), default="WHATSAPP")
    source_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    draft_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # delivery address snapshot
    delivery_state: Mapped[str] = mapped_column(String(80), default="")
    delivery_city: Mapped[str] = mapped_column(String(80), default="")
    delivery_area: Mapped[str] = mapped_column(String(120), default="")
    delivery_street: Mapped[str] = mapped_column(String(255), default="")
    delivery_landmark: Mapped[str] = mapped_column(String(255), default="")
    delivery_gps: Mapped[str] = mapped_column(String(80), default="")
    instructions: Mapped[str] = mapped_column(Text, default="")
    items_total_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    delivery_fee_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    cod_amount_kobo: Mapped[int] = mapped_column(BigInteger, default=0)  # expected COD
    assigned_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_reason: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    variant_id: Mapped[int] = mapped_column(Integer, default=0)
    name_snapshot: Mapped[str] = mapped_column(String(220))
    sku_snapshot: Mapped[str] = mapped_column(String(80), default="")
    qty: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    line_total_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    # EXTRACTED | DEFAULT | MANUAL
    price_source: Mapped[str] = mapped_column(String(20), default="DEFAULT")


class OrderEvent(Base):
    __tablename__ = "order_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40), default="STATUS_CHANGE")
    from_status: Mapped[str] = mapped_column(String(40), default="")
    to_status: Mapped[str] = mapped_column(String(40), default="")
    actor_label: Mapped[str] = mapped_column(String(120), default="system")
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class CustomerConfirmation(Base):
    __tablename__ = "customer_confirmations"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    agent_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # NOT_STARTED | CALL_ATTEMPTED | NO_ANSWER | CUSTOMER_CONFIRMED |
    # CUSTOMER_REQUESTED_RESCHEDULE | ADDRESS_NEEDS_CORRECTION | CUSTOMER_REJECTED | INVALID_PHONE_NUMBER
    status: Mapped[str] = mapped_column(String(40), default="NOT_STARTED", index=True)
    outcome_note: Mapped[str] = mapped_column(String(255), default="")
    attempts_count: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ConfirmationAttempt(Base):
    __tablename__ = "confirmation_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    confirmation_id: Mapped[int] = mapped_column(ForeignKey("customer_confirmations.id"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    outcome: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(String(255), default="")
    by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
