from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.db import get_db, utcnow
from app.core.deps import require_perm, require_any_perm
from app.core.serialize import serialize
from app.core.audit import audit
from app.core.ids import next_ref
from app.modules.identity_models import User
from app.modules.orders_models import Order, Customer
from app.modules.cod_models import CODCollection, CashHandover
from app.modules.delivery_models import Rider, Delivery
from app.modules.notify import notify

router = APIRouter(prefix="/api/cod", tags=["cod"])
require_cod_view = require_any_perm("cod.manage", "finance.manage", "reports.view", "dispatch.manage")
COD_METHODS = ("CASH", "BANK_TRANSFER", "DIGITAL", "POS", "CARD", "OTHER")
COLLECTABLE_ORDER_STATUSES = ("DISPATCHED", "IN_TRANSIT", "DELIVERED")


def ensure_cod_pending(db, order, delivery_id=None, rider_id=None):
    """A delivered COD order always gets a PENDING_VERIFICATION collection record, no
    matter which endpoint marked it delivered. Delivery is never proof of cash."""
    from app.modules.charges import ensure_order_charges
    ensure_order_charges(db, order)
    if order.payment_method != "COD":
        return None
    exists = db.query(CODCollection).filter(CODCollection.order_id == order.id).first()
    if exists:
        return exists
    c = CODCollection(order_id=order.id, delivery_id=delivery_id, expected_kobo=order.cod_amount_kobo,
                      collected_kobo=0, method="CASH", status="PENDING_VERIFICATION", rider_id=rider_id)
    db.add(c)
    db.flush()
    return c


class CollectionIn(BaseModel):
    order_id: int
    collected_kobo: int
    method: str = "CASH"
    note: str = ""
    rider_id: int | None = None


class VerifyIn(BaseModel):
    note: str = ""


class HandoverIn(BaseModel):
    rider_id: int | None = None
    amount_expected_kobo: int
    note: str = ""


class HandoverConfirmIn(BaseModel):
    amount_counted_kobo: int
    note: str = ""


@router.get("/collections")
def list_collections(user: User = Depends(require_cod_view), db: Session = Depends(get_db), status: str = ""):
    query = (db.query(CODCollection, Order, Customer)
             .join(Order, Order.id == CODCollection.order_id)
             .join(Customer, Customer.id == Order.customer_id))
    if status:
        query = query.filter(CODCollection.status == status)
    rows = query.order_by(CODCollection.id.desc()).limit(200).all()
    return [serialize(c, order_reference=o.reference, customer_name=cu.name,
                      vendor_id=o.vendor_id, discrepancy_kobo=c.expected_kobo - c.collected_kobo)
            for c, o, cu in rows]


@router.post("/collections")
def record_collection(body: CollectionIn, user: User = Depends(require_perm("cod.manage")), db: Session = Depends(get_db)):
    """Record money collected for an order. Expected and actual are stored separately."""
    o = db.get(Order, body.order_id)
    if not o:
        raise HTTPException(404, "Order not found")
    if o.payment_method != "COD":
        raise HTTPException(400, "Order is not a COD order")
    if body.collected_kobo < 0:
        raise HTTPException(400, "Collected amount cannot be negative")
    if body.method not in COD_METHODS:
        raise HTTPException(400, f"Unknown method. Valid: {', '.join(COD_METHODS)}")
    if o.status not in COLLECTABLE_ORDER_STATUSES:
        raise HTTPException(400, f"Cash cannot be collected for an order in status {o.status}")
    if body.rider_id and not db.get(Rider, body.rider_id):
        raise HTTPException(400, "Unknown rider")
    existing = db.query(CODCollection).filter(CODCollection.order_id == o.id).first()
    if existing and (existing.verified_at is not None or existing.status == "VERIFIED"):
        raise HTTPException(400, "A verified collection already exists for this order")
    c = existing or CODCollection(order_id=o.id, expected_kobo=o.cod_amount_kobo)
    c.collected_kobo = body.collected_kobo
    c.method = body.method
    c.collected_by_user_id = user.id
    c.rider_id = body.rider_id
    c.collected_at = utcnow()
    c.status = "PENDING_VERIFICATION"
    c.note = body.note
    if not existing:
        db.add(c)
        db.flush()
    # A delivery confirmation is never treated as proof of cash collection (PRD rule):
    # the collection stays PENDING_VERIFICATION until finance verifies it.
    notify(db, event_type="COD_RECORDED", title=f"COD recorded for {o.reference}",
           body=f"{body.collected_kobo / 100:,.0f} NGN via {body.method} - awaiting verification",
           entity_type="cod_collection", entity_id=c.id)
    db.commit()
    audit(db, user, "create", "cod_collection", c.id, f"COD collection recorded for {o.reference}")
    db.commit()
    return serialize(c)


class UpdateIn(BaseModel):
    collected_kobo: int
    method: str | None = None
    note: str = ""


@router.patch("/collections/{collection_id}")
def update_collection(collection_id: int, body: UpdateIn, user: User = Depends(require_perm("cod.manage")), db: Session = Depends(get_db)):
    """Set the actual collected amount on a pending collection (before verification)."""
    c = db.get(CODCollection, collection_id)
    if not c:
        raise HTTPException(404, "Collection not found")
    if c.status not in ("PENDING_VERIFICATION",) or c.verified_at is not None:
        raise HTTPException(400, f"Cannot edit a {c.status} collection")
    if body.collected_kobo < 0:
        raise HTTPException(400, "Collected amount cannot be negative")
    if body.method and body.method not in COD_METHODS:
        raise HTTPException(400, f"Unknown method. Valid: {', '.join(COD_METHODS)}")
    c.collected_kobo = body.collected_kobo
    if body.method:
        c.method = body.method
    if body.note:
        c.note = body.note
    db.commit()
    return serialize(c)


@router.post("/collections/{collection_id}/verify")
def verify_collection(collection_id: int, body: VerifyIn, user: User = Depends(require_perm("cod.manage")), db: Session = Depends(get_db)):
    """Verify a collection -> vendor payable + charge recognition via double-entry journal."""
    c = db.get(CODCollection, collection_id)
    if not c:
        raise HTTPException(404, "Collection not found")
    if c.verified_at is not None or c.status == "VERIFIED":
        raise HTTPException(400, "Already verified")
    if c.status not in ("PENDING_VERIFICATION", "DISCREPANCY"):
        raise HTTPException(400, f"Cannot verify a {c.status} collection")
    o = db.get(Order, c.order_id)
    discrepancy = c.expected_kobo - c.collected_kobo
    if discrepancy != 0 and not body.note.strip():
        raise HTTPException(400, "Collection does not match expected amount - a reason is required to verify a discrepancy")
    c.status = "VERIFIED" if discrepancy == 0 else "DISCREPANCY"
    c.discrepancy_kobo = discrepancy
    c.verified_by_user_id = user.id
    c.verified_at = utcnow()
    if discrepancy != 0:
        c.note = (c.note + " | " if c.note else "") + f"Discrepancy note: {body.note}"
        notify(db, event_type="COD_DISCREPANCY", title=f"COD discrepancy on {o.reference}",
               body=f"Short {abs(discrepancy) / 100:,.0f} NGN", entity_type="cod_collection", entity_id=c.id)

    # --- Accounting (double-entry, per PRD example flow) ---
    from app.modules.ledger import get_account_by_subtype, post_journal
    cod_account = get_account_by_subtype(db, "COD_CLEARING")
    payables = get_account_by_subtype(db, "VENDOR_PAYABLE")
    revenue = get_account_by_subtype(db, "LOGISTICS_REVENUE")
    try:
        if c.collected_kobo > 0:  # nothing collected -> nothing to journal (no zero-value entries)
            post_journal(db,
                         memo=f"COD collection verified for {o.reference}",
                         source_type="COD_COLLECTION", source_id=c.id,
                         lines=[{"account_id": cod_account.id, "debit_kobo": c.collected_kobo},
                                {"account_id": payables.id, "credit_kobo": c.collected_kobo, "vendor_id": o.vendor_id}],
                         posted_by=user)
        # Charge recognition: vendor payable is reduced by operator's earned charges
        from app.modules.charges_models import Charge
        charges = db.query(Charge).filter(Charge.order_id == o.id, Charge.status == "APPLIED").all()
        total_charges = sum(ch.amount_kobo for ch in charges)
        if total_charges > 0:
            post_journal(db,
                         memo=f"Logistics charge recognition for {o.reference}",
                         source_type="CHARGE_RECOGNITION", source_id=o.id,
                         lines=[{"account_id": payables.id, "debit_kobo": total_charges, "vendor_id": o.vendor_id},
                                {"account_id": revenue.id, "credit_kobo": total_charges}],
                         posted_by=user)
    except ValueError as ex:
        db.rollback()
        raise HTTPException(400, str(ex))
    db.commit()
    audit(db, user, "verify", "cod_collection", c.id,
          f"Collection verified for {o.reference}" + (f" with discrepancy {discrepancy}" if discrepancy else ""))
    db.commit()
    return serialize(c, order_reference=o.reference)


@router.post("/collections/{collection_id}/flag")
def flag_collection(collection_id: int, body: VerifyIn, user: User = Depends(require_perm("cod.manage")), db: Session = Depends(get_db)):
    c = db.get(CODCollection, collection_id)
    if not c:
        raise HTTPException(404, "Collection not found")
    if c.verified_at is not None or c.status not in ("PENDING_VERIFICATION", "DISCREPANCY"):
        raise HTTPException(400, f"Cannot flag a {c.status} collection")
    c.status = "DISCREPANCY"
    c.discrepancy_kobo = c.expected_kobo - c.collected_kobo
    c.note = (c.note + " | " if c.note else "") + f"Flagged: {body.note}"
    db.commit()
    return serialize(c)


@router.get("/handovers")
def list_handovers(user: User = Depends(require_cod_view), db: Session = Depends(get_db)):
    rows = db.query(CashHandover).order_by(CashHandover.id.desc()).limit(100).all()
    riders = {r.id: r.full_name for r in db.query(Rider).all()}
    return [serialize(h, rider_name=riders.get(h.rider_id)) for h in rows]


@router.post("/handovers")
def create_handover(body: HandoverIn, user: User = Depends(require_perm("cod.manage")), db: Session = Depends(get_db)):
    if body.amount_expected_kobo < 0:
        raise HTTPException(400, "Expected amount cannot be negative")
    if body.rider_id and not db.get(Rider, body.rider_id):
        raise HTTPException(400, "Unknown rider")
    h = CashHandover(reference="PENDING", rider_id=body.rider_id, user_id=user.id,
                     amount_expected_kobo=body.amount_expected_kobo, note=body.note,
                     handed_at=utcnow(), status="PENDING")
    db.add(h)
    db.flush()
    h.reference = next_ref(db, CashHandover, "reference", "HDV")
    # Attach this rider's unhandled pending collections
    if body.rider_id:
        pending = (db.query(CODCollection)
                   .filter(CODCollection.rider_id == body.rider_id,
                           CODCollection.status == "PENDING_VERIFICATION",
                           CODCollection.handover_id.is_(None)).all())
        for c in pending:
            c.handover_id = h.id
    db.commit()
    return serialize(h)


@router.post("/handovers/{handover_id}/confirm")
def confirm_handover(handover_id: int, body: HandoverConfirmIn, user: User = Depends(require_perm("cod.manage")), db: Session = Depends(get_db)):
    h = db.get(CashHandover, handover_id)
    if not h:
        raise HTTPException(404, "Handover not found")
    if body.amount_counted_kobo < 0:
        raise HTTPException(400, "Counted amount cannot be negative")
    if h.status == "CONFIRMED":
        raise HTTPException(400, "Handover already confirmed")
    h.amount_counted_kobo = body.amount_counted_kobo
    diff = h.amount_expected_kobo - body.amount_counted_kobo
    h.status = "CONFIRMED" if diff == 0 else "DISCREPANCY"
    h.confirmed_at = utcnow()
    h.note = (h.note + " | " if h.note else "") + (body.note or (f"Difference {diff / 100:,.0f} NGN" if diff else ""))
    db.commit()
    return serialize(h)
