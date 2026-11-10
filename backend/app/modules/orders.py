import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.db import get_db, utcnow
from app.core.deps import require_staff, require_perm, get_current_user
from app.core.serialize import serialize, serialize_list
from app.core.audit import audit
from app.core.ids import next_ref
from app.core.money import naira_to_kobo
from app.modules.identity_models import User
from app.modules.vendors_models import Vendor
from app.modules.orders_models import (Customer, CustomerAddress, OrderDraft, Order, OrderItem,
                                       OrderEvent, CustomerConfirmation, ConfirmationAttempt)
from app.modules.catalog_models import Product, ProductVariant
from app.modules.inventory_models import StockReceipt, Warehouse  # noqa (StockReceipt imports for metadata)
from app.modules.inventory import reserve_stock, release_reservations, consume_reservations, restock_return, default_warehouse
from app.modules.notify import notify

router = APIRouter(prefix="/api/orders", tags=["orders"])
customers_router = APIRouter(prefix="/api/customers", tags=["customers"])
confirmations_router = APIRouter(prefix="/api/confirmations", tags=["confirmations"])

ORDER_STATUSES = [
    "DRAFT", "PENDING_REVIEW", "AWAITING_INFORMATION", "PENDING_VENDOR_CONFIRMATION",
    "CONFIRMED", "PENDING_CUSTOMER_CONFIRMATION", "CUSTOMER_CONFIRMED", "PROCESSING",
    "READY_FOR_DISPATCH", "DISPATCHED", "IN_TRANSIT", "DELIVERED", "DELIVERY_FAILED",
    "RETURN_REQUESTED", "RETURN_IN_TRANSIT", "RETURNED_TO_WAREHOUSE", "CANCELLED",
]
TRANSITIONS: dict[str, list[str]] = {
    "DRAFT": ["PENDING_REVIEW", "CONFIRMED", "CANCELLED"],
    "PENDING_REVIEW": ["CONFIRMED", "AWAITING_INFORMATION", "PENDING_VENDOR_CONFIRMATION", "CANCELLED"],
    "AWAITING_INFORMATION": ["PENDING_REVIEW", "CONFIRMED", "CANCELLED"],
    "PENDING_VENDOR_CONFIRMATION": ["CONFIRMED", "CANCELLED"],
    "CONFIRMED": ["PENDING_CUSTOMER_CONFIRMATION", "PROCESSING", "READY_FOR_DISPATCH", "CANCELLED"],
    "PENDING_CUSTOMER_CONFIRMATION": ["CUSTOMER_CONFIRMED", "CANCELLED"],
    "CUSTOMER_CONFIRMED": ["PROCESSING", "READY_FOR_DISPATCH", "CANCELLED"],
    "PROCESSING": ["READY_FOR_DISPATCH", "PENDING_CUSTOMER_CONFIRMATION", "CANCELLED"],
    "READY_FOR_DISPATCH": ["DISPATCHED", "IN_TRANSIT", "DELIVERED", "CANCELLED"],
    "DISPATCHED": ["IN_TRANSIT", "DELIVERED", "DELIVERY_FAILED", "RETURN_REQUESTED"],
    "IN_TRANSIT": ["DELIVERED", "DELIVERY_FAILED", "RETURN_REQUESTED"],
    "DELIVERED": ["RETURN_REQUESTED"],
    "DELIVERY_FAILED": ["RETURN_REQUESTED", "RETURN_IN_TRANSIT", "READY_FOR_DISPATCH", "CANCELLED"],
    "RETURN_REQUESTED": ["RETURN_IN_TRANSIT", "RETURNED_TO_WAREHOUSE"],
    "RETURN_IN_TRANSIT": ["RETURNED_TO_WAREHOUSE"],
    "RETURNED_TO_WAREHOUSE": [],
    "CANCELLED": [],
}

# "Mark delivered" can skip every step once the order is confirmed (e.g. handed over directly).
for _st in ("CONFIRMED", "PENDING_CUSTOMER_CONFIRMATION", "CUSTOMER_CONFIRMED", "PROCESSING", "READY_FOR_DISPATCH",
            "DISPATCHED", "IN_TRANSIT", "DELIVERY_FAILED"):
    if "DELIVERED" not in TRANSITIONS[_st]:
        TRANSITIONS[_st].insert(-1 if TRANSITIONS[_st][-1] == "CANCELLED" else len(TRANSITIONS[_st]), "DELIVERED")
SKIPPABLE_TO_DELIVERED = ("CONFIRMED", "PENDING_CUSTOMER_CONFIRMATION", "CUSTOMER_CONFIRMED", "PROCESSING",
                          "READY_FOR_DISPATCH", "DELIVERY_FAILED")


class ManualOrderItem(BaseModel):
    product_id: int
    variant_id: int = 0
    qty: int = 1
    unit_price_kobo: int | None = None
    line_total_kobo: int | None = None  # bundle price for the whole line, e.g. 2 books for 50
    discount_kobo: int = 0               # money off this line
    is_gift: bool = False                # free item added to the order


class ManualOrderIn(BaseModel):
    vendor_id: int
    customer_name: str
    customer_phone: str
    customer_alt_phone: str = ""
    delivery_state: str = ""
    delivery_city: str = ""
    delivery_area: str = ""
    delivery_street: str = ""
    delivery_landmark: str = ""
    instructions: str = ""
    payment_method: str = "COD"
    warehouse_id: int | None = None  # optional fulfilment override (multi-warehouse)
    discount_kobo: int = 0           # money off the whole order
    discount_percent: float = 0      # or a percentage off the whole order
    discount_note: str = ""
    items: list[ManualOrderItem]


class StatusIn(BaseModel):
    to_status: str
    note: str = ""


class DraftEditIn(BaseModel):
    customer_name: str | None = None
    customer_phone: str | None = None
    quantity: int | None = None
    unit_price_kobo: int | None = None
    state: str | None = None
    city: str | None = None
    street: str | None = None
    product_id: int | None = None
    variant_id: int | None = None
    review_notes: str | None = None


PAYMENT_METHODS = ("COD", "PREPAID", "TRANSFER", "POS")
ATTEMPT_OUTCOMES = ("CALL_ATTEMPTED", "NO_ANSWER", "PHONE_SWITCHED_OFF", "CUSTOMER_AWAY", "INVALID_PHONE_NUMBER", "CUSTOMER_CONFIRMED",
                    "CUSTOMER_REJECTED", "CUSTOMER_REQUESTED_RESCHEDULE", "ADDRESS_NEEDS_CORRECTION")
ATTEMPT_ALLOWED_ORDER_STATUSES = ("CONFIRMED", "PENDING_CUSTOMER_CONFIRMATION", "PROCESSING")


def normalize_phone(p: str) -> str:
    digits = "".join(ch for ch in (p or "") if ch.isdigit())
    if digits.startswith("234") and len(digits) >= 13:
        digits = "0" + digits[3:]
    return digits


class AssignIn(BaseModel):
    user_id: int | None = None


class AttemptIn(BaseModel):
    outcome: str
    note: str = ""
    follow_up_date: str | None = None   # YYYY-MM-DD: when to call again / when the customer will collect


class OutcomeIn(BaseModel):
    status: str
    note: str = ""
    next_action_at: str | None = None


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------

def titleize_status(s: str) -> str:
    return (s or "").replace("_", " ").title()


def add_event(db, order, event_type, from_status="", to_status="", actor=None, note=""):
    db.add(OrderEvent(order_id=order.id, event_type=event_type, from_status=from_status,
                      to_status=to_status, actor_label=(actor.full_name if actor else "system"),
                      note=note))


def upsert_customer(db, vendor_id: int, name: str, phone: str, alt_phone: str = "") -> Customer:
    phone = normalize_phone(phone) or (phone or "").strip()
    if not phone:
        raise HTTPException(400, "Customer phone number is required")
    c = db.query(Customer).filter(Customer.vendor_id == vendor_id, Customer.phone == phone).first()
    if not c:
        c = Customer(vendor_id=vendor_id, name=name or "Unknown", phone=phone, alt_phone=alt_phone or "")
        db.add(c)
        db.flush()
    elif name and c.name in ("Unknown", ""):
        c.name = name
    if alt_phone and not c.alt_phone:
        c.alt_phone = alt_phone
    return c


def duplicate_check(db, vendor_id: int, customer_phone: str, product_id: int, qty: int) -> Order | None:
    """Flag probable duplicates without discarding legitimate repeat orders."""
    cutoff = utcnow() - timedelta(hours=48)
    rows = (db.query(Order, OrderItem)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .filter(Order.vendor_id == vendor_id,
                    Order.created_at >= cutoff,
                    Order.status.notin_(["CANCELLED"]),
                    OrderItem.product_id == product_id,
                    OrderItem.qty == qty)
            .all())
    phone = normalize_phone(customer_phone) or (customer_phone or "").strip()
    for o, item in rows:
        cust = db.get(Customer, o.customer_id)
        if cust and cust.phone == phone:
            return o
    return None


def pick_warehouse(db, product_id: int, qty: int, preferred_warehouse_id: int | None = None):
    """Warehouse that physically holds this product with enough available stock;
    a preferred (e.g. staff-chosen or user home) warehouse wins when it can fulfil;
    falls back to the default warehouse (which then raises a clear stock error)."""
    from app.modules.inventory_models import InventoryBalance
    if preferred_warehouse_id:
        bal = (db.query(InventoryBalance)
               .filter(InventoryBalance.product_id == product_id,
                       InventoryBalance.warehouse_id == preferred_warehouse_id,
                       (InventoryBalance.qty_physical - InventoryBalance.qty_reserved) >= qty)
               .first())
        if bal:
            w = db.get(Warehouse, bal.warehouse_id)
            if w and w.is_active:
                return w
    bal = (db.query(InventoryBalance)
           .filter(InventoryBalance.product_id == product_id,
                   (InventoryBalance.qty_physical - InventoryBalance.qty_reserved) >= qty)
           .first())
    if bal:
        return db.get(Warehouse, bal.warehouse_id) or default_warehouse(db)
    return default_warehouse(db)


def create_order_from_draft(db, draft: OrderDraft, actor=None) -> Order:
    """Convert a validated draft into an operational order + stock reservations."""
    x = draft.extracted or {}
    if not draft.vendor_id:
        raise HTTPException(400, "Draft has no vendor identity")
    vendor = db.get(Vendor, draft.vendor_id)
    if not vendor or vendor.status != "ACTIVE":
        raise HTTPException(400, "Vendor account is not active")

    product_id = x.get("product_id") or (x.get("product") or {}).get("product_id")
    variant_id = x.get("variant_id") or (x.get("product") or {}).get("variant_id") or 0
    product = db.get(Product, int(product_id)) if product_id else None
    if not product:
        raise HTTPException(400, "Draft has no resolved product. Match the product first.")
    if product.vendor_id != draft.vendor_id:
        raise HTTPException(400, "Product does not belong to this vendor")

    qty = int(x.get("quantity") or 0)
    if qty <= 0:
        raise HTTPException(400, "Quantity must be at least 1")
    if variant_id:
        _pv = db.get(ProductVariant, int(variant_id))
        if not _pv or _pv.product_id != product.id:
            raise HTTPException(400, "Draft variant does not belong to the matched product")
    pay_method = x.get("payment_method") or "COD"
    if pay_method not in PAYMENT_METHODS:
        raise HTTPException(400, f"Unknown payment method {pay_method}")

    unit_price = int(x.get("unit_price_kobo") or 0)
    price_source = x.get("price_source", "EXTRACTED")
    if unit_price <= 0:
        unit_price = product.default_sell_price_kobo or 0
        price_source = "DEFAULT"
    if unit_price <= 0:
        raise HTTPException(400, "No selling price available. Never invent prices - set a price on the product or draft.")

    cust_name = x.get("customer_name")
    cust_phone = x.get("customer_phone")
    if not cust_phone:
        raise HTTPException(400, "Customer phone number is missing")

    warehouse = pick_warehouse(db, product.id, qty)
    customer = upsert_customer(db, draft.vendor_id, cust_name, cust_phone, x.get("customer_phone_alt") or "")
    if (x.get("state") or x.get("city")):
        addr_exists = db.query(CustomerAddress).filter(CustomerAddress.customer_id == customer.id).first()
        if not addr_exists:
            db.add(CustomerAddress(customer_id=customer.id, state=x.get("state") or "",
                                   city=x.get("city") or "", street=x.get("street") or "",
                                   is_default=True))

    line_total = qty * unit_price
    delivery_fee = 0
    cod_amount = line_total + delivery_fee if pay_method == "COD" else 0

    order = Order(reference="PENDING", vendor_id=draft.vendor_id, customer_id=customer.id,
                  warehouse_id=warehouse.id, status="CONFIRMED",
                  payment_method=pay_method,
                  source=draft.source or "WHATSAPP", source_message_id=draft.message_id,
                  draft_id=draft.id, delivery_state=x.get("state") or "", delivery_city=x.get("city") or "",
                  delivery_area=x.get("area") or "", delivery_street=x.get("street") or "",
                  delivery_landmark=x.get("landmark") or "", instructions=x.get("instructions") or "",
                  items_total_kobo=line_total, delivery_fee_kobo=delivery_fee,
                  cod_amount_kobo=cod_amount, created_by_user_id=actor.id if actor else None,
                  confirmed_at=utcnow())
    db.add(order)
    db.flush()
    order.reference = next_ref(db, Order, "reference", "KW")
    db.add(OrderItem(order_id=order.id, product_id=product.id, variant_id=variant_id,
                     name_snapshot=f"{product.name}" + (f" ({_pv.name})" if variant_id else ""),
                     sku_snapshot=product.sku, qty=qty, unit_price_kobo=unit_price,
                     line_total_kobo=line_total, price_source=price_source))
    # Stock reservation (raises 400 when insufficient)
    reserve_stock(db, order.id, product.id, variant_id, warehouse.id, qty, actor)
    add_event(db, order, "CREATED", to_status="CONFIRMED", actor=actor,
              note=f"Created from draft {draft.draft_ref} ({draft.source})")
    if draft.duplicate_of_order_id:
        add_event(db, order, "FLAGGED", actor=actor, note=f"Possible duplicate of order id {draft.duplicate_of_order_id}")

    draft.status = "CONVERTED"
    draft.converted_order_id = order.id

    notify(db, event_type="ORDER_CREATED", title=f"New order {order.reference}",
           body=f"{vendor.name}: {product.name} x{qty} for {customer.name}",
           vendor_id=vendor.id, entity_type="order", entity_id=order.id)
    audit(db, actor, "create", "order", order.id, f"Order {order.reference} created from draft {draft.draft_ref}")
    return order


# ---------------------------------------------------------------------------
# Router endpoints
# ---------------------------------------------------------------------------

@router.get("")
def list_orders(user: User = Depends(require_staff), db: Session = Depends(get_db),
                status: str = "", vendor_id: int = 0, q: str = "", limit: int = 100):
    query = (db.query(Order, Vendor, Customer)
             .join(Vendor, Vendor.id == Order.vendor_id)
             .join(Customer, Customer.id == Order.customer_id))
    if status:
        query = query.filter(Order.status == status)
    if vendor_id:
        query = query.filter(Order.vendor_id == vendor_id)
    if q:
        like = f"%{q}%"
        query = query.filter((Order.reference.ilike(like)) | (Customer.name.ilike(like)) |
                             (Customer.phone.ilike(like)))
    rows = query.order_by(Order.id.desc()).limit(min(limit, 300)).all()
    wh_names = {w.id: w.name for w in db.query(Warehouse).all()}
    return [serialize(o, vendor_name=v.name, customer_name=c.name, customer_phone=c.phone,
                      warehouse_name=wh_names.get(o.warehouse_id, ""),
                      item_count=db.query(OrderItem).filter(OrderItem.order_id == o.id).count())
            for o, v, c in rows]


@router.get("/drafts")
def list_drafts(user: User = Depends(require_staff), db: Session = Depends(get_db),
                status: str = "", vendor_id: int = 0):
    query = db.query(OrderDraft)
    if status:
        query = query.filter(OrderDraft.status == status)
    if vendor_id:
        query = query.filter(OrderDraft.vendor_id == vendor_id)
    rows = query.order_by(OrderDraft.id.desc()).limit(150).all()
    out = []
    for d in rows:
        v = db.get(Vendor, d.vendor_id) if d.vendor_id else None
        x = d.extracted or {}
        out.append(serialize(d, vendor_name=v.name if v else "Unassigned",
                             customer_name=x.get("customer_name"),
                             product_label=(x.get("product") or {}).get("name") or "Unresolved product",
                             quantity=x.get("quantity")))
    return out


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: int, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    d = db.get(OrderDraft, draft_id)
    if not d:
        raise HTTPException(404, "Draft not found")
    v = db.get(Vendor, d.vendor_id) if d.vendor_id else None
    msg = None
    if d.message_id:
        from app.modules.conversations_models import Message
        msg = db.get(Message, d.message_id)
    return serialize(d, vendor_name=v.name if v else None,
                     original_message=serialize(msg) if msg else None)


@router.patch("/drafts/{draft_id}")
def edit_draft(draft_id: int, body: DraftEditIn, user: User = Depends(require_perm("orders.manage")), db: Session = Depends(get_db)):
    """Staff corrections to AI-extracted fields (PRD: allow staff to correct extracted fields)."""
    d = db.get(OrderDraft, draft_id)
    if not d:
        raise HTTPException(404, "Draft not found")
    if d.status in ("CONVERTED", "DISCARDED"):
        raise HTTPException(400, f"Draft already {d.status}")
    x = dict(d.extracted or {})
    data = body.model_dump(exclude_unset=True)
    if data.get("customer_name") is not None:
        x["customer_name"] = data["customer_name"]
    if data.get("customer_phone") is not None:
        x["customer_phone"] = data["customer_phone"]
    if data.get("quantity") is not None:
        if int(data["quantity"]) <= 0:
            raise HTTPException(400, "Quantity must be at least 1")
        x["quantity"] = int(data["quantity"])
    if data.get("unit_price_kobo") is not None:
        if int(data["unit_price_kobo"]) <= 0:
            raise HTTPException(400, "Unit price must be positive")
        x["unit_price_kobo"] = int(data["unit_price_kobo"])
        x["price_source"] = "MANUAL"
    if data.get("state") is not None:
        x["state"] = data["state"]
    if data.get("city") is not None:
        x["city"] = data["city"]
    if data.get("street") is not None:
        x["street"] = data["street"]
    if data.get("product_id"):
        p = db.get(Product, int(data["product_id"]))
        if not p:
            raise HTTPException(404, "Product not found")
        if d.vendor_id and p.vendor_id != d.vendor_id:
            raise HTTPException(400, "Product must belong to the draft's vendor")
        if data.get("variant_id"):
            _v = db.get(ProductVariant, int(data["variant_id"]))
            if not _v or _v.product_id != p.id:
                raise HTTPException(400, "Variant does not belong to this product")
        x["product"] = {"product_id": p.id, "variant_id": int(data.get("variant_id") or 0),
                        "name": p.name, "sku": p.sku, "score": 100, "matched_label": "manual match"}
    if data.get("review_notes") is not None:
        d.review_notes = data["review_notes"]
    # recompute missing fields
    missing = []
    if not x.get("customer_name"):
        missing.append("customer_name")
    if not x.get("customer_phone"):
        missing.append("customer_phone")
    if not (x.get("product") or x.get("product_id")):
        missing.append("product")
    if not x.get("quantity"):
        missing.append("quantity")
    if not (x.get("city") or x.get("state")):
        missing.append("delivery_address")
    d.extracted = x
    d.missing_fields = missing
    if not missing and d.status == "AWAITING_VENDOR":
        d.status = "PENDING_REVIEW"
    db.commit()
    audit(db, user, "update", "order_draft", d.id, f"Corrected draft {d.draft_ref}")
    db.commit()
    return serialize(d)


@router.post("/drafts/{draft_id}/confirm")
def confirm_draft(draft_id: int, user: User = Depends(require_perm("orders.manage")), db: Session = Depends(get_db)):
    d = db.get(OrderDraft, draft_id)
    if not d:
        raise HTTPException(404, "Draft not found")
    if d.status in ("CONVERTED", "DISCARDED"):
        raise HTTPException(400, f"Draft already {d.status}")
    if d.missing_fields:
        raise HTTPException(400, {"message": "Draft still has missing fields", "missing": d.missing_fields})
    order = create_order_from_draft(db, d, user)
    db.commit()
    # WhatsApp confirmation to the vendor (simulated outbound)
    try:
        from app.modules.conversations import send_outbound_text
        x = d.extracted or {}
        send_outbound_text(db, d.conversation_id,
                           f"Order {order.reference} registered: {x.get('quantity')} x "
                           f"{(x.get('product') or {}).get('name')}. We will update you at every step. Thank you!")
        db.commit()
    except Exception:
        db.rollback()  # the order is already committed; a failed courtesy message must not poison the session
    return serialize(order)


@router.post("/drafts/{draft_id}/discard")
def discard_draft(draft_id: int, user: User = Depends(require_perm("orders.manage")), db: Session = Depends(get_db)):
    d = db.get(OrderDraft, draft_id)
    if not d:
        raise HTTPException(404, "Draft not found")
    d.status = "DISCARDED"
    db.commit()
    audit(db, user, "discard", "order_draft", d.id, f"Discarded draft {d.draft_ref}")
    db.commit()
    return serialize(d)


@router.post("")
def create_manual_order(body: ManualOrderIn, user: User = Depends(require_perm("orders.manage")), db: Session = Depends(get_db)):
    """Staff-assisted manual order entry (fallback channel)."""
    vendor = db.get(Vendor, body.vendor_id)
    if not vendor:
        raise HTTPException(404, "Vendor not found")
    from app.core.vendorguard import vendor_pause_message
    if vendor.status != "ACTIVE":
        raise HTTPException(400, vendor_pause_message(vendor, "create orders"))
    if not body.items:
        raise HTTPException(400, "At least one item is required")
    if not normalize_phone(body.customer_phone) or len(normalize_phone(body.customer_phone)) < 10:
        raise HTTPException(400, "A valid customer phone number is required")
    if not body.customer_name.strip():
        raise HTTPException(400, "Customer name is required")
    if body.payment_method not in PAYMENT_METHODS:
        raise HTTPException(400, f"payment_method must be one of {', '.join(PAYMENT_METHODS)}")
    for it in body.items:
        if it.qty <= 0:
            raise HTTPException(400, "Item quantity must be at least 1")
        if it.unit_price_kobo is not None and it.unit_price_kobo <= 0:
            raise HTTPException(400, "Unit price must be positive")
        if min(it.discount_kobo, it.line_total_kobo if it.line_total_kobo is not None else 0) < 0:
            raise HTTPException(400, "Discounts and bundle prices cannot be negative")
    if body.discount_kobo < 0 or not (0 <= body.discount_percent <= 100):
        raise HTTPException(400, "Order discount must be a positive amount or a percentage up to 100")
    if body.warehouse_id:
        wh = db.get(Warehouse, body.warehouse_id)
        if not wh or not wh.is_active:
            raise HTTPException(400, "Selected warehouse does not exist or is inactive")
    warehouse = pick_warehouse(db, body.items[0].product_id, body.items[0].qty,
                               preferred_warehouse_id=body.warehouse_id)
    customer = upsert_customer(db, body.vendor_id, body.customer_name, body.customer_phone, body.customer_alt_phone)
    total = 0
    prepared = []
    for it in body.items:
        p = db.get(Product, it.product_id)
        if not p:
            raise HTTPException(404, f"Product {it.product_id} not found")
        if p.vendor_id != body.vendor_id:
            raise HTTPException(400, f"Product {p.name} does not belong to vendor {vendor.name}")
        if it.variant_id:
            pv = db.get(ProductVariant, it.variant_id)
            if not pv or pv.product_id != p.id:
                raise HTTPException(400, f"Variant {it.variant_id} does not belong to {p.name}")
        price = it.unit_price_kobo if it.unit_price_kobo is not None else (p.default_sell_price_kobo or 0)
        if price <= 0 and not it.is_gift:
            raise HTTPException(400, f"No price for {p.name}. Set a price on the product first.")
        gross = price * it.qty
        if it.is_gift:
            line_total = 0
        elif it.line_total_kobo is not None:
            if it.line_total_kobo > gross:
                raise HTTPException(400, f"The bundle price for {p.name} is higher than the normal price. Change the unit price instead.")
            line_total = it.line_total_kobo
        else:
            if it.discount_kobo > gross:
                raise HTTPException(400, f"The discount on {p.name} is more than the item costs")
            line_total = gross - it.discount_kobo
        total += line_total
        prepared.append((p, it, price, gross, line_total))
    if total <= 0:
        raise HTTPException(400, "An order needs at least one item that is not free")
    order_discount = body.discount_kobo or int(round(total * body.discount_percent / 100))
    if order_discount > total:
        raise HTTPException(400, "The order discount is more than the order total")
    total -= order_discount
    cod_amount = total if body.payment_method == "COD" else 0
    order = Order(reference="PENDING", vendor_id=vendor.id, customer_id=customer.id,
                  warehouse_id=warehouse.id, status="CONFIRMED", payment_method=body.payment_method,
                  source="MANUAL", delivery_state=body.delivery_state, delivery_city=body.delivery_city,
                  delivery_area=body.delivery_area, delivery_street=body.delivery_street,
                  delivery_landmark=body.delivery_landmark, instructions=body.instructions,
                  items_total_kobo=total, cod_amount_kobo=cod_amount,
                  discount_kobo=order_discount, discount_note=body.discount_note.strip()[:255],
                  created_by_user_id=user.id, confirmed_at=utcnow())
    db.add(order)
    db.flush()
    order.reference = next_ref(db, Order, "reference", "KW")
    for p, it, price, gross, line_total in prepared:
        db.add(OrderItem(order_id=order.id, product_id=p.id, variant_id=it.variant_id or 0,
                         name_snapshot=p.name + (" (free gift)" if it.is_gift else ""), sku_snapshot=p.sku, qty=it.qty,
                         unit_price_kobo=price, line_total_kobo=line_total, discount_kobo=gross - line_total,
                         is_gift=it.is_gift, price_source="MANUAL"))
        reserve_stock(db, order.id, p.id, it.variant_id or 0, warehouse.id, it.qty, user)
    saved = sum(i[3] - i[4] for i in prepared) + order_discount
    add_event(db, order, "CREATED", to_status="CONFIRMED", actor=user,
              note="Manual entry by staff" + (f", customer saves ₦{saved / 100:,.0f}" if saved else ""))
    notify(db, event_type="ORDER_CREATED", title=f"New order {order.reference}",
           body=f"Manual order for {vendor.name}", vendor_id=vendor.id, entity_type="order", entity_id=order.id)
    audit(db, user, "create", "order", order.id, f"Manual order {order.reference} created")
    db.commit()
    return serialize(order, warehouse_name=warehouse.name)


@router.get("/{order_id}")
def get_order(order_id: int, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(404, "Order not found")
    v = db.get(Vendor, o.vendor_id)
    c = db.get(Customer, o.customer_id)
    items = db.query(OrderItem).filter(OrderItem.order_id == o.id).all()
    events = db.query(OrderEvent).filter(OrderEvent.order_id == o.id).order_by(OrderEvent.id).all()
    confirmation = db.query(CustomerConfirmation).filter(CustomerConfirmation.order_id == o.id).first()
    from app.modules.delivery_models import Delivery
    deliveries = db.query(Delivery).filter(Delivery.order_id == o.id).order_by(Delivery.id).all()
    from app.modules.cod_models import CODCollection
    collections = db.query(CODCollection).filter(CODCollection.order_id == o.id).all()
    from app.modules.charges_models import Charge
    charges = db.query(Charge).filter(Charge.order_id == o.id).all()
    draft = db.get(OrderDraft, o.draft_id) if o.draft_id else None
    source_msg = None
    if o.source_message_id:
        from app.modules.conversations_models import Message
        source_msg = db.get(Message, o.source_message_id)
    wh = db.get(Warehouse, o.warehouse_id) if o.warehouse_id else None
    return serialize(o, vendor_name=v.name if v else None,
                     warehouse_name=wh.name if wh else "",
                     customer=serialize(c) if c else None,
                     items=serialize_list(items), events=serialize_list(events),
                     confirmation=serialize(confirmation) if confirmation else None,
                     deliveries=serialize_list(deliveries), collections=serialize_list(collections),
                     charges=serialize_list(charges),
                     draft=serialize(draft) if draft else None,
                     original_message=serialize(source_msg) if source_msg else None)


@router.post("/{order_id}/status")
def change_status(order_id: int, body: StatusIn, user: User = Depends(require_perm("orders.manage")), db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(404, "Order not found")
    to = body.to_status
    if to not in ORDER_STATUSES:
        raise HTTPException(400, f"Unknown status {to}")
    allowed = TRANSITIONS.get(o.status, [])
    # Authorised exceptions: allow skipping customer confirmation with recorded reason (PRD rule)
    if to not in allowed and not (o.status in ("CONFIRMED", "CUSTOMER_CONFIRMED") and to == "READY_FOR_DISPATCH" and body.note.strip()):
        raise HTTPException(400, f"Cannot move order from {o.status} to {to}. Allowed: {', '.join(allowed) or 'none'}")
    if to == "DELIVERED" and o.status in SKIPPABLE_TO_DELIVERED and not body.note.strip():
        raise HTTPException(400, "Add a note saying why the usual steps were skipped")
    if to == "CANCELLED" and not body.note.strip():
        raise HTTPException(400, "A reason is required to cancel an order")
    from_status = o.status
    o.status = to
    if to == "CANCELLED":
        o.cancelled_at = utcnow()
        o.cancel_reason = body.note
        release_reservations(db, o.id, user)
    elif to == "DELIVERED":
        o.delivered_at = utcnow()
        consume_reservations(db, o.id, user)
        from app.modules.cod import ensure_cod_pending
        ensure_cod_pending(db, o)
    elif to == "RETURNED_TO_WAREHOUSE":
        restock_return(db, o.id, user)
    elif to == "CONFIRMED":
        o.confirmed_at = o.confirmed_at or utcnow()
    add_event(db, o, "STATUS_CHANGE", from_status, to, user, body.note)
    audit(db, user, "status_change", "order", o.id, f"Order {o.reference}: {from_status} -> {to}", data={"note": body.note})
    notify(db, event_type="ORDER_STATUS_CHANGED",
           title=f"Order {o.reference}: {titleize_status(to)}",
           body=f"Status moved from {titleize_status(from_status)} to {titleize_status(to)}" + (f" - {body.note}" if body.note else ""),
           vendor_id=o.vendor_id, entity_type="order", entity_id=o.id,
           dedup_key=f"ORDER_STATUS_CHANGED:order:{o.id}:{to}")
    db.commit()
    return serialize(o)


@router.post("/{order_id}/assign")
def assign_order(order_id: int, body: AssignIn, user: User = Depends(require_perm("orders.manage")), db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(404, "Order not found")
    assignee = None
    if body.user_id is not None:
        assignee = db.get(User, body.user_id)
        if not assignee or not assignee.is_active or assignee.is_vendor:
            raise HTTPException(400, "Assignee must be an active staff user")
    o.assigned_user_id = body.user_id
    add_event(db, o, "ASSIGNED", actor=user,
              note=f"Assigned to {assignee.full_name}" if assignee else "Unassigned")
    db.commit()
    return serialize(o)


# ---------------------------------------------------------------------------
# Customers & confirmations
# ---------------------------------------------------------------------------

@customers_router.get("")
def list_customers(user: User = Depends(require_staff), db: Session = Depends(get_db),
                   vendor_id: int = 0, q: str = ""):
    query = (db.query(Customer, Vendor).join(Vendor, Vendor.id == Customer.vendor_id))
    if vendor_id:
        query = query.filter(Customer.vendor_id == vendor_id)
    if q:
        like = f"%{q}%"
        query = query.filter((Customer.name.ilike(like)) | (Customer.phone.ilike(like)))
    rows = query.order_by(Customer.id.desc()).limit(300).all()
    return [serialize(c, vendor_name=v.name) for c, v in rows]


class CustomerIn(BaseModel):
    vendor_id: int
    name: str
    phone: str
    alt_phone: str = ""
    email: str = ""
    notes: str = ""


@customers_router.post("")
def create_customer(body: CustomerIn, user: User = Depends(require_perm("orders.manage")), db: Session = Depends(get_db)):
    if not db.get(Vendor, body.vendor_id):
        raise HTTPException(404, "Vendor not found")
    c = upsert_customer(db, body.vendor_id, body.name, body.phone, body.alt_phone)
    c.email = body.email
    c.notes = body.notes
    db.commit()
    return serialize(c)


@confirmations_router.get("/queue")
def confirmation_queue(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    rows = (db.query(Order, Customer, CustomerConfirmation, Vendor)
            .join(Customer, Customer.id == Order.customer_id)
            .outerjoin(CustomerConfirmation, CustomerConfirmation.order_id == Order.id)
            .join(Vendor, Vendor.id == Order.vendor_id)
            .filter(Order.status.in_(["CONFIRMED", "PENDING_CUSTOMER_CONFIRMATION", "PROCESSING"]))
            .order_by(Order.id.desc()).limit(100).all())
    return [serialize(o, customer_name=c.name, customer_phone=c.phone, vendor_name=v.name,
                      confirmation_status=(cf.status if cf else "NOT_STARTED"),
                      attempts=(cf.attempts_count if cf else 0),
                      follow_up_at=(cf.next_action_at.isoformat() if cf and cf.next_action_at else None),
                      follow_up_due=bool(cf and cf.next_action_at and cf.next_action_at <= utcnow()),
                      last_note=(cf.outcome_note if cf else ""),
                      items_total=o.items_total_kobo, cod=o.cod_amount_kobo)
            for o, c, cf, v in rows]


@confirmations_router.post("/{order_id}/attempt")
def record_attempt(order_id: int, body: AttemptIn, user: User = Depends(require_perm("confirmations.manage")), db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(404, "Order not found")
    if body.outcome not in ATTEMPT_OUTCOMES:
        raise HTTPException(400, f"outcome must be one of {', '.join(ATTEMPT_OUTCOMES)}")
    if o.status not in ATTEMPT_ALLOWED_ORDER_STATUSES:
        raise HTTPException(400, f"Order is {o.status}; customer confirmation no longer applies")
    cf = db.query(CustomerConfirmation).filter(CustomerConfirmation.order_id == order_id).first()
    if not cf:
        cf = CustomerConfirmation(order_id=order_id, agent_user_id=user.id)
        db.add(cf)
        db.flush()
    cf.attempts_count += 1
    cf.agent_user_id = user.id
    attempt_no = cf.attempts_count
    cf.status = body.outcome if body.outcome in (
        "CALL_ATTEMPTED", "NO_ANSWER", "INVALID_PHONE_NUMBER", "PHONE_SWITCHED_OFF", "CUSTOMER_AWAY") else cf.status
    if body.outcome in ("NO_ANSWER", "PHONE_SWITCHED_OFF", "CUSTOMER_AWAY"):
        # Park the order as "pending customer confirmation" until the next follow-up.
        when = None
        if body.follow_up_date:
            try:
                when = datetime.strptime(body.follow_up_date[:10], "%Y-%m-%d").replace(hour=8)
            except ValueError:
                raise HTTPException(400, "follow_up_date must be YYYY-MM-DD")
        if body.outcome == "CUSTOMER_AWAY" and not when:
            raise HTTPException(400, "Pick the date the customer will be back / ready to receive")
        if when and when < utcnow() - timedelta(days=1):
            raise HTTPException(400, "Follow-up date is in the past")
        cf.next_action_at = when or (utcnow() + timedelta(hours=4 if body.outcome == "NO_ANSWER" else 6))
        if o.status in ("CONFIRMED", "PROCESSING"):
            label = {"NO_ANSWER": "Customer not picking calls", "PHONE_SWITCHED_OFF": "Customer phone switched off",
                     "CUSTOMER_AWAY": "Customer not around"}[body.outcome]
            add_event(db, o, "CONFIRMATION", from_status=o.status, to_status="PENDING_CUSTOMER_CONFIRMATION",
                      actor=user, note=f"{label}; follow up {cf.next_action_at:%d %b}" + (f" - {body.note}" if body.note else ""))
            o.status = "PENDING_CUSTOMER_CONFIRMATION"
    elif body.outcome in ("CUSTOMER_CONFIRMED", "CUSTOMER_REJECTED"):
        cf.next_action_at = None
    if body.outcome == "CUSTOMER_CONFIRMED":
        cf.status = "CUSTOMER_CONFIRMED"
        cf.confirmed_at = utcnow()
        if o.status in ("CONFIRMED", "PENDING_CUSTOMER_CONFIRMATION"):
            add_event(db, o, "CONFIRMATION", from_status=o.status, to_status="CUSTOMER_CONFIRMED", actor=user, note=body.note)
            o.status = "CUSTOMER_CONFIRMED"
    elif body.outcome == "CUSTOMER_REJECTED":
        cf.status = "CUSTOMER_REJECTED"
        if o.status != "CANCELLED":
            from_status = o.status
            o.status = "CANCELLED"
            o.cancelled_at = utcnow()
            o.cancel_reason = f"Customer rejected: {body.note}"
            release_reservations(db, o.id, user)
            add_event(db, o, "STATUS_CHANGE", from_status, "CANCELLED", user, o.cancel_reason)
    elif body.outcome == "CUSTOMER_REQUESTED_RESCHEDULE":
        cf.status = "CUSTOMER_REQUESTED_RESCHEDULE"
        cf.next_action_at = utcnow() + timedelta(days=1)
        if o.status == "CONFIRMED":
            o.status = "PENDING_CUSTOMER_CONFIRMATION"
    elif body.outcome == "ADDRESS_NEEDS_CORRECTION":
        cf.status = "ADDRESS_NEEDS_CORRECTION"
    db.add(ConfirmationAttempt(confirmation_id=cf.id, attempt_no=attempt_no, outcome=body.outcome,
                               note=body.note, by_user_id=user.id))
    cf.outcome_note = body.note
    db.commit()
    return serialize(cf)
