"""Dashboard widgets and report aggregates."""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, case
from sqlalchemy.orm import Session
from app.core.db import get_db, utcnow
from app.core.deps import require_staff, get_current_user
from app.modules.identity_models import User
from app.modules.orders_models import (Order, OrderItem, OrderDraft, CustomerConfirmation,
                                        Customer)
from app.modules.cod_models import CODCollection
from app.modules.settlements_models import Settlement
from app.modules.catalog_models import Product
from app.modules.inventory_models import InventoryBalance
from app.modules.charges_models import Charge
from app.modules.conversations_models import Conversation, Message
from app.modules.delivery_models import Delivery, Rider
from app.modules.ledger_models import Expense

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
                       func.sum(case((Delivery.status == "DELIVERED", 1), else_=0)))
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


# ---------------------------------------------------------------------------
# Phase 6B: advanced analytics (vendor / staff / operational / financial)
# ---------------------------------------------------------------------------

def _ledger_balance(db, *, subtype: str | None = None, vendor_id: int | None = None,
                    start=None, end=None) -> int:
    """Credit-minus-debit balance of POSTED lines for an account subtype (or
    per-vendor vendor-payable lines), optionally date-bounded."""
    from app.modules.ledger_models import JournalLine as JL, JournalEntry as JE, Account as Acc
    q = (db.query(func.coalesce(func.sum(JL.credit_kobo - JL.debit_kobo), 0))
         .select_from(JL).join(JE, JE.id == JL.entry_id)
         .filter(JE.status == "POSTED"))
    if subtype:
        q = q.filter(JL.account_id == Acc.id, Acc.subtype == subtype)
    if vendor_id is not None:
        q = q.filter(JL.vendor_id == vendor_id)
    if start is not None:
        q = q.filter(JE.entry_date >= start)
    if end is not None:
        q = q.filter(JE.entry_date < end)
    return q.scalar() or 0


@router.get("/reports/vendor-performance")
def vendor_performance(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Per-vendor operating scorecard: volume, delivery quality, money flows."""
    from app.modules.vendors_models import Vendor
    vendors = db.query(Vendor).order_by(Vendor.name).all()
    out = []
    for v in vendors:
        total = db.query(func.count(Order.id)).filter(Order.vendor_id == v.id).scalar() or 0
        delivered = db.query(func.count(Order.id)).filter(
            Order.vendor_id == v.id, Order.status == "DELIVERED").scalar() or 0
        failed = db.query(func.count(Order.id)).filter(
            Order.vendor_id == v.id, Order.status.in_(["DELIVERY_FAILED", "RETURNED"])).scalar() or 0
        cod = (db.query(func.coalesce(func.sum(CODCollection.collected_kobo), 0))
               .join(Order, Order.id == CODCollection.order_id)
               .filter(Order.vendor_id == v.id, CODCollection.status == "VERIFIED").scalar() or 0)
        charges = (db.query(func.coalesce(func.sum(Charge.amount_kobo), 0))
                   .filter(Charge.vendor_id == v.id, Charge.status == "APPLIED").scalar() or 0)
        net = cod - charges
        outstanding = _ledger_balance(db, vendor_id=v.id)
        # average cycle time (hours) created -> delivered
        cycle = (db.query(func.avg(func.julianday(Order.delivered_at) - func.julianday(Order.created_at)))
                 .filter(Order.vendor_id == v.id, Order.status == "DELIVERED",
                         Order.delivered_at.isnot(None)).scalar())
        out.append({
            "vendor_id": v.id, "vendor": v.name, "code": v.code, "status": v.status,
            "orders": total, "delivered": delivered, "failed_or_returned": failed,
            "delivery_rate": round(delivered / total * 100, 1) if total else 0,
            "cod_verified_kobo": cod, "charges_kobo": charges, "net_kobo": net,
            "outstanding_payable_kobo": outstanding,
            "avg_cycle_hours": round(cycle, 1) if cycle else None,
        })
    return out


@router.get("/reports/staff-performance")
def staff_performance(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Per-staff activity from real attribution fields on orders/COD/settlements."""
    from app.modules.identity_models import User as U
    from app.modules.ledger_models import JournalEntry as JE
    from app.modules.settlements_models import Settlement as S
    users = db.query(U).filter(U.is_active.is_(True)).all() if hasattr(U, "is_active") else db.query(U).all()
    from app.modules.identity_models import Role
    role_names = {r.id: r.name for r in db.query(Role).all()}
    out = []
    for u in users:
        orders_created = db.query(func.count(Order.id)).filter(
            Order.created_by_user_id == u.id).scalar() or 0
        cod_verified_n = db.query(func.count(CODCollection.id)).filter(
            CODCollection.verified_by_user_id == u.id).scalar() or 0
        cod_verified_amt = (db.query(func.coalesce(func.sum(CODCollection.collected_kobo), 0))
                            .filter(CODCollection.verified_by_user_id == u.id,
                                    CODCollection.status == "VERIFIED").scalar() or 0)
        settlements_approved = db.query(func.count(S.id)).filter(
            S.approved_by_user_id == u.id).scalar() or 0
        entries_posted = db.query(func.count(JE.id)).filter(
            JE.posted_by_user_id == u.id, JE.status == "POSTED").scalar() or 0
        if not (orders_created or cod_verified_n or settlements_approved or entries_posted):
            continue
        out.append({"user_id": u.id, "name": u.full_name or u.email,
                    "role": role_names.get(u.role_id, ""),
                    "orders_created": orders_created,
                    "cod_verifications": cod_verified_n,
                    "cod_verified_kobo": cod_verified_amt,
                    "settlements_approved": settlements_approved,
                    "journal_entries_posted": entries_posted})
    return out


@router.get("/reports/operational")
def operational(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    """14-day operational trend + flow efficiency + geography."""
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=13)
    created = dict(db.query(func.date(Order.created_at), func.count(Order.id))
                   .filter(Order.created_at >= start).group_by(func.date(Order.created_at)).all())
    delivered = dict(db.query(func.date(Order.delivered_at), func.count(Order.id))
                     .filter(Order.delivered_at >= start).group_by(func.date(Order.delivered_at)).all())
    days = []
    for i in range(14):
        d = (start + timedelta(days=i)).date()
        key = d.isoformat()
        days.append({"day": key, "created": created.get(key, 0), "delivered": delivered.get(key, 0)})
    total = db.query(func.count(Order.id)).scalar() or 0
    delivered_n = db.query(func.count(Order.id)).filter(Order.status == "DELIVERED").scalar() or 0
    failed_n = db.query(func.count(Order.id)).filter(
        Order.status.in_(["DELIVERY_FAILED", "RETURNED"])).scalar() or 0
    cycle = (db.query(func.avg(func.julianday(Order.delivered_at) - func.julianday(Order.created_at)))
             .filter(Order.status == "DELIVERED", Order.delivered_at.isnot(None)).scalar())
    from app.modules.orders_models import CustomerAddress
    cities = (db.query(CustomerAddress.city, func.count(Order.id))
              .select_from(Order)
              .join(Customer, Customer.id == Order.customer_id)
              .join(CustomerAddress, (CustomerAddress.customer_id == Customer.id)
                    & (CustomerAddress.is_default.is_(True)))
              .group_by(CustomerAddress.city).order_by(func.count(Order.id).desc())
              .limit(8).all())
    if not cities:
        cities = (db.query(CustomerAddress.city, func.count(Order.id))
                  .select_from(Order)
                  .join(Customer, Customer.id == Order.customer_id)
                  .join(CustomerAddress, CustomerAddress.customer_id == Customer.id)
                  .group_by(CustomerAddress.city).order_by(func.count(Order.id).desc())
                  .limit(8).all())
    drafts = db.query(func.count(OrderDraft.id)).scalar() or 0
    converted = db.query(func.count(OrderDraft.id)).filter(OrderDraft.status == "CONVERTED").scalar() or 0
    wa_in = db.query(func.count(Message.id)).filter(Message.direction == "IN").scalar() or 0
    return {
        "daily": days,
        "total_orders": total, "delivered": delivered_n, "failed_or_returned": failed_n,
        "delivery_rate": round(delivered_n / total * 100, 1) if total else 0,
        "avg_cycle_hours": round(cycle, 1) if cycle else None,
        "top_cities": [{"city": c or "Unknown", "orders": n} for c, n in cities],
        "drafts": drafts, "drafts_converted": converted,
        "wa_to_draft_rate": round(drafts / wa_in * 100, 1) if wa_in else 0,
    }


@router.get("/reports/financial")
def financial(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Money view: COD funnel, charges, settlements, revenue and expenses."""
    from app.modules.ledger_models import JournalEntry as JE, JournalLine as JL, Account as Acc
    from app.modules.settlements_models import Settlement as S
    cod_expected = (db.query(func.coalesce(func.sum(CODCollection.expected_kobo), 0)).scalar() or 0)
    cod_collected = (db.query(func.coalesce(func.sum(CODCollection.collected_kobo), 0)).scalar() or 0)
    cod_verified = (db.query(func.coalesce(func.sum(CODCollection.collected_kobo), 0))
                    .filter(CODCollection.status == "VERIFIED").scalar() or 0)
    cod_pending = (db.query(func.coalesce(func.sum(CODCollection.collected_kobo), 0))
                   .filter(CODCollection.status.in_(["PENDING_VERIFICATION", "DISCREPANCY", "UNVERIFIED"])).scalar() or 0)
    discrepancy = (db.query(func.coalesce(func.sum(CODCollection.discrepancy_kobo), 0)).scalar() or 0)
    charges_by_type = dict(db.query(Charge.charge_type, func.coalesce(func.sum(Charge.amount_kobo), 0))
                           .filter(Charge.status == "APPLIED").group_by(Charge.charge_type).all())
    settlements_by_status = dict(db.query(S.status, func.count(S.id)).group_by(S.status).all())
    settled_net = (db.query(func.coalesce(func.sum(S.net_kobo), 0))
                   .filter(S.status.in_(["PAID", "PARTIALLY_PAID"])).scalar() or 0)
    # 30-day revenue + expense trend from the immutable ledger
    start = (utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=29))
    rev_rows = (db.query(func.date(JE.entry_date), func.coalesce(func.sum(JL.credit_kobo - JL.debit_kobo), 0))
                .select_from(JL).join(JE, JE.id == JL.entry_id).join(Acc, Acc.id == JL.account_id)
                .filter(Acc.subtype == "LOGISTICS_REVENUE", JE.status == "POSTED", JE.entry_date >= start)
                .group_by(func.date(JE.entry_date)).all())
    exp_rows = (db.query(func.date(JE.entry_date), func.coalesce(func.sum(JL.debit_kobo - JL.credit_kobo), 0))
                .select_from(JL).join(JE, JE.id == JL.entry_id).join(Acc, Acc.id == JL.account_id)
                .filter(Acc.subtype == "OPERATING_EXPENSE", JE.status == "POSTED", JE.entry_date >= start)
                .group_by(func.date(JE.entry_date)).all())
    rev_by_day, exp_by_day = dict(rev_rows), dict(exp_rows)
    trend = []
    for i in range(30):
        d = (start + timedelta(days=i)).date().isoformat()
        trend.append({"day": d, "revenue": (rev_by_day.get(d, 0) or 0) / 100,
                      "expense": (exp_by_day.get(d, 0) or 0) / 100})
    revenue_total = _ledger_balance(db, subtype="LOGISTICS_REVENUE")
    expense_total = -_ledger_balance(db, subtype="OPERATING_EXPENSE")
    vendor_payables = _ledger_balance(db, subtype="VENDOR_PAYABLE")
    # cash balances: sum debit-credit of cash accounts
    cash = (db.query(func.coalesce(func.sum(JL.debit_kobo - JL.credit_kobo), 0))
            .select_from(JL).join(JE, JE.id == JL.entry_id).join(Acc, Acc.id == JL.account_id)
            .filter(Acc.is_cash.is_(True), JE.status == "POSTED").scalar() or 0)
    expenses_by_category = dict(db.query(Expense.category, func.coalesce(func.sum(Expense.amount_kobo), 0))
                                .filter(Expense.status.in_(["APPROVED", "PAID"]))
                                .group_by(Expense.category).all())
    return {
        "cod": {"expected_kobo": cod_expected, "collected_kobo": cod_collected,
                "verified_kobo": cod_verified, "pending_verification_kobo": cod_pending,
                "discrepancy_kobo": discrepancy,
                "leakage_rate": round(discrepancy / cod_expected * 100, 2) if cod_expected else 0},
        "charges_by_type_kobo": charges_by_type,
        "settlements_by_status": settlements_by_status,
        "settled_net_kobo": settled_net,
        "vendor_payables_kobo": vendor_payables,
        "revenue_total_kobo": revenue_total,
        "expense_total_kobo": expense_total,
        "cash_balance_kobo": cash,
        "expenses_by_category_kobo": expenses_by_category,
        "trend_30d": trend,
    }


# ---------------------------------------------------------------------------
# Phase 6D: CSV exports
# ---------------------------------------------------------------------------

def _csv_response(filename: str, header: list[str], rows: list[list]):
    import io as _io
    import csv as _csv
    from urllib.parse import quote
    from fastapi.responses import Response
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    buf.seek(0)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={quote(filename)}"})


@router.get("/reports/export/{dataset}")
def export_dataset(dataset: str, vendor_id: int = 0,
                   user: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Export operational/financial datasets as CSV.

    Datasets: orders, ledger, settlements, cod, vendors."""
    from app.modules.ledger_models import JournalEntry as JE, JournalLine as JL, Account as Acc
    from app.modules.vendors_models import Vendor
    dataset = dataset.lower()
    if dataset == "orders":
        q = db.query(Order).order_by(Order.id.desc())
        if vendor_id:
            q = q.filter(Order.vendor_id == vendor_id)
        rows = []
        for o in q.limit(5000).all():
            c = db.get(Customer, o.customer_id)
            v = db.get(Vendor, o.vendor_id) if o.vendor_id else None
            total = (db.query(func.coalesce(func.sum(OrderItem.line_total_kobo), 0))
                     .filter(OrderItem.order_id == o.id).scalar() or 0)
            rows.append([o.reference, o.created_at.strftime("%Y-%m-%d %H:%M") if o.created_at else "",
                         v.name if v else "", c.name if c else "", c.phone if c else "",
                         o.status, f"{total / 100:.2f}",
                         o.delivered_at.strftime("%Y-%m-%d %H:%M") if o.delivered_at else ""])
        return _csv_response("keyway-orders.csv",
                             ["reference", "created_at", "vendor", "customer", "customer_phone",
                              "status", "total_ngn", "delivered_at"], rows)
    if dataset == "ledger":
        q = (db.query(JL, JE, Acc).select_from(JL)
             .join(JE, JE.id == JL.entry_id).join(Acc, Acc.id == JL.account_id)
             .filter(JE.status.in_(["POSTED", "REVERSED"])).order_by(JE.id, JL.id))
        if vendor_id:
            q = q.filter(JL.vendor_id == vendor_id)
        rows = []
        for jl, je, acc in q.limit(10000).all():
            v = db.get(Vendor, jl.vendor_id) if jl.vendor_id else None
            rows.append([je.entry_no, je.entry_date.strftime("%Y-%m-%d %H:%M") if je.entry_date else "",
                         je.source_type, je.status, acc.code, acc.name,
                         f"{jl.debit_kobo / 100:.2f}", f"{jl.credit_kobo / 100:.2f}",
                         v.name if v else "", jl.memo or je.memo])
        return _csv_response("keyway-ledger.csv",
                             ["entry_no", "date", "source", "entry_status", "account_code",
                              "account", "debit_ngn", "credit_ngn", "vendor", "memo"], rows)
    if dataset == "settlements":
        from app.modules.settlements_models import Settlement as S
        q = db.query(S).order_by(S.id.desc())
        if vendor_id:
            q = q.filter(S.vendor_id == vendor_id)
        rows = []
        for s in q.limit(5000).all():
            v = db.get(Vendor, s.vendor_id)
            rows.append([s.reference, v.name if v else "",
                         s.period_start.strftime("%Y-%m-%d") if s.period_start else "",
                         s.period_end.strftime("%Y-%m-%d") if s.period_end else "",
                         f"{s.gross_kobo / 100:.2f}", f"{s.charges_kobo / 100:.2f}",
                         f"{s.deductions_kobo / 100:.2f}", f"{s.net_kobo / 100:.2f}", s.status])
        return _csv_response("keyway-settlements.csv",
                             ["reference", "vendor", "period_start", "period_end", "gross_ngn",
                              "charges_ngn", "deductions_ngn", "net_ngn", "status"], rows)
    if dataset == "cod":
        q = db.query(CODCollection).order_by(CODCollection.id.desc())
        rows = []
        for c in q.limit(5000).all():
            o = db.get(Order, c.order_id)
            rows.append([o.reference if o else c.order_id,
                         f"{c.expected_kobo / 100:.2f}", f"{c.collected_kobo / 100:.2f}",
                         c.method, c.status, f"{c.discrepancy_kobo / 100:.2f}",
                         c.collected_at.strftime("%Y-%m-%d %H:%M") if c.collected_at else "",
                         c.verified_at.strftime("%Y-%m-%d %H:%M") if c.verified_at else ""])
        return _csv_response("keyway-cod.csv",
                             ["order", "expected_ngn", "collected_ngn", "method", "status",
                              "discrepancy_ngn", "collected_at", "verified_at"], rows)
    if dataset == "vendors":
        rows = []
        for v in db.query(Vendor).order_by(Vendor.name).all():
            orders = db.query(func.count(Order.id)).filter(Order.vendor_id == v.id).scalar() or 0
            outstanding = _ledger_balance(db, vendor_id=v.id)
            rows.append([v.code, v.name, v.phone, v.city, v.state, v.status,
                         v.settlement_frequency, orders, f"{outstanding / 100:.2f}"])
        return _csv_response("keyway-vendors.csv",
                             ["code", "name", "phone", "city", "state", "status",
                              "settlement_frequency", "orders", "outstanding_payable_ngn"], rows)
    raise HTTPException(404, f"Unknown dataset '{dataset}'. Use orders|ledger|settlements|cod|vendors")
