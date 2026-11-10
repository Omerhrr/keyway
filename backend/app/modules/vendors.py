from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.db import get_db, utcnow
from app.core.deps import require_staff, require_perm, get_current_user
from app.core.serialize import serialize, serialize_list
from app.core.audit import audit
from app.core.ids import next_ref
from app.modules.identity_models import User
from app.modules.vendors_models import Vendor, VendorContact, VendorAgreement
from app.modules.catalog_models import Product
from app.modules.orders_models import Order
from app.modules.cod_models import CODCollection
from app.modules.charges_models import Charge
from app.modules.settlements_models import Settlement
from app.core.csvsafe import csv_safe  # noqa: F401
from sqlalchemy import func, distinct

router = APIRouter(prefix="/api/vendors", tags=["vendors"])


class VendorIn(BaseModel):
    name: str
    business_name: str = ""
    email: str = ""
    phone: str = ""
    city: str = ""
    state: str = ""
    status: str = "ACTIVE"
    auto_confirm_orders: bool = False
    settlement_frequency: str = "WEEKLY"
    pricing_notes: str = ""


class VendorPatch(BaseModel):
    name: str | None = None
    business_name: str | None = None
    email: str | None = None
    phone: str | None = None
    city: str | None = None
    state: str | None = None
    status: str | None = None
    auto_confirm_orders: bool | None = None
    settlement_frequency: str | None = None
    pricing_notes: str | None = None


class ContactPatch(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    is_primary: bool | None = None
    is_whatsapp: bool | None = None
    wa_verified: bool | None = None
    verification_method: str | None = None


VENDOR_STATUSES = ("ACTIVE", "SUSPENDED", "PENDING", "INACTIVE")
FREQUENCIES = ("DAILY", "WEEKLY", "BIWEEKLY", "MONTHLY")


class ContactIn(BaseModel):
    name: str
    phone: str
    email: str = ""
    is_primary: bool = False
    is_whatsapp: bool = True
    wa_verified: bool = True
    verification_method: str = "PHONE_NUMBER"


class AgreementIn(BaseModel):
    title: str
    terms: str = ""
    document_ref: str = ""


def normalize_phone(p: str) -> str:
    digits = "".join(ch for ch in (p or "") if ch.isdigit())
    if digits.startswith("234"):
        digits = "0" + digits[3:]
    return digits


@router.get("")
def list_vendors(user: User = Depends(require_staff), db: Session = Depends(get_db),
                 q: str = "", status: str = ""):
    query = db.query(Vendor)
    if q:
        query = query.filter(Vendor.name.ilike(f"%{q}%"))
    if status:
        query = query.filter(Vendor.status == status)
    vendors = query.order_by(Vendor.name).all()
    vendor_ids = [v.id for v in vendors]
    contacts = db.query(VendorContact).filter(VendorContact.vendor_id.in_(vendor_ids)).all() if vendor_ids else []
    prod_counts = dict(db.query(Product.vendor_id, func.count(Product.id)).filter(
        Product.vendor_id.in_(vendor_ids)).group_by(Product.vendor_id).all()) if vendor_ids else {}
    order_counts = dict(db.query(Order.vendor_id, func.count(Order.id)).filter(
        Order.vendor_id.in_(vendor_ids)).group_by(Order.vendor_id).all()) if vendor_ids else {}
    primary_by_vendor = {}
    for c in contacts:
        if c.is_primary or c.vendor_id not in primary_by_vendor:
            primary_by_vendor[c.vendor_id] = c
    out = []
    for v in vendors:
        c = primary_by_vendor.get(v.id)
        out.append(serialize(v, primary_contact=serialize(c) if c else None,
                             product_count=prod_counts.get(v.id, 0),
                             order_count=order_counts.get(v.id, 0)))
    return out


@router.post("")
def create_vendor(body: VendorIn, user: User = Depends(require_perm("vendors.manage")), db: Session = Depends(get_db)):
    if not body.name.strip():
        raise HTTPException(400, "Vendor name is required")
    if body.status not in VENDOR_STATUSES:
        raise HTTPException(400, f"status must be one of {', '.join(VENDOR_STATUSES)}")
    if body.settlement_frequency not in FREQUENCIES:
        raise HTTPException(400, f"settlement_frequency must be one of {', '.join(FREQUENCIES)}")
    if db.query(Vendor).filter(func.lower(Vendor.name) == body.name.strip().lower()).first():
        raise HTTPException(400, "A vendor with this name already exists")
    v = Vendor(code="PENDING", **body.model_dump())
    db.add(v)
    db.flush()
    v.code = f"VD-{1000 + v.id}"
    db.commit()
    audit(db, user, "create", "vendor", v.id, f"Registered vendor {v.name}")
    db.commit()
    return serialize(v)


@router.get("/{vendor_id}")
def get_vendor(vendor_id: int, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    v = db.get(Vendor, vendor_id)
    if not v:
        raise HTTPException(404, "Vendor not found")
    contacts = db.query(VendorContact).filter(VendorContact.vendor_id == vendor_id).order_by(VendorContact.id).all()
    agreements = db.query(VendorAgreement).filter(VendorAgreement.vendor_id == vendor_id).all()
    order_stats = db.query(Order.status, func.count(Order.id)).filter(Order.vendor_id == vendor_id).group_by(Order.status).all()
    collected = db.query(func.coalesce(func.sum(CODCollection.collected_kobo), 0)).filter(
        CODCollection.order_id.in_(db.query(Order.id).filter(Order.vendor_id == vendor_id)),
        CODCollection.verified_at.isnot(None)).scalar()
    charges = db.query(func.coalesce(func.sum(Charge.amount_kobo), 0)).filter(
        Charge.vendor_id == vendor_id, Charge.status == "APPLIED").scalar()
    settled = db.query(func.coalesce(func.sum(Settlement.net_kobo), 0)).filter(
        Settlement.vendor_id == vendor_id, Settlement.status.in_(["PAID", "PARTIALLY_PAID"])).scalar()
    # Outstanding payable from the double-entry ledger (vendor-scoped journal lines)
    from app.modules.ledger_models import JournalLine, JournalEntry
    ledger_payable = (db.query(func.coalesce(func.sum(JournalLine.credit_kobo - JournalLine.debit_kobo), 0))
                      .select_from(JournalLine).join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
                      .filter(JournalLine.vendor_id == vendor_id, JournalEntry.status.in_(("POSTED", "REVERSED")),
                              JournalEntry.source_type.in_(["COD_COLLECTION", "CHARGE_RECOGNITION", "SETTLEMENT_PAYOUT"]))
                      .scalar() or 0)
    payable = max(0, ledger_payable)
    return serialize(v, contacts=serialize_list(contacts), agreements=serialize_list(agreements),
                     order_stats=[{"status": s, "count": c} for s, c in order_stats],
                     financial_summary={
                         "verified_collections_kobo": collected or 0,
                         "charges_kobo": charges or 0,
                         "settled_kobo": settled or 0,
                         "outstanding_payable_kobo": payable,
                     })


@router.patch("/{vendor_id}")
def update_vendor(vendor_id: int, body: VendorPatch, user: User = Depends(require_perm("vendors.manage")), db: Session = Depends(get_db)):
    v = db.get(Vendor, vendor_id)
    if not v:
        raise HTTPException(404, "Vendor not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("status") is not None and data["status"] not in VENDOR_STATUSES:
        raise HTTPException(400, f"status must be one of {', '.join(VENDOR_STATUSES)}")
    if data.get("settlement_frequency") is not None and data["settlement_frequency"] not in FREQUENCIES:
        raise HTTPException(400, f"settlement_frequency must be one of {', '.join(FREQUENCIES)}")
    if "name" in data and not (data["name"] or "").strip():
        raise HTTPException(400, "Vendor name cannot be empty")
    for k, val in data.items():
        if val is not None:
            setattr(v, k, val)
    db.commit()
    audit(db, user, "update", "vendor", v.id, f"Updated vendor {v.name}")
    db.commit()
    return serialize(v)


@router.post("/{vendor_id}/contacts")
def add_contact(vendor_id: int, body: ContactIn, user: User = Depends(require_perm("vendors.manage")), db: Session = Depends(get_db)):
    v = db.get(Vendor, vendor_id)
    if not v:
        raise HTTPException(404, "Vendor not found")
    phone = normalize_phone(body.phone)
    if not phone or len(phone) < 10:
        raise HTTPException(400, "Valid phone number required")
    existing = db.query(VendorContact).filter(VendorContact.phone == phone).first()
    if existing:
        raise HTTPException(400, "This phone number is already registered to another vendor contact")
    c = VendorContact(vendor_id=vendor_id, name=body.name, phone=phone, email=body.email,
                      is_primary=body.is_primary, is_whatsapp=body.is_whatsapp,
                      wa_verified=body.wa_verified, verification_method=body.verification_method,
                      verified_at=utcnow() if body.wa_verified else None)
    if body.is_primary:
        for other in db.query(VendorContact).filter(VendorContact.vendor_id == vendor_id).all():
            other.is_primary = False
    db.add(c)
    db.commit()
    audit(db, user, "create", "vendor_contact", c.id, f"Added contact {c.name} ({c.phone}) to {v.name}")
    db.commit()
    return serialize(c)


@router.patch("/contacts/{contact_id}")
def update_contact(contact_id: int, body: ContactPatch, user: User = Depends(require_perm("vendors.manage")), db: Session = Depends(get_db)):
    c = db.get(VendorContact, contact_id)
    if not c:
        raise HTTPException(404, "Contact not found")
    data = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if "phone" in data:
        data["phone"] = normalize_phone(data["phone"])
        if len(data["phone"]) < 10:
            raise HTTPException(400, "Valid phone number required")
        clash = db.query(VendorContact).filter(VendorContact.phone == data["phone"],
                                               VendorContact.id != c.id).first()
        if clash:
            raise HTTPException(400, "This phone number is already registered to another vendor contact")
    if data.get("is_primary"):
        for other in db.query(VendorContact).filter(VendorContact.vendor_id == c.vendor_id,
                                                    VendorContact.id != c.id).all():
            other.is_primary = False
    if data.get("wa_verified") and not c.wa_verified:
        c.verified_at = utcnow()
    for k, val in data.items():
        setattr(c, k, val)
    audit(db, user, "update", "vendor_contact", c.id, f"Updated contact {c.name} ({c.phone})")
    db.commit()
    return serialize(c)


@router.delete("/contacts/{contact_id}")
def delete_contact(contact_id: int, user: User = Depends(require_perm("vendors.manage")), db: Session = Depends(get_db)):
    c = db.get(VendorContact, contact_id)
    if not c:
        raise HTTPException(404, "Contact not found")
    audit(db, user, "delete", "vendor_contact", c.id, f"Removed contact {c.name} ({c.phone})")
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.post("/{vendor_id}/agreements")
def add_agreement(vendor_id: int, body: AgreementIn, user: User = Depends(require_perm("vendors.manage")), db: Session = Depends(get_db)):
    if not db.get(Vendor, vendor_id):
        raise HTTPException(404, "Vendor not found")
    a = VendorAgreement(vendor_id=vendor_id, **body.model_dump())
    db.add(a)
    db.commit()
    audit(db, user, "create", "vendor_agreement", a.id, f"Added agreement {a.title}")
    db.commit()
    return serialize(a)


@router.get("/{vendor_id}/statement")
def vendor_statement(vendor_id: int, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Vendor account statement: collections, charges, settlements as line items."""
    v = db.get(Vendor, vendor_id)
    if not v:
        raise HTTPException(404, "Vendor not found")
    order_ids = [r[0] for r in db.query(Order.id).filter(Order.vendor_id == vendor_id).all()]
    lines = []
    for c in db.query(CODCollection).filter(CODCollection.order_id.in_(order_ids or [0])).order_by(CODCollection.id).all():
        lines.append({"date": c.created_at, "type": "COD_COLLECTION", "label": f"COD collection (order #{c.order_id})",
                      "credit_kobo": c.collected_kobo, "status": c.status})
    for ch in db.query(Charge).filter(Charge.vendor_id == vendor_id).order_by(Charge.id).all():
        lines.append({"date": ch.created_at, "type": "CHARGE", "label": f"{ch.charge_type} ({ch.reason or 'charge'})",
                      "debit_kobo": ch.amount_kobo, "status": ch.status})
    for s in db.query(Settlement).filter(Settlement.vendor_id == vendor_id).order_by(Settlement.id).all():
        lines.append({"date": s.created_at, "type": "SETTLEMENT", "label": f"Settlement {s.reference} ({s.status})",
                      "debit_kobo": s.net_kobo, "status": s.status})
    lines.sort(key=lambda l: l["date"] or "")
    return {"vendor": serialize(v), "lines": lines}


def _naira(k: int) -> str:
    return f"₦{(k or 0) / 100:,.0f}"


def _narrate(items, order) -> str:
    """Plain-language story of what was sold on an order."""
    parts = []
    for it in items:
        name = (it.name_snapshot or "").replace(" (free gift)", "")
        if it.is_gift:
            parts.append(f"{it.qty} x {name} given free")
        elif it.discount_kobo:
            parts.append(f"{it.qty} x {name} at {_naira(it.unit_price_kobo)} each, sold for {_naira(it.line_total_kobo)} (offer, customer saved {_naira(it.discount_kobo)})")
        else:
            parts.append(f"{it.qty} x {name} at {_naira(it.unit_price_kobo)} each = {_naira(it.line_total_kobo)}")
    text = "; ".join(parts)
    if order.discount_kobo:
        text += f"; order discount {_naira(order.discount_kobo)}" + (f" ({order.discount_note})" if order.discount_note else "")
    return text


@router.get("/{vendor_id}/record")
def vendor_record(vendor_id: int, date_from: str = "", date_to: str = "",
                  user: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Everything we have done for one vendor: sales with narration, money remitted, stock held.
    Built so it can be printed or exported and sent to the vendor in a dispute."""
    from datetime import datetime, timedelta
    from app.modules.orders_models import OrderItem, Customer
    from app.modules.settlements_models import SettlementItem, Payment
    from app.modules.inventory_models import InventoryBalance
    v = db.get(Vendor, vendor_id)
    if not v:
        raise HTTPException(404, "Vendor not found")

    def parse(s, end=False):
        if not s:
            return None
        try:
            d = datetime.strptime(s[:10], "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, "Dates must look like 2026-11-30")
        return d + timedelta(days=1) if end else d
    start, end = parse(date_from), parse(date_to, True)

    q = db.query(Order).filter(Order.vendor_id == vendor_id)
    if start:
        q = q.filter(Order.created_at >= start)
    if end:
        q = q.filter(Order.created_at < end)
    orders = q.order_by(Order.created_at.desc()).all()
    oids = [o.id for o in orders] or [0]
    items_by = {}
    for it in db.query(OrderItem).filter(OrderItem.order_id.in_(oids)).order_by(OrderItem.id).all():
        items_by.setdefault(it.order_id, []).append(it)
    custs = {c.id: c for c in db.query(Customer).filter(Customer.id.in_([o.customer_id for o in orders] or [0])).all()}
    collected = {}
    for c in db.query(CODCollection).filter(CODCollection.order_id.in_(oids)).all():
        t = collected.setdefault(c.order_id, {"kobo": 0, "verified": True})
        t["kobo"] += c.collected_kobo
        t["verified"] = t["verified"] and c.status in ("VERIFIED", "DISCREPANCY")
    charges = {}
    for ch in db.query(Charge).filter(Charge.order_id.in_(oids), Charge.status != "REVERSED").all():
        charges[ch.order_id] = charges.get(ch.order_id, 0) + ch.amount_kobo
    settled_orders = {r[0] for r in db.query(SettlementItem.order_id).filter(
        SettlementItem.order_id.in_(oids), SettlementItem.type == "COLLECTION").all()}

    sales, lines = [], []
    s = {"orders": len(orders), "delivered": 0, "open": 0, "cancelled_or_returned": 0, "units_sold": 0,
         "gift_units": 0, "gift_value_kobo": 0, "normal_value_kobo": 0, "offers_kobo": 0, "sales_kobo": 0,
         "charges_kobo": 0, "collected_kobo": 0}
    for o in orders:
        its = items_by.get(o.id, [])
        delivered = o.status == "DELIVERED"
        if delivered:
            s["delivered"] += 1
        elif o.status in ("CANCELLED", "RETURNED_TO_WAREHOUSE", "RETURN_REQUESTED", "RETURN_IN_TRANSIT"):
            s["cancelled_or_returned"] += 1
        else:
            s["open"] += 1
        order_charges = charges.get(o.id, 0) if delivered else 0
        if delivered:
            for it in its:
                if it.is_gift:
                    s["gift_units"] += it.qty
                    s["gift_value_kobo"] += it.qty * it.unit_price_kobo
                else:
                    s["units_sold"] += it.qty
                    s["normal_value_kobo"] += it.qty * it.unit_price_kobo
                    s["offers_kobo"] += it.discount_kobo
            s["offers_kobo"] += o.discount_kobo
            s["sales_kobo"] += o.items_total_kobo
            s["charges_kobo"] += order_charges
            s["collected_kobo"] += collected.get(o.id, {}).get("kobo", 0)
        c = custs.get(o.customer_id)
        # Same rule the settlement uses: cash actually collected for the order, less our charges on it.
        # (The delivery fee the customer pays on top is what covers the delivery charge.)
        got = collected.get(o.id, {}).get("kobo", 0)
        net = got - order_charges if delivered and got else 0
        sales.append({
            "id": o.id, "reference": o.reference, "date": o.delivered_at or o.created_at, "created_at": o.created_at,
            "status": o.status, "customer": c.name if c else "", "payment_method": o.payment_method,
            "narration": _narrate(its, o), "items_total_kobo": o.items_total_kobo,
            "order_discount_kobo": o.discount_kobo, "delivery_fee_kobo": o.delivery_fee_kobo,
            "collected_kobo": collected.get(o.id, {}).get("kobo", 0), "charges_kobo": order_charges,
            "net_kobo": net, "settled": o.id in settled_orders,
            "items": [{"name": (i.name_snapshot or "").replace(" (free gift)", ""), "sku": i.sku_snapshot, "qty": i.qty,
                       "unit_price_kobo": i.unit_price_kobo, "line_total_kobo": i.line_total_kobo,
                       "discount_kobo": i.discount_kobo, "is_gift": i.is_gift} for i in its],
        })
        for i in its:
            lines.append({"order": o.reference, "date": o.delivered_at or o.created_at, "status": o.status,
                          "customer": c.name if c else "", "product": (i.name_snapshot or "").replace(" (free gift)", ""),
                          "sku": i.sku_snapshot, "qty": i.qty, "unit_price_kobo": i.unit_price_kobo,
                          "line_total_kobo": 0 if i.is_gift else i.line_total_kobo, "is_gift": i.is_gift,
                          "line_discount_kobo": i.discount_kobo})
    earned = sum(x["net_kobo"] for x in sales)

    pq = db.query(Payment).filter(Payment.vendor_id == vendor_id)
    if start:
        pq = pq.filter(Payment.paid_at >= start)
    if end:
        pq = pq.filter(Payment.paid_at < end)
    users = {u.id: u.full_name for u in db.query(User).all()}
    sref = {x.id: x.reference for x in db.query(Settlement).filter(Settlement.vendor_id == vendor_id).all()}
    remittances = [{"date": p.paid_at or p.created_at, "settlement": sref.get(p.settlement_id, ""),
                    "amount_kobo": p.amount_kobo, "method": p.method, "bank_ref": p.bank_ref,
                    "note": p.note, "recorded_by": users.get(p.recorded_by_user_id, "")}
                   for p in pq.order_by(Payment.paid_at.desc(), Payment.id.desc()).all()]
    paid_out = sum(r["amount_kobo"] for r in remittances)

    sq = db.query(Settlement).filter(Settlement.vendor_id == vendor_id)
    settlements = []
    for st in sq.order_by(Settlement.id.desc()).all():
        refs = [r[0] for r in db.query(Order.reference).join(SettlementItem, SettlementItem.order_id == Order.id)
                .filter(SettlementItem.settlement_id == st.id, SettlementItem.type == "COLLECTION").all()]
        settlements.append({"id": st.id, "reference": st.reference, "date": st.created_at, "gross_kobo": st.gross_kobo,
                            "charges_kobo": st.charges_kobo, "net_kobo": st.net_kobo, "paid_kobo": st.paid_kobo,
                            "status": st.status, "orders": refs})

    stock = []
    for p in db.query(Product).filter(Product.vendor_id == vendor_id).order_by(Product.name).all():
        b = db.query(func.coalesce(func.sum(InventoryBalance.qty_physical), 0),
                     func.coalesce(func.sum(InventoryBalance.qty_reserved), 0),
                     func.coalesce(func.sum(InventoryBalance.qty_damaged), 0)).filter(InventoryBalance.product_id == p.id).one()
        stock.append({"id": p.id, "name": p.name, "sku": p.sku, "price_kobo": p.default_sell_price_kobo,
                      "reorder_level": p.reorder_level, "status": p.status,
                      "physical": int(b[0]), "reserved": int(b[1]), "damaged": int(b[2]), "available": int(b[0]) - int(b[1])})

    return {"vendor": serialize(v), "period": {"from": date_from, "to": date_to},
            "summary": {**s, "earned_kobo": earned, "paid_out_kobo": paid_out, "balance_kobo": earned - paid_out},
            "sales": sales, "lines": lines, "remittances": remittances, "settlements": settlements, "stock": stock}
