from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, utcnow


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    actor_label: Mapped[str] = mapped_column(String(120), default="system")
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(60), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    summary: Mapped[str] = mapped_column(String(255), default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str] = mapped_column(String(60), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    # IN_APP | WHATSAPP | EMAIL | SMS
    channel: Mapped[str] = mapped_column(String(20), default="IN_APP", index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    vendor_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_type: Mapped[str] = mapped_column(String(60), default="")
    title: Mapped[str] = mapped_column(String(160), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    entity_type: Mapped[str] = mapped_column(String(60), default="")
    entity_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # UNREAD | READ | SENT | FAILED
    status: Mapped[str] = mapped_column(String(20), default="UNREAD", index=True)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    # idempotency: same event re-fired for the same entity does not duplicate
    dedup_key: Mapped[str] = mapped_column(String(160), default="", index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class NotificationRule(Base):
    """Advanced notification rules (PRD: notifications_and_automation).
    Routes an event_type to staff (ALL_STAFF), a whole role, or one user,
    on a chosen channel. Falls back to ALL_STAFF in-app when no rule matches."""
    __tablename__ = "notification_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # ALL_STAFF | ROLE | USER
    target_scope: Mapped[str] = mapped_column(String(20), default="ALL_STAFF")
    role_name: Mapped[str] = mapped_column(String(80), default="")
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # IN_APP | WHATSAPP | EMAIL | SMS
    channel: Mapped[str] = mapped_column(String(20), default="IN_APP")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
