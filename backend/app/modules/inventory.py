from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.db import get_db, utcnow
from app.core.deps import require_staff, require_perm
from app.core.serialize import serialize, serialize_list
from app.core.audit import audit
from app.core.ids import next_ref
from app.core.money import naira_to_kobo
from app.modules.identity_models import User
from app.modules.inventory_models import (Warehouse, WarehouseLocation, InventoryBalance,
                                          InventoryMovement, StockReceipt, StockReceiptLine,
                                          StockReservation, StockTransfer)
from app.modules.catalog_models import Product, ProductVariant
from app.modules.vendors_models import Vendor

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


class WarehouseIn(BaseModel):
    code: str
    name: str
    address: str = ""
    city: str = ""
    state: str = ""
    is_default: bool = False


class LocationIn(BaseModel):
    warehouse_id: int
    code: str
    kind: str = "SHELF"


class AdjustIn(BaseModel):
    balance_id: int
    delta_physical: int = 0
    delta_damaged: int = 0
    reason: str


class ReceiptLineIn(BaseModel):
    product_id: int
    variant_id: int = 0
    expected_qty: int = 0
    received_qty: int = 0
    damaged_qty: int = 0
    note: str = ""


class ReceiptIn(BaseModel):
    vendor_id: int
    warehouse_id: int
    batch_ref: str = ""
    notes: str = ""
    lines: list[ReceiptLineIn]


class TransferIn(BaseModel):
    product_id: int
    variant_id: int = 0
    from_warehouse_id: int
    to_warehouse_id: int
    qty: int
    reason: str = ""


def default_warehouse(db: Session) -> Warehouse:
    w = db.query(Warehouse).filter(Warehouse.is_default.is_(True)).first() or db.query(Warehouse).first()
    if not w:
        raise HTTPException(400, "No warehouse configured")
    return w


def get_or_create_balance(db: Session, product_id: int, variant_id: int, warehouse_id: int) -> InventoryBalance:
    b = (db.query(InventoryBalance)
         .filter(InventoryBalance.product_id == product_id,
                 InventoryBalance.variant_id == (variant_id or 0),
                 InventoryBalance.warehouse_id == warehouse_id,
                 InventoryBalance.location_id == 0).first())
    if not b:
        b = InventoryBalance(product_id=product_id, variant_id=variant_id or 0,
                             warehouse_id=warehouse_id, location_id=0)
        db.add(b)
        db.flush()
    return b


def _movement(db, product_id, variant_id, warehouse_id, mtype, qty, reason="", ref_type="", ref_id="", actor=None):
    db.add(InventoryMovement(product_id=product_id, variant_id=variant_id or 0,
                             warehouse_id=warehouse_id, movement_type=mtype, qty=qty,
                             reason=reason, ref_type=ref_type, ref_id=str(ref_id or ""),
                             actor_user_id=actor.id if actor else None))


def reserve_stock(db, order_id, product_id, variant_id, warehouse_id, qty, actor=None):
    """Reserve stock for an order. Raises 400 if available stock is insufficient.
    Stock must never go negative through ordinary order processing (PRD rule)."""
    b = get_or_create_balance(db, product_id, variant_id, warehouse_id)
    available = b.qty_physical - b.qty_reserved
    if available < qty:
        raise HTTPException(400, f"Insufficient stock: only {available} available, {qty} requested")
    b.qty_reserved += qty
    db.add(StockReservation(order_id=order_id, product_id=product_id, variant_id=variant_id or 0,
                            warehouse_id=warehouse_id, qty=qty, status="ACTIVE"))
    db.flush()
    _movement(db, product_id, variant_id, warehouse_id, "RESERVE", qty, f"Reserved for order #{order_id}", "order", order_id, actor)


def release_reservations(db, order_id, actor=None):
    res = db.query(StockReservation).filter(StockReservation.order_id == order_id,
                                            StockReservation.status == "ACTIVE").all()
    for r in res:
        b = get_or_create_balance(db, r.product_id, r.variant_id, r.warehouse_id)
        b.qty_reserved = max(0, b.qty_reserved - r.qty)
        r.status = "RELEASED"
        r.released_at = utcnow()
        _movement(db, r.product_id, r.variant_id, r.warehouse_id, "RELEASE", -r.qty,
                  f"Reservation released for order #{order_id}", "order", order_id, actor)


def consume_reservations(db, order_id, actor=None):
    """On successful delivery: reserved stock leaves the warehouse physically."""
    res = db.query(StockReservation).filter(StockReservation.order_id == order_id,
                                            StockReservation.status == "ACTIVE").all()
    for r in res:
        b = get_or_create_balance(db, r.product_id, r.variant_id, r.warehouse_id)
        b.qty_reserved = max(0, b.qty_reserved - r.qty)
        b.qty_physical = max(0, b.qty_physical - r.qty)
        r.status = "CONSUMED"
        _movement(db, r.product_id, r.variant_id, r.warehouse_id, "DEDUCT", -r.qty,
                  f"Delivered order #{order_id}", "order", order_id, actor)


def restock_return(db, order_id, actor=None):
    """Returned goods back to available stock (restocking rule: back to physical, reservation freed)."""
    res = db.query(StockReservation).filter(StockReservation.order_id == order_id,
                                            StockReservation.status == "ACTIVE").all()
    for r in res:
        b = get_or_create_balance(db, r.product_id, r.variant_id, r.warehouse_id)
        b.qty_reserved = max(0, b.qty_reserved - r.qty)
        b.qty_damaged += r.qty  # returns go to damaged/returns pending inspection
        r.status = "RELEASED"
        _movement(db, r.product_id, r.variant_id, r.warehouse_id, "RETURN", r.qty,
                  f"Return from order #{order_id} pending inspection", "order", order_id, actor)


@router.get("/warehouses")
def list_warehouses(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    ws = db.query(Warehouse).order_by(Warehouse.id).all()
    locs = db.query(WarehouseLocation).all()
    return [serialize(w, locations=serialize_list([l for l in locs if l.warehouse_id == w.id])) for w in ws]


@router.post("/warehouses")
def create_warehouse(body: WarehouseIn, user: User = Depends(require_perm("inventory.manage")), db: Session = Depends(get_db)):
    if db.query(Warehouse).filter(Warehouse.code == body.code).first():
        raise HTTPException(400, "Warehouse code exists")
    w = Warehouse(**body.model_dump())
    db.add(w)
    db.commit()
    return serialize(w)


@router.post("/locations")
def create_location(body: LocationIn, user: User = Depends(require_perm("inventory.manage")), db: Session = Depends(get_db)):
    l = WarehouseLocation(**body.model_dump())
    db.add(l)
    db.commit()
    return serialize(l)


@router.get("/balances")
def balances(user: User = Depends(require_staff), db: Session = Depends(get_db),
             vendor_id: int = 0, warehouse_id: int = 0, q: str = "", low_stock: bool = False):
    query = (db.query(InventoryBalance, Product, Vendor)
             .join(Product, Product.id == InventoryBalance.product_id)
             .join(Vendor, Vendor.id == Product.vendor_id))
    if vendor_id:
        query = query.filter(Product.vendor_id == vendor_id)
    if warehouse_id:
        query = query.filter(InventoryBalance.warehouse_id == warehouse_id)
    if q:
        query = query.filter(Product.name.ilike(f"%{q}%"))
    rows = query.order_by(Product.name).all()
    out = []
    whs = {w.id: w.name for w in db.query(Warehouse).all()}
    for b, p, v in rows:
        available = b.qty_physical - b.qty_reserved
        if low_stock and available > p.reorder_level:
            continue
        out.append(serialize(b, product_name=p.name, sku=p.sku, variant_name="", vendor_name=v.name,
                             vendor_id=p.vendor_id, reorder_level=p.reorder_level,
                             warehouse_name=whs.get(b.warehouse_id, ""),
                             qty_available=available, low_stock=available <= p.reorder_level,
                             value_kobo=available * (p.default_sell_price_kobo or 0)))
    return out


@router.get("/movements")
def movements(user: User = Depends(require_staff), db: Session = Depends(get_db),
              product_id: int = 0, warehouse_id: int = 0, mtype: str = "", limit: int = 200):
    query = (db.query(InventoryMovement, Product)
             .join(Product, Product.id == InventoryMovement.product_id))
    if product_id:
        query = query.filter(InventoryMovement.product_id == product_id)
    if warehouse_id:
        query = query.filter(InventoryMovement.warehouse_id == warehouse_id)
    if mtype:
        query = query.filter(InventoryMovement.movement_type == mtype)
    rows = query.order_by(InventoryMovement.id.desc()).limit(min(limit, 500)).all()
    return [serialize(m, product_name=p.name, sku=p.sku) for m, p in rows]


@router.post("/adjust")
def adjust(body: AdjustIn, user: User = Depends(require_perm("inventory.manage")), db: Session = Depends(get_db)):
    """Stock adjustments require authorization and a recorded reason (PRD rule)."""
    b = db.get(InventoryBalance, body.balance_id)
    if not b:
        raise HTTPException(404, "Balance not found")
    if not body.reason.strip():
        raise HTTPException(400, "A reason is required for every stock adjustment")
    b.qty_physical = max(0, b.qty_physical + body.delta_physical)
    b.qty_damaged = max(0, b.qty_damaged + body.delta_damaged)
    if body.delta_physical:
        _movement(db, b.product_id, b.variant_id, b.warehouse_id, "ADJUST", body.delta_physical, body.reason, "manual", "", user)
    if body.delta_damaged:
        _movement(db, b.product_id, b.variant_id, b.warehouse_id, "DAMAGE", body.delta_damaged, body.reason, "manual", "", user)
    db.commit()
    audit(db, user, "adjust", "inventory_balance", b.id, f"Stock adjust: {body.reason}",
          data={"delta_physical": body.delta_physical, "delta_damaged": body.delta_damaged})
    db.commit()
    from app.modules.notify import run_automation_checks
    run_automation_checks(db)  # low-stock alerts after adjustments (idempotent)
    return serialize(b)


@router.get("/receipts")
def list_receipts(user: User = Depends(require_staff), db: Session = Depends(get_db), status: str = ""):
    query = (db.query(StockReceipt, Vendor, Warehouse)
             .join(Vendor, Vendor.id == StockReceipt.vendor_id)
             .join(Warehouse, Warehouse.id == StockReceipt.warehouse_id))
    if status:
        query = query.filter(StockReceipt.status == status)
    rows = query.order_by(StockReceipt.id.desc()).limit(200).all()
    out = []
    for r, v, w in rows:
        lines = db.query(StockReceiptLine).filter(StockReceiptLine.receipt_id == r.id).all()
        out.append(serialize(r, vendor_name=v.name, warehouse_name=w.name,
                             total_expected=sum(l.expected_qty for l in lines),
                             total_received=sum(l.received_qty for l in lines),
                             line_count=len(lines)))
    return out


@router.get("/receipts/{receipt_id}")
def get_receipt(receipt_id: int, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    r = db.get(StockReceipt, receipt_id)
    if not r:
        raise HTTPException(404, "Receipt not found")
    lines = (db.query(StockReceiptLine, Product)
             .join(Product, Product.id == StockReceiptLine.product_id)
             .filter(StockReceiptLine.receipt_id == receipt_id).all())
    v = db.get(Vendor, r.vendor_id)
    w = db.get(Warehouse, r.warehouse_id)
    return serialize(r, vendor_name=v.name if v else "", warehouse_name=w.name if w else "",
                     lines=[serialize(l, product_name=p.name, sku=p.sku) for l, p in lines])


@router.post("/receipts")
def create_receipt(body: ReceiptIn, user: User = Depends(require_perm("inventory.manage")), db: Session = Depends(get_db)):
    if not body.lines:
        raise HTTPException(400, "At least one product line is required")
    r = StockReceipt(reference="PENDING", vendor_id=body.vendor_id, warehouse_id=body.warehouse_id,
                     batch_ref=body.batch_ref, notes=body.notes, created_by_user_id=user.id, status="DRAFT")
    db.add(r)
    db.flush()
    r.reference = next_ref(db, StockReceipt, "reference", "RCV")
    for line in body.lines:
        p = db.get(Product, line.product_id)
        if not p:
            raise HTTPException(400, f"Product {line.product_id} not found")
        if p.vendor_id != body.vendor_id:
            raise HTTPException(400, f"Product {p.name} does not belong to this vendor (vendor-owned inventory rule)")
        db.add(StockReceiptLine(receipt_id=r.id, product_id=line.product_id,
                                variant_id=line.variant_id or 0, expected_qty=line.expected_qty,
                                received_qty=line.received_qty, damaged_qty=line.damaged_qty, note=line.note))
    db.commit()
    audit(db, user, "create", "stock_receipt", r.id, f"Stock receipt {r.reference} created")
    db.commit()
    return serialize(r)


@router.post("/receipts/{receipt_id}/confirm")
def confirm_receipt(receipt_id: int, user: User = Depends(require_perm("inventory.manage")), db: Session = Depends(get_db)):
    r = db.get(StockReceipt, receipt_id)
    if not r:
        raise HTTPException(404, "Receipt not found")
    if r.status != "DRAFT":
        raise HTTPException(400, f"Receipt already {r.status}")
    lines = db.query(StockReceiptLine).filter(StockReceiptLine.receipt_id == r.id).all()
    for l in lines:
        if l.received_qty <= 0 and l.damaged_qty <= 0:
            continue
        b = get_or_create_balance(db, l.product_id, l.variant_id, r.warehouse_id)
        b.qty_physical += l.received_qty
        b.qty_damaged += l.damaged_qty
        if l.received_qty:
            _movement(db, l.product_id, l.variant_id, r.warehouse_id, "RECEIVE", l.received_qty,
                      f"Stock receipt {r.reference}", "stock_receipt", r.id, user)
        if l.damaged_qty:
            _movement(db, l.product_id, l.variant_id, r.warehouse_id, "DAMAGE", l.damaged_qty,
                      f"Damaged in receipt {r.reference}", "stock_receipt", r.id, user)
    r.status = "CONFIRMED"
    r.confirmed_at = utcnow()
    db.commit()
    audit(db, user, "confirm", "stock_receipt", r.id, f"Stock receipt {r.reference} confirmed")
    db.commit()
    from app.modules.notify import run_automation_checks
    run_automation_checks(db)  # low-stock alerts after stock changes (idempotent)
    return serialize(r)


# ---- multi-warehouse stock transfers ----------------------------------------

def _transfer_row(db, t: StockTransfer):
    p = db.get(Product, t.product_id)
    v = db.get(Vendor, p.vendor_id) if p else None
    fw = db.get(Warehouse, t.from_warehouse_id)
    tw = db.get(Warehouse, t.to_warehouse_id)
    return serialize(t, product_name=p.name if p else "", sku=p.sku if p else "",
                     vendor_name=v.name if v else "", vendor_id=p.vendor_id if p else None,
                     from_warehouse_name=fw.name if fw else "", to_warehouse_name=tw.name if tw else "")


@router.get("/transfers")
def list_transfers(user: User = Depends(require_staff), db: Session = Depends(get_db),
                   status: str = "", limit: int = 100):
    query = db.query(StockTransfer)
    if status:
        query = query.filter(StockTransfer.status == status)
    rows = query.order_by(StockTransfer.id.desc()).limit(min(limit, 300)).all()
    return [_transfer_row(db, t) for t in rows]


@router.post("/transfers")
def create_transfer(body: TransferIn, user: User = Depends(require_perm("inventory.manage")),
                    db: Session = Depends(get_db)):
    """Move stock between warehouses. Two-phase: create (IN_TRANSIT) then receive.
    Source available stock must cover the transfer - stock never goes negative."""
    if body.qty <= 0:
        raise HTTPException(400, "Quantity must be positive")
    if body.from_warehouse_id == body.to_warehouse_id:
        raise HTTPException(400, "Source and destination warehouse must differ")
    src = db.get(Warehouse, body.from_warehouse_id)
    dst = db.get(Warehouse, body.to_warehouse_id)
    if not src or not dst:
        raise HTTPException(404, "Warehouse not found")
    if not src.is_active or not dst.is_active:
        raise HTTPException(400, "Both warehouses must be active")
    p = db.get(Product, body.product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    sb = get_or_create_balance(db, body.product_id, body.variant_id, body.from_warehouse_id)
    available = sb.qty_physical - sb.qty_reserved
    if available < body.qty:
        raise HTTPException(400, f"Insufficient stock at {src.name}: {available} available, {body.qty} requested")
    sb.qty_physical -= body.qty
    sb.qty_in_transit = (sb.qty_in_transit or 0) + body.qty
    t = StockTransfer(reference="PENDING", product_id=body.product_id, variant_id=body.variant_id or 0,
                      from_warehouse_id=body.from_warehouse_id, to_warehouse_id=body.to_warehouse_id,
                      qty=body.qty, reason=body.reason, status="IN_TRANSIT", created_by_user_id=user.id)
    db.add(t)
    db.flush()
    t.reference = next_ref(db, StockTransfer, "reference", "TRF")
    _movement(db, body.product_id, body.variant_id, body.from_warehouse_id, "TRANSFER_OUT", -body.qty,
              body.reason or f"Transfer to {dst.name}", "stock_transfer", t.id, user)
    db.commit()
    audit(db, user, "create", "stock_transfer", t.id,
          f"Transfer {t.reference}: {body.qty} x {p.name} {src.code} -> {dst.code}")
    db.commit()
    return _transfer_row(db, t)


@router.post("/transfers/{transfer_id}/receive")
def receive_transfer(transfer_id: int, user: User = Depends(require_perm("inventory.manage")),
                     db: Session = Depends(get_db)):
    t = db.get(StockTransfer, transfer_id)
    if not t:
        raise HTTPException(404, "Transfer not found")
    if t.status != "IN_TRANSIT":
        raise HTTPException(400, f"Transfer already {t.status}")
    dbb = get_or_create_balance(db, t.product_id, t.variant_id, t.to_warehouse_id)
    dbb.qty_physical += t.qty
    sb = get_or_create_balance(db, t.product_id, t.variant_id, t.from_warehouse_id)
    sb.qty_in_transit = max(0, (sb.qty_in_transit or 0) - t.qty)
    dst = db.get(Warehouse, t.to_warehouse_id)
    _movement(db, t.product_id, t.variant_id, t.to_warehouse_id, "TRANSFER_IN", t.qty,
              t.reason or f"Received from transfer {t.reference}", "stock_transfer", t.id, user)
    t.status = "RECEIVED"
    t.received_at = utcnow()
    db.commit()
    audit(db, user, "receive", "stock_transfer", t.id, f"Transfer {t.reference} received at {dst.name if dst else t.to_warehouse_id}")
    db.commit()
    from app.modules.notify import run_automation_checks
    run_automation_checks(db)
    return _transfer_row(db, t)


@router.post("/transfers/{transfer_id}/cancel")
def cancel_transfer(transfer_id: int, user: User = Depends(require_perm("inventory.manage")),
                    db: Session = Depends(get_db)):
    t = db.get(StockTransfer, transfer_id)
    if not t:
        raise HTTPException(404, "Transfer not found")
    if t.status != "IN_TRANSIT":
        raise HTTPException(400, f"Transfer already {t.status}")
    sb = get_or_create_balance(db, t.product_id, t.variant_id, t.from_warehouse_id)
    sb.qty_physical += t.qty
    sb.qty_in_transit = max(0, (sb.qty_in_transit or 0) - t.qty)
    _movement(db, t.product_id, t.variant_id, t.from_warehouse_id, "TRANSFER_IN", t.qty,
              f"Transfer {t.reference} cancelled - stock returned", "stock_transfer", t.id, user)
    t.status = "CANCELLED"
    db.commit()
    audit(db, user, "cancel", "stock_transfer", t.id, f"Transfer {t.reference} cancelled, stock returned to source")
    db.commit()
    return _transfer_row(db, t)
