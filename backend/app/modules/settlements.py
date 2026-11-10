from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.db import get_db, utcnow
from app.core.deps import require_perm, require_any_perm
from app.core.serialize import serialize, serialize_list
from app.core.audit import audit
from app.core.ids import next_ref
from app.modules.identity_models import User
from app.modules.vendors_models import Vendor
from app.modules.settlements_models import Settlement, SettlementItem, Payment
from app.modules.cod_models import CODCollection
from app.modules.orders_models import Order
from app.modules.charges_models import Charge
from app.modules.notify import notify

router = APIRouter(prefix="/api/settlements", tags=["settlements"])
require_settlement_view = require_any_perm("settlements.manage", "settlements.approve",
                                           "finance.manage", "reports.view")
PAY_METHODS = ("BANK_TRANSFER", "CASH", "DIGITAL", "CHEQUE", "POS", "OTHER")


class BuildIn(BaseModel):
    vendor_id: int


class PayIn(BaseModel):
    amount_kobo: int
    bank_ref: str = ""
    method: str = "BANK_TRANSFER"
    note: str = ""


@router.get("")
def list_settlements(user: User = Depends(require_settlement_view), db: Session = Depends(get_db), status: str = "", vendor_id: int = 0):
    query = (db.query(Settlement, Vendor).join(Vendor, Vendor.id == Settlement.vendor_id))
    if status:
        query = query.filter(Settlement.status == status)
    if vendor_id:
        query = query.filter(Settlement.vendor_id == vendor_id)
    rows = query.order_by(Settlement.id.desc()).limit(100).all()
    return [serialize(s, vendor_name=v.name) for s, v in rows]


def _gather(db: Session, vendor):
    """Collections and charges that are ready to be settled for a vendor."""
    order_ids = [r[0] for r in db.query(Order.id).filter(Order.vendor_id == vendor.id).all()]
    settled_collection_ids = {i.collection_id for i in db.query(SettlementItem)
                              .filter(SettlementItem.collection_id.isnot(None)).all()}
    settled_charge_ids = {i.charge_id for i in db.query(SettlementItem)
                          .filter(SettlementItem.charge_id.isnot(None)).all()}

    collections = (db.query(CODCollection)
                   .filter(CODCollection.order_id.in_(order_ids or [0]),
                           CODCollection.status.in_(("VERIFIED", "DISCREPANCY")),
                           CODCollection.verified_at.isnot(None))
                   .order_by(CODCollection.id).all())
    collections = [c for c in collections if c.id not in settled_collection_ids]
    # Charges settle against the orders whose collections are being settled
    # (plus unattached vendor charges), so undelivered orders' charges stay out.
    collection_order_ids = {c.order_id for c in collections}
    charges = (db.query(Charge)
               .filter(Charge.vendor_id == vendor.id, Charge.status == "APPLIED")
               .order_by(Charge.id).all())
    charges = [ch for ch in charges if ch.id not in settled_charge_ids
               and (ch.order_id is None or ch.order_id in collection_order_ids)]

    return collections, charges


@router.get("/preview")
def preview(vendor_id: int, user: User = Depends(require_settlement_view), db: Session = Depends(get_db)):
    """What a settlement built right now for this vendor would contain."""
    vendor = db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(404, "Vendor not found")
    collections, charges = _gather(db, vendor)
    gross = sum(c.collected_kobo for c in collections)
    charges_total = sum(ch.amount_kobo for ch in charges)
    refs = [r[0] for r in db.query(Order.reference).filter(Order.id.in_([c.order_id for c in collections] or [0])).all()]
    return {"orders": refs, "collections": len(collections), "gross_kobo": gross, "charges_kobo": charges_total,
            "net_kobo": gross - charges_total, "can_build": bool(collections) and gross - charges_total > 0}


@router.post("/build")
def build_settlement(body: BuildIn, user: User = Depends(require_perm("settlements.manage")), db: Session = Depends(get_db)):
    """Compute a settlement batch: verified collections - authorized charges (PRD formula).
    Reproducible: traceable to underlying orders and collections via settlement items."""
    vendor = db.get(Vendor, body.vendor_id)
    if not vendor:
        raise HTTPException(404, "Vendor not found")
    collections, charges = _gather(db, vendor)
    gross = sum(c.collected_kobo for c in collections)
    charges_total = sum(ch.amount_kobo for ch in charges)
    net = gross - charges_total
    if not collections and not charges:
        raise HTTPException(400, "No verified collections available to settle for this vendor")
    if net <= 0:
        raise HTTPException(400, "Nothing payable: charges meet or exceed verified collections. "
                                 "Leave them to carry forward to the next settlement.")

    s = Settlement(reference="PENDING", vendor_id=vendor.id,
                   gross_kobo=gross, charges_kobo=charges_total,
                   deductions_kobo=0, adjustments_kobo=0, net_kobo=net,
                   status="READY_FOR_APPROVAL", created_by_user_id=user.id)
    db.add(s)
    db.flush()
    s.reference = next_ref(db, Settlement, "reference", "STL")
    for c in collections:
        o = db.get(Order, c.order_id)
        db.add(SettlementItem(settlement_id=s.id, order_id=c.order_id, collection_id=c.id,
                              type="COLLECTION", gross_kobo=c.collected_kobo,
                              deduction_kobo=0, net_kobo=c.collected_kobo))
        _ = o
    for ch in charges:
        db.add(SettlementItem(settlement_id=s.id, order_id=ch.order_id, charge_id=ch.id,
                              type="CHARGE", gross_kobo=0, deduction_kobo=ch.amount_kobo,
                              net_kobo=-ch.amount_kobo))
    db.commit()
    notify(db, event_type="SETTLEMENT_READY", title=f"Settlement {s.reference} ready for approval",
           vendor_id=vendor.id, entity_type="settlement", entity_id=s.id)
    audit(db, user, "build", "settlement", s.id,
          f"Settlement {s.reference} built: gross {gross}, charges {charges_total}, net {net}")
    db.commit()
    return serialize(s)


CHARGEABLE = ("READY_FOR_APPROVAL", "APPROVED", "PARTIALLY_PAID")


class AddChargeIn(BaseModel):
    order_id: int | None = None   # charge a specific order in this settlement (optional)
    charge_type: str = "OTHER"
    amount_kobo: int
    reason: str


@router.post("/{settlement_id}/charges")
def add_settlement_charge(settlement_id: int, body: AddChargeIn, user: User = Depends(require_perm("settlements.manage")), db: Session = Depends(get_db)):
    """Add one of our own charges to a settlement before it is approved (e.g. storage, special handling)."""
    from app.modules.charges import apply_charge, CHARGE_TYPES
    s = db.get(Settlement, settlement_id)
    if not s:
        raise HTTPException(404, "Settlement not found")
    if s.status not in CHARGEABLE:
        raise HTTPException(400, "Charges can only be added until the settlement is fully paid")
    if body.charge_type not in CHARGE_TYPES:
        raise HTTPException(400, "Unknown charge type")
    if body.amount_kobo <= 0:
        raise HTTPException(400, "Enter the charge amount")
    if not body.reason.strip():
        raise HTTPException(400, "Every charge needs a recorded reason")
    if s.net_kobo - body.amount_kobo < max(0, s.paid_kobo):
        raise HTTPException(400, "This charge is more than what is still unpaid on this settlement")
    from app.modules.ledger import get_account_by_subtype, post_journal
    if body.order_id and not db.query(SettlementItem).filter(SettlementItem.settlement_id == s.id,
                                                               SettlementItem.order_id == body.order_id).first():
        raise HTTPException(400, "That order is not part of this settlement")
    ch = apply_charge(db, vendor_id=s.vendor_id, order_id=body.order_id or None, charge_type=body.charge_type,
                      amount_kobo=body.amount_kobo, reason=body.reason.strip(), actor=user, commit=False)
    db.add(SettlementItem(settlement_id=s.id, order_id=ch.order_id, charge_id=ch.id, type="CHARGE",
                          gross_kobo=0, deduction_kobo=ch.amount_kobo, net_kobo=-ch.amount_kobo))
    s.charges_kobo += ch.amount_kobo
    s.net_kobo -= ch.amount_kobo
    try:
        post_journal(db, memo=f"Charge on settlement {s.reference}: {body.reason.strip()}",
                     source_type="CHARGE_RECOGNITION", source_id=ch.id,
                     lines=[{"account_id": get_account_by_subtype(db, "VENDOR_PAYABLE").id, "debit_kobo": ch.amount_kobo, "vendor_id": s.vendor_id},
                            {"account_id": get_account_by_subtype(db, "LOGISTICS_REVENUE").id, "credit_kobo": ch.amount_kobo}],
                     posted_by=user)
    except ValueError as ex:
        db.rollback()
        raise HTTPException(400, str(ex))
    audit(db, user, "add_charge", "settlement", s.id, f"{body.charge_type} {ch.amount_kobo} added to {s.reference}")
    db.commit()
    return serialize(s)


@router.get("/{settlement_id}")
def get_settlement(settlement_id: int, user: User = Depends(require_settlement_view), db: Session = Depends(get_db)):
    s = db.get(Settlement, settlement_id)
    if not s:
        raise HTTPException(404, "Settlement not found")
    v = db.get(Vendor, s.vendor_id)
    items = (db.query(SettlementItem).filter(SettlementItem.settlement_id == s.id)
             .order_by(SettlementItem.type, SettlementItem.id).all())
    payments = db.query(Payment).filter(Payment.settlement_id == s.id).all()
    out_items = []
    for i in items:
        o = db.get(Order, i.order_id) if i.order_id else None
        note = ""
        if o and i.type == "COLLECTION":
            from app.modules.vendors import _narrate
            from app.modules.orders_models import OrderItem, Customer
            cu = db.get(Customer, o.customer_id)
            note = f"{cu.name if cu else ''} · {_narrate(db.query(OrderItem).filter(OrderItem.order_id == o.id).order_by(OrderItem.id).all(), o)}"
        out_items.append(serialize(i, order_reference=o.reference if o else None, note=note))
    return serialize(s, vendor_name=v.name if v else None, items=out_items, payments=serialize_list(payments))


@router.post("/{settlement_id}/approve")
def approve(settlement_id: int, user: User = Depends(require_perm("settlements.approve")), db: Session = Depends(get_db)):
    """Separate approval step - approval and payment recording are separately auditable."""
    s = db.get(Settlement, settlement_id)
    if not s:
        raise HTTPException(404, "Settlement not found")
    if s.status != "READY_FOR_APPROVAL":
        raise HTTPException(400, f"Cannot approve a settlement in status {s.status}")
    if s.created_by_user_id == user.id and not user.is_superuser:
        raise HTTPException(403, "Segregation of duties: someone other than the builder must approve")
    s.status = "APPROVED"
    s.approved_by_user_id = user.id
    s.approved_at = utcnow()
    db.commit()
    audit(db, user, "approve", "settlement", s.id, f"Settlement {s.reference} approved")
    db.commit()
    return serialize(s)


@router.post("/{settlement_id}/pay")
def record_payment(settlement_id: int, body: PayIn, user: User = Depends(require_perm("settlements.manage")), db: Session = Depends(get_db)):
    s = db.get(Settlement, settlement_id)
    if not s:
        raise HTTPException(404, "Settlement not found")
    if s.status not in ("APPROVED", "PARTIALLY_PAID"):
        raise HTTPException(400, f"Settlement must be APPROVED before payment (currently {s.status})")
    if body.amount_kobo <= 0:
        raise HTTPException(400, "Payment amount must be positive")
    if body.method not in PAY_METHODS:
        raise HTTPException(400, f"Unknown payment method. Valid: {', '.join(PAY_METHODS)}")
    if s.paid_kobo + body.amount_kobo > s.net_kobo:
        raise HTTPException(400, "Payment exceeds the settlement net amount")

    p = Payment(settlement_id=s.id, vendor_id=s.vendor_id, direction="VENDOR_PAYOUT",
                amount_kobo=body.amount_kobo, method=body.method, bank_ref=body.bank_ref,
                paid_at=utcnow(), recorded_by_user_id=user.id, note=body.note)
    db.add(p)
    s.paid_kobo += body.amount_kobo
    s.status = "PAID" if s.paid_kobo >= s.net_kobo else "PARTIALLY_PAID"

    # Ledger: vendor payable settles out through the bank
    from app.modules.ledger import get_account_by_subtype, post_journal
    payables = get_account_by_subtype(db, "VENDOR_PAYABLE")
    bank = get_account_by_subtype(db, "BANK")
    post_journal(db, memo=f"Vendor settlement payout {s.reference}",
                 source_type="SETTLEMENT_PAYOUT", source_id=s.id,
                 lines=[{"account_id": payables.id, "debit_kobo": body.amount_kobo, "vendor_id": s.vendor_id},
                        {"account_id": bank.id, "credit_kobo": body.amount_kobo}],
                 posted_by=user)
    db.commit()
    notify(db, event_type="SETTLEMENT_PAID", title=f"Settlement {s.reference} payment recorded",
           vendor_id=s.vendor_id, entity_type="settlement", entity_id=s.id)
    audit(db, user, "pay", "settlement", s.id, f"Payment {body.amount_kobo} recorded for {s.reference} ({s.status})")
    db.commit()
    return serialize(s)
