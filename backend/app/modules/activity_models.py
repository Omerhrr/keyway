from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, JSON
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
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
