from datetime import datetime
from sqlalchemy import String, Boolean, Integer, ForeignKey, DateTime, Text, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, utcnow

# NOTE: variant_id uses 0 for "no variant", location_id 0 for "unassigned" so that
# SQLite unique constraints behave deterministically (NULL != NULL in SQLite).


class Warehouse(Base):
    __tablename__ = "warehouses"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str] = mapped_column(String(255), default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    state: Mapped[str] = mapped_column(String(80), default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WarehouseLocation(Base):
    __tablename__ = "warehouse_locations"
    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    code: Mapped[str] = mapped_column(String(60))
    # SHELF | STAGING | DAMAGED | RETURNS
    kind: Mapped[str] = mapped_column(String(20), default="SHELF")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class InventoryBalance(Base):
    __tablename__ = "inventory_balances"
    __table_args__ = (UniqueConstraint("product_id", "variant_id", "warehouse_id", "location_id", name="uq_balance"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    variant_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    location_id: Mapped[int] = mapped_column(Integer, default=0)
    qty_physical: Mapped[int] = mapped_column(Integer, default=0)
    qty_reserved: Mapped[int] = mapped_column(Integer, default=0)
    qty_damaged: Mapped[int] = mapped_column(Integer, default=0)
    qty_in_transit: Mapped[int] = mapped_column(Integer, default=0)

    @property
    def qty_available(self) -> int:
        return self.qty_physical - self.qty_reserved


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    variant_id: Mapped[int] = mapped_column(Integer, default=0)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    # RECEIVE | ADJUST | RESERVE | RELEASE | DEDUCT | RETURN | TRANSFER_IN | TRANSFER_OUT | DAMAGE
    movement_type: Mapped[str] = mapped_column(String(20), index=True)
    qty: Mapped[int] = mapped_column(Integer)  # signed
    reason: Mapped[str] = mapped_column(String(255), default="")
    ref_type: Mapped[str] = mapped_column(String(40), default="")
    ref_id: Mapped[str] = mapped_column(String(40), default="")
    batch_ref: Mapped[str] = mapped_column(String(60), default="")
    actor_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class StockReceipt(Base):
    __tablename__ = "stock_receipts"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))
    batch_ref: Mapped[str] = mapped_column(String(60), default="")
    # DRAFT | CONFIRMED | CANCELLED
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class StockReceiptLine(Base):
    __tablename__ = "stock_receipt_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("stock_receipts.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    variant_id: Mapped[int] = mapped_column(Integer, default=0)
    expected_qty: Mapped[int] = mapped_column(Integer, default=0)
    received_qty: Mapped[int] = mapped_column(Integer, default=0)
    damaged_qty: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(String(255), default="")


class StockTransfer(Base):
    __tablename__ = "stock_transfers"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    variant_id: Mapped[int] = mapped_column(Integer, default=0)
    from_warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    to_warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    qty: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(255), default="")
    # IN_TRANSIT | RECEIVED | CANCELLED
    status: Mapped[str] = mapped_column(String(20), default="IN_TRANSIT", index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class StockReservation(Base):
    __tablename__ = "stock_reservations"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    variant_id: Mapped[int] = mapped_column(Integer, default=0)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))
    qty: Mapped[int] = mapped_column(Integer)
    # ACTIVE | RELEASED | CONSUMED
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    released_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
