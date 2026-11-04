from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, utcnow


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(20), default="WHATSAPP")
    vendor_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    contact_phone: Mapped[str] = mapped_column(String(30), index=True)
    contact_name: Mapped[str] = mapped_column(String(120), default="")
    wa_contact_id: Mapped[str] = mapped_column(String(60), default="")
    # NEW | OPEN | PROCESSING | WAITING_FOR_VENDOR | WAITING_FOR_STAFF | RESOLVED | ARCHIVED
    status: Mapped[str] = mapped_column(String(30), default="NEW", index=True)
    assigned_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    label: Mapped[str] = mapped_column(String(60), default="")
    unread_count: Mapped[int] = mapped_column(Integer, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_message_preview: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    # IN | OUT
    direction: Mapped[str] = mapped_column(String(10), index=True)
    wa_message_id: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True, index=True)
    # text | image | audio | voice | document | location | contacts | system
    msg_type: Mapped[str] = mapped_column(String(20), default="text")
    body_text: Mapped[str] = mapped_column(Text, default="")
    media_ref: Mapped[str] = mapped_column(String(255), default="")
    # RECEIVED | QUEUED | SENT | DELIVERED | READ | FAILED
    status: Mapped[str] = mapped_column(String(20), default="RECEIVED", index=True)
    intent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class MessageAttachment(Base):
    __tablename__ = "message_attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="document")
    mime: Mapped[str] = mapped_column(String(80), default="")
    file_name: Mapped[str] = mapped_column(String(160), default="")
    storage_ref: Mapped[str] = mapped_column(String(255), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MessageProcessingAttempt(Base):
    __tablename__ = "message_processing_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    # OK | NEEDS_REVIEW | FAILED | ASKED_VENDOR
    status: Mapped[str] = mapped_column(String(30), index=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class VendorIdentityMatch(Base):
    __tablename__ = "vendor_identity_matches"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phone: Mapped[str] = mapped_column(String(30), index=True)
    matched_vendor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # PHONE_NUMBER | WHATSAPP_BUSINESS | VENDOR_CODE | STAFF_ASSISTED | NONE
    method: Mapped[str] = mapped_column(String(30), default="NONE")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    # AUTO | PENDING | MATCHED_MANUAL
    status: Mapped[str] = mapped_column(String(30), default="AUTO", index=True)
    decided_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
