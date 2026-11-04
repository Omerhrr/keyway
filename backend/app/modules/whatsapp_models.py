from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, utcnow


class WhatsAppAccount(Base):
    __tablename__ = "whatsapp_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), default="Keyway Logistics")
    phone_number_id: Mapped[str] = mapped_column(String(60), default="")
    waba_id: Mapped[str] = mapped_column(String(60), default="")
    # SIMULATOR | CLOUD_API
    mode: Mapped[str] = mapped_column(String(20), default="SIMULATOR")
    # CONNECTED | DISCONNECTED
    status: Mapped[str] = mapped_column(String(20), default="CONNECTED")
    access_token_enc: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MessageTemplate(Base):
    __tablename__ = "message_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(40), default="UTILITY")
    language: Mapped[str] = mapped_column(String(10), default="en")
    body: Mapped[str] = mapped_column(Text)  # may contain {{1}}, {{2}} placeholders
    variables: Mapped[list] = mapped_column(JSON, default=list)
    # APPROVED | PENDING | DISABLED
    status: Mapped[str] = mapped_column(String(20), default="APPROVED")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
