from datetime import datetime
from sqlalchemy import BigInteger, String, Integer, ForeignKey, DateTime, JSON, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, utcnow


class DeliveryZone(Base):
    __tablename__ = "delivery_zones"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(80), default="", index=True)
    cities: Mapped[list] = mapped_column(JSON, default=list)
    base_fee_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Rider(Base):
    __tablename__ = "riders"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(30), default="")
    vehicle: Mapped[str] = mapped_column(String(60), default="")
    zone_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ACTIVE | OFFLINE | SUSPENDED
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Carrier(Base):
    __tablename__ = "carriers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    # LOCAL_3P | INTERSTATE
    kind: Mapped[str] = mapped_column(String(20), default="INTERSTATE")
    contact_phone: Mapped[str] = mapped_column(String(30), default="")
    tracking_url: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Waybill(Base):
    __tablename__ = "waybills"
    id: Mapped[int] = mapped_column(primary_key=True)
    waybill_no: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    carrier_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    destination_state: Mapped[str] = mapped_column(String(80), default="")
    total_parcels: Mapped[int] = mapped_column(Integer, default=0)
    dispatch_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # PREPARING | IN_TRANSIT | DELIVERED | RECEIVED
    status: Mapped[str] = mapped_column(String(20), default="PREPARING")
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Delivery(Base):
    __tablename__ = "deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    # IN_HOUSE_RIDER | LOCAL_3P | INTERSTATE | WAYBILL
    mode: Mapped[str] = mapped_column(String(20), default="IN_HOUSE_RIDER")
    # PENDING_ASSIGNMENT | ASSIGNED | PICKED_UP | DISPATCHED | IN_TRANSIT |
    # OUT_FOR_DELIVERY | DELIVERED | FAILED | RETURNING | RETURNED
    status: Mapped[str] = mapped_column(String(30), default="PENDING_ASSIGNMENT", index=True)
    zone_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rider_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    carrier_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    waybill_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fee_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    dispatch_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failure_reason: Mapped[str] = mapped_column(String(255), default="")
    proof_ref: Mapped[str] = mapped_column(String(255), default="")
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DeliveryAssignment(Base):
    __tablename__ = "delivery_assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_id: Mapped[int] = mapped_column(Integer, index=True)
    rider_id: Mapped[int] = mapped_column(Integer, index=True)
    assigned_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # ASSIGNED | ACCEPTED | REJECTED | COMPLETED
    status: Mapped[str] = mapped_column(String(20), default="ASSIGNED")
