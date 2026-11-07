from datetime import datetime
from sqlalchemy import BigInteger, String, Boolean, Integer, ForeignKey, DateTime, Text, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, utcnow


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("vendor_id", "sku", name="uq_vendor_sku"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    sku: Mapped[str] = mapped_column(String(60), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(80), default="")
    unit: Mapped[str] = mapped_column(String(20), default="pcs")
    default_sell_price_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    reorder_level: Mapped[int] = mapped_column(Integer, default=5)
    image_ref: Mapped[str] = mapped_column(String(255), default="")
    # ACTIVE | ARCHIVED
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ProductVariant(Base):
    __tablename__ = "product_variants"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    sku: Mapped[str] = mapped_column(String(60), index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    barcode: Mapped[str] = mapped_column(String(60), default="")
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    sell_price_kobo: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # overrides product default
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ProductAlias(Base):
    __tablename__ = "product_aliases"
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    variant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alias: Mapped[str] = mapped_column(String(160), index=True)
    weight: Mapped[int] = mapped_column(Integer, default=90)  # match priority hint
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
