"""Vendor self-service portal API. Every query is hard-scoped to the caller's vendor
(vendor-level data isolation is a PRD security requirement)."""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.deps import get_vendor_user
from app.core.serialize import serialize, serialize_list
from app.modules.identity_models import User
from app.modules.vendors_models import Vendor, VendorContact
from app.modules.catalog_models import Product
from app.modules.inventory_models import InventoryBalance
from app.modules.orders_models import Order, OrderItem, Customer
from app.modules.cod_models import CODCollection
from app.modules.charges_models import Charge
from app.modules.settlements_models import Settlement

router = APIRouter(prefix="/api/portal", tags=["vendor portal"])


@router.get("/summary")
def summary(user: User = Depends(get_vendor_user), db: Session = Depends(get_db)):
    vid = user.vendor_id
    v = db.get(Vendor, vid)
    order_ids = [r[0] for r in db.query(Order.id).filter(Order.vendor_id == vid).all()]
    verified = (db.query(func.coalesce(func.sum(CODCollection.collected_kobo), 0))
                .filter(CODCollection.order_id.in_(order_ids or [0]), CODCollection.verified_at.isnot(None)).scalar() or 0)
    charges = (db.query(func.coalesce(func.sum(Charge.amount_kobo), 0))
               .filter(Charge.vendor_id == vid, Charge.status == "APPLIED").scalar() or 0)
    # Outstanding payable straight from the double-entry ledger (vendor-scoped journal lines)
    from app.modules.ledger_models import JournalLine, JournalEntry
    from sqlalchemy import and_
    ledger_payable = (db.query(func.coalesce(func.sum(JournalLine.credit_kobo - JournalLine.debit_kobo), 0))
                      .select_from(JournalLine).join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
                      .filter(JournalLine.vendor_id == vid, JournalEntry.status.in_(("POSTED", "REVERSED")),
                              JournalEntry.source_type.in_(["COD_COLLECTION", "CHARGE_RECOGNITION", "SETTLEMENT_PAYOUT"]))
                      .scalar() or 0)
    settled = (db.query(func.coalesce(func.sum(Settlement.net_kobo), 0))
               .filter(Settlement.vendor_id == vid, Settlement.status.in_(["PAID", "PARTIALLY_PAID"])).scalar() or 0)
    stock_value = (db.query(func.coalesce(
                       func.sum((InventoryBalance.qty_physical - InventoryBalance.qty_reserved) * Product.default_sell_price_kobo), 0))
                   .select_from(InventoryBalance).join(Product, Product.id == InventoryBalance.product_id)
                   .filter(Product.vendor_id == vid).scalar() or 0)
    return serialize(v, orders_total=db.query(func.count(Order.id)).filter(Order.vendor_id == vid).scalar() or 0,
                     orders_active=db.query(func.count(Order.id)).filter(
                         Order.vendor_id == vid,
                         Order.status.notin_(["DELIVERED", "CANCELLED", "RETURNED_TO_WAREHOUSE"])).scalar() or 0,
                     verified_collections_kobo=verified, charges_kobo=charges,
                     settled_kobo=settled, ledger_payable_kobo=max(0, ledger_payable),
                     outstanding_payable_kobo=max(0, ledger_payable),
                     inventory_value_kobo=stock_value)


@router.get("/orders")
def portal_orders(user: User = Depends(get_vendor_user), db: Session = Depends(get_db), status: str = "", q: str = ""):
    query = (db.query(Order, Customer)
             .join(Customer, Customer.id == Order.customer_id)
             .filter(Order.vendor_id == user.vendor_id))
    if status:
        query = query.filter(Order.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter((Order.reference.ilike(like)) | (Customer.name.ilike(like)) | (Customer.phone.ilike(like)))
    rows = query.order_by(Order.id.desc()).limit(100).all()
    return [serialize(o, customer_name=c.name, customer_phone=c.phone) for o, c in rows]


@router.get("/orders/{order_id}")
def portal_order(order_id: int, user: User = Depends(get_vendor_user), db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o or o.vendor_id != user.vendor_id:
        # isolation: a vendor can never read another vendor's order
        from fastapi import HTTPException
        raise HTTPException(404, "Order not found")
    items = db.query(OrderItem).filter(OrderItem.order_id == o.id).all()
    c = db.get(Customer, o.customer_id)
    return serialize(o, customer_name=c.name if c else None, items=serialize_list(items))


@router.get("/inventory")
def portal_inventory(user: User = Depends(get_vendor_user), db: Session = Depends(get_db)):
    rows = (db.query(InventoryBalance, Product)
            .join(Product, Product.id == InventoryBalance.product_id)
            .filter(Product.vendor_id == user.vendor_id).all())
    agg = {}
    for b, p in rows:
        a = agg.setdefault(p.id, {"product": p, "physical": 0, "reserved": 0})
        a["physical"] += b.qty_physical
        a["reserved"] += b.qty_reserved
    return [serialize(a["product"], qty_physical=a["physical"], qty_reserved=a["reserved"],
                      qty_available=a["physical"] - a["reserved"],
                      low_stock=(a["physical"] - a["reserved"]) <= a["product"].reorder_level)
            for a in agg.values()]


@router.get("/statement")
def portal_statement(user: User = Depends(get_vendor_user), db: Session = Depends(get_db)):
    vid = user.vendor_id
    order_ids = [r[0] for r in db.query(Order.id).filter(Order.vendor_id == vid).all()]
    lines = []
    for c in db.query(CODCollection).filter(CODCollection.order_id.in_(order_ids or [0])).all():
        lines.append({"date": c.created_at, "type": "COD_COLLECTION",
                      "label": f"COD collection (order #{c.order_id})", "credit_kobo": c.collected_kobo,
                      "status": c.status})
    for ch in db.query(Charge).filter(Charge.vendor_id == vid).all():
        lines.append({"date": ch.created_at, "type": "CHARGE",
                      "label": f"{ch.charge_type}", "debit_kobo": ch.amount_kobo, "status": ch.status})
    for s in db.query(Settlement).filter(Settlement.vendor_id == vid).all():
        lines.append({"date": s.created_at, "type": "SETTLEMENT",
                      "label": f"Settlement {s.reference}", "debit_kobo": s.net_kobo, "status": s.status})
    lines.sort(key=lambda l: l["date"] or "")
    return {"lines": lines}
