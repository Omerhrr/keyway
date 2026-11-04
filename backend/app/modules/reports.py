"""Dashboard widgets and report aggregates."""
from datetime import timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.db import get_db, utcnow
from app.core.deps import require_staff, get_current_user
from app.modules.identity_models import User
from app.modules.orders_models import Order, OrderItem, OrderDraft, CustomerConfirmation
from app.modules.cod_models import CODCollection
from app.modules.settlements_models import Settlement
from app.modules.catalog_models import Product
from app.modules.inventory_models import InventoryBalance
from app.modules.charges_models import Charge
from app.modules.conversations_models import Conversation, Message
from app.modules.delivery_models import Delivery, Rider

router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/dashboard")
def dashboard(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    def count(model, *filters):
        return db.query(func.count(model.id)).filter(*filters).scalar() or 0

    orders_today = count(Order, Order.created_at >= today)
    awaiting_processing = count(Order, Order.status.in_(["CONFIRMED", "PROCESSING", "CUSTOMER_CONFIRMED"]))
    awaiting_customer = count(Order, Order.status == "PENDING_CUSTOMER_CONFIRMATION")
    ready_dispatch = count(Order, Order.status == "READY_FOR_DISPATCH")
    in_transit = count(Order, Order.status.in_(["DISPATCHED", "IN_TRANSIT", "OUT_FOR_DELIVERY"]))
    delivered_today = count(Order, Order.status == "DELIVERED", Order.delivered_at >= today)
    failed = count(Order, Order.status == "DELIVERY_FAILED")
    pending_cod = (db.query(func.count(CODCollection.id))
                   .filter(CODCollection.status.in_(["PENDING_VERIFICATION", "DISCREPANCY"])).scalar() or 0)
    cash_today = (db.query(func.coalesce(func.sum(CODCollection.collected_kobo), 0))
                  .filter(CODCollection.collected_at >= today).scalar() or 0)
    settlements_pending = count(Settlement, Settlement.status.in_(["READY_FOR_APPROVAL", "APPROVED", "PENDING_RECONCILIATION"]))
    drafts_pending = count(OrderDraft, OrderDraft.status.in_(["PENDING_REVIEW", "AWAITING_VENDOR"]))
    unassigned_senders = count(Conversation, Conversation.vendor_id.is_(None),
                               Conversation.status.in_(["NEW", "OPEN", "WAITING_FOR_STAFF"]))
    confirmation_queue = (db.query(func.count(Order.id))
                          .filter(Order.status.in_(["CONFIRMED", "PENDING_CUSTOMER_CONFIRMATION"])).scalar() or 0)

    # Inventory value at sell price + low stock alerts (vendor-owned stock)
    value = 0
    low_stock = 0
    balances = (db.query(InventoryBalance, Product)
                .join(Product, Product.id == InventoryBalance.product_id).all())
    for b, p in balances:
        available = b.qty_physical - b.qty_reserved
        value += available * (p.default_sell_price_kobo or 0)
        if available <= p.reorder_level:
            low_stock += 1
    vendor_payables = 0
    # Vendor payables straight from the ledger: VENDOR_PAYABLE account balance (credit-positive)
    from app.modules.ledger_models import JournalLine as JL, JournalEntry as JE, Account as Acc
    pay_acc = db.query(Acc).filter(Acc.subtype == "VENDOR_PAYABLE").first()
    if pay_acc:
        credits = (db.query(func.coalesce(func.sum(JL.credit_kobo), 0))
                   .select_from(JL).join(JE, JE.id == JL.entry_id)
                   .filter(JL.account_id == pay_acc.id, JE.status == "POSTED").scalar() or 0)
        debits = (db.query(func.coalesce(func.sum(JL.debit_kobo), 0))
                  .select_from(JL).join(JE, JE.id == JL.entry_id)
                  .filter(JL.account_id == pay_acc.id, JE.status == "POSTED").scalar() or 0)
        vendor_payables = max(0, credits - debits)
    verified = (db.query(func.coalesce(func.sum(CODCollection.collected_kobo), 0))
                .filter(CODCollection.status == "VERIFIED").scalar() or 0)
    from app.modules.settlements_models import Settlement as S
    charges_total = (db.query(func.coalesce(func.sum(Charge.amount_kobo), 0))
                     .filter(Charge.status == "APPLIED").scalar() or 0)
    settled_total = (db.query(func.coalesce(func.sum(S.net_kobo), 0))
                     .filter(S.status.in_(["PAID", "PARTIALLY_PAID"])).scalar() or 0)
    # Revenue recognized = LOGISTICS_REVENUE account balance (from the immutable ledger)
    revenue = 0
    rev_acc = db.query(Acc).filter(Acc.subtype == "LOGISTICS_REVENUE").first()
    if rev_acc:
        revenue = (db.query(func.coalesce(func.sum(JL.credit_kobo - JL.debit_kobo), 0))
                   .select_from(JL).join(JE, JE.id == JL.entry_id)
                   .filter(JL.account_id == rev_acc.id, JE.status == "POSTED").scalar() or 0)

    orders_by_status = dict(db.query(Order.status, func.count(Order.id)).group_by(Order.status).all())
    return {
        "orders_today": orders_today,
        "awaiting_processing": awaiting_processing,
        "awaiting_customer_confirmation": awaiting_customer,
        "ready_for_dispatch": ready_dispatch,
        "in_transit": in_transit,
        "delivered_today": delivered_today,
        "failed_deliveries": failed,
        "pending_cod_collections": pending_cod,
        "cash_collected_today_kobo": cash_today,
        "settlements_pending": settlements_pending,
        "drafts_pending_review": drafts_pending,
        "unassigned_senders": unassigned_senders,
        "confirmation_queue": confirmation_queue,
        "inventory_value_kobo": value,
        "low_stock_alerts": low_stock,
        "vendor_payables_kobo": vendor_payables,
        "logistics_revenue_kobo": revenue,
        "orders_by_status": orders_by_status,
    }


@router.get("/reports/orders-by-status")
def orders_by_status(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return [{"status": s, "count": c} for s, c in
            db.query(Order.status, func.count(Order.id)).group_by(Order.status).all()]


@router.get("/reports/revenue-14d")
def revenue_14d(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=13)
    rows = (db.query(CODCollection.collected_at, CODCollection.collected_kobo)
            .filter(CODCollection.collected_at >= start, CODCollection.status != "UNVERIFIED").all())
    days = {}
    for i in range(14):
        d = (start + timedelta(days=i)).strftime("%m-%d")
        days[d] = 0
    for at, amt in rows:
        if at:
            key = at.strftime("%m-%d")
            if key in days:
                days[key] += amt / 100
    return [{"day": k, "amount": v} for k, v in days.items()]


@router.get("/reports/delivery-performance")
def delivery_performance(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    total = db.query(func.count(Delivery.id)).scalar() or 0
    delivered = db.query(func.count(Delivery.id)).filter(Delivery.status == "DELIVERED").scalar() or 0
    failed = db.query(func.count(Delivery.id)).filter(Delivery.status == "FAILED").scalar() or 0
    riders = (db.query(Rider.full_name,
                       func.count(Delivery.id),
                       func.sum(func.case((Delivery.status == "DELIVERED", 1), else_=0)))
              .outerjoin(Delivery, Delivery.rider_id == Rider.id)
              .group_by(Rider.id).all())
    return {"total": total, "delivered": delivered, "failed": failed,
            "success_rate": round(delivered / total * 100, 1) if total else 0,
            "riders": [{"name": n, "total": t or 0, "delivered": d or 0} for n, t, d in riders]}


@router.get("/reports/whatsapp-stats")
def whatsapp_stats(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    total_in = db.query(func.count(Message.id)).filter(Message.direction == "IN").scalar() or 0
    by_intent = dict(db.query(Message.intent, func.count(Message.id))
                     .filter(Message.direction == "IN").group_by(Message.intent).all())
    drafts = db.query(func.count(OrderDraft.id)).scalar() or 0
    converted = db.query(func.count(OrderDraft.id)).filter(OrderDraft.status == "CONVERTED").scalar() or 0
    unknown = db.query(func.count(Conversation.id)).filter(Conversation.vendor_id.is_(None)).scalar() or 0
    return {"inbound_messages": total_in, "intents": by_intent, "drafts_created": drafts,
            "drafts_converted": converted, "conversion_rate": round(converted / drafts * 100, 1) if drafts else 0,
            "unassigned_senders": unknown}
