from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.db import get_db, utcnow
from app.core.deps import require_staff, require_perm, get_current_user
from app.core.serialize import serialize, serialize_list
from app.core.audit import audit
from app.core.ids import next_ref
from app.modules.identity_models import User
from app.modules.orders_models import Order, Customer
from app.modules.delivery_models import DeliveryZone, Rider, Carrier, Waybill, Delivery, DeliveryAssignment
from app.modules.orders import add_event, TRANSITIONS
from app.modules.inventory import consume_reservations
from app.modules.notify import notify
from app.modules.vendors_models import Vendor

router = APIRouter(prefix="/api/dispatch", tags=["dispatch"])

DELIVERY_TRANSITIONS = {
    "PENDING_ASSIGNMENT": ["ASSIGNED", "DISPATCHED", "FAILED"],
    "ASSIGNED": ["PICKED_UP", "DISPATCHED", "OUT_FOR_DELIVERY", "DELIVERED", "FAILED"],
    "PICKED_UP": ["DISPATCHED", "OUT_FOR_DELIVERY", "DELIVERED", "FAILED"],
    "DISPATCHED": ["IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED", "FAILED"],
    "IN_TRANSIT": ["OUT_FOR_DELIVERY", "DELIVERED", "FAILED", "RETURNING"],
    "OUT_FOR_DELIVERY": ["DELIVERED", "FAILED", "RETURNING"],
    "DELIVERED": [],
    "FAILED": ["RETURNING", "RETURNED", "PENDING_ASSIGNMENT"],
    "RETURNING": ["RETURNED"],
    "RETURNED": [],
}


DELIVERY_MODES = ("IN_HOUSE_RIDER", "LOCAL_3P", "INTERSTATE", "WAYBILL")


class DispatchIn(BaseModel):
    order_id: int
    mode: str = "IN_HOUSE_RIDER"
    rider_id: int | None = None
    carrier_id: int | None = None
    zone_id: int | None = None
    waybill_id: int | None = None
    fee_kobo: int = 0


class DeliveryStatusIn(BaseModel):
    to_status: str
    failure_reason: str = ""
    proof_ref: str = ""
    note: str = ""


class RiderIn(BaseModel):
    full_name: str
    phone: str = ""
    vehicle: str = ""
    zone_id: int | None = None
    status: str = "ACTIVE"
    user_id: int | None = None
    login_email: str = ""      # optional: give the rider a sign-in to see their own deliveries
    login_password: str = ""


class CarrierIn(BaseModel):
    name: str
    kind: str = "INTERSTATE"
    contact_phone: str = ""
    tracking_url: str = ""


class ZoneIn(BaseModel):
    name: str
    state: str = ""
    cities: list[str] = []
    base_fee_kobo: int = 0


class WaybillIn(BaseModel):
    carrier_id: int | None = None
    destination_state: str = ""
    total_parcels: int = 0
    note: str = ""


@router.get("/deliveries")
def list_deliveries(user: User = Depends(require_staff), db: Session = Depends(get_db),
                    status: str = "", mode: str = ""):
    query = (db.query(Delivery, Order, Customer, Vendor)
             .join(Order, Order.id == Delivery.order_id)
             .join(Customer, Customer.id == Order.customer_id)
             .join(Vendor, Vendor.id == Order.vendor_id))
    if status:
        query = query.filter(Delivery.status == status)
    if mode:
        query = query.filter(Delivery.mode == mode)
    rows = query.order_by(Delivery.id.desc()).limit(200).all()
    riders = {r.id: r.full_name for r in db.query(Rider).all()}
    out = []
    for d, o, c, v in rows:
        out.append(serialize(d, order_reference=o.reference, order_status=o.status,
                             customer_name=c.name, customer_phone=c.phone,
                             delivery_city=o.delivery_city, delivery_state=o.delivery_state,
                             vendor_name=v.name, cod_expected=o.cod_amount_kobo,
                             rider_name=riders.get(d.rider_id)))
    return out


@router.post("/deliveries")
def create_dispatch(body: DispatchIn, user: User = Depends(require_perm("dispatch.manage")), db: Session = Depends(get_db)):
    o = db.get(Order, body.order_id)
    if not o:
        raise HTTPException(404, "Order not found")
    if o.status not in ("READY_FOR_DISPATCH",):
        raise HTTPException(400, f"Order must be READY_FOR_DISPATCH first (currently {o.status})")
    if body.mode not in DELIVERY_MODES:
        raise HTTPException(400, f"mode must be one of {', '.join(DELIVERY_MODES)}")
    if body.fee_kobo < 0:
        raise HTTPException(400, "Delivery fee cannot be negative")
    if body.rider_id:
        rider = db.get(Rider, body.rider_id)
        if not rider or rider.status != "ACTIVE":
            raise HTTPException(400, "Rider not found or not active")
    if body.carrier_id and not db.get(Carrier, body.carrier_id):
        raise HTTPException(400, "Carrier not found")
    if body.waybill_id and not db.get(Waybill, body.waybill_id):
        raise HTTPException(400, "Waybill not found")
    if body.zone_id and not db.get(DeliveryZone, body.zone_id):
        raise HTTPException(400, "Delivery zone not found")
    zone = db.get(DeliveryZone, body.zone_id) if body.zone_id else None
    fee = body.fee_kobo or (zone.base_fee_kobo if zone else 0)
    d = Delivery(order_id=o.id, mode=body.mode, zone_id=zone.id if zone else None,
                 rider_id=body.rider_id, carrier_id=body.carrier_id, waybill_id=body.waybill_id,
                 fee_kobo=fee, status="PENDING_ASSIGNMENT")
    db.add(d)
    db.flush()
    if body.rider_id:
        d.status = "ASSIGNED"
        db.add(DeliveryAssignment(delivery_id=d.id, rider_id=body.rider_id,
                                  assigned_by_user_id=user.id, status="ASSIGNED"))
    # Apply the delivery charge through the charge engine (recorded, never silent)
    from app.modules.charges import apply_charge
    charge_type = "LOCAL_DELIVERY" if body.mode in ("IN_HOUSE_RIDER", "LOCAL_3P") else "INTERSTATE_DISPATCH"
    charge_note = ""
    try:
        apply_charge(db, vendor_id=o.vendor_id, order_id=o.id, charge_type=charge_type,
                     amount_kobo=fee, reason=f"Delivery fee for {o.reference}", actor=user, commit=False)
    except ValueError as ex:
        # No fee and no pricing rule: dispatch continues but the gap is recorded, not hidden.
        charge_note = " (no delivery charge recorded: no fee given and no pricing rule found)"
    o.delivery_fee_kobo = fee
    if o.payment_method == "COD":
        o.cod_amount_kobo = o.items_total_kobo + fee
    from_status = o.status
    o.status = "DISPATCHED"
    d.dispatch_at = utcnow()
    add_event(db, o, "DISPATCH", from_status, "DISPATCHED", user,
              f"Dispatched via {body.mode.replace('_', ' ').title()}, delivery fee ₦{fee / 100:,.0f}{charge_note}")
    notify(db, event_type="ORDER_DISPATCHED", title=f"Order {o.reference} dispatched",
           vendor_id=o.vendor_id, entity_type="order", entity_id=o.id)
    audit(db, user, "dispatch", "order", o.id, f"Order {o.reference} dispatched via {body.mode}")
    db.commit()
    return serialize(d)


@router.post("/deliveries/{delivery_id}/status")
def update_delivery_status(delivery_id: int, body: DeliveryStatusIn, user: User = Depends(require_perm("dispatch.manage")), db: Session = Depends(get_db)):
    d = db.get(Delivery, delivery_id)
    if not d:
        raise HTTPException(404, "Delivery not found")
    to = body.to_status
    if to not in DELIVERY_TRANSITIONS.get(d.status, []):
        raise HTTPException(400, f"Cannot move delivery from {d.status} to {to}")
    o = db.get(Order, d.order_id)
    if o.status in ("CANCELLED", "DELIVERED", "RETURNED_TO_WAREHOUSE") and to != "RETURNED":
        raise HTTPException(400, f"Order {o.reference} is {o.status}; its delivery can no longer change")
    if to == "FAILED" and not body.failure_reason.strip():
        raise HTTPException(400, "A failure reason is required")
    prev = o.status
    d.status = to
    if to == "DELIVERED":
        d.delivered_at = utcnow()
        d.proof_ref = body.proof_ref or d.proof_ref
        o.status = "DELIVERED"
        o.delivered_at = utcnow()
        consume_reservations(db, o.id, user)
        add_event(db, o, "STATUS_CHANGE", prev, "DELIVERED", user, body.note or "Delivered")
        notify(db, event_type="ORDER_DELIVERED", title=f"Order {o.reference} delivered",
               vendor_id=o.vendor_id, entity_type="order", entity_id=o.id)
        # Auto-create pending COD collection record (actual amount recorded on confirmation)
        from app.modules.cod import ensure_cod_pending
        ensure_cod_pending(db, o, delivery_id=d.id, rider_id=d.rider_id)
    elif to == "FAILED":
        d.failure_reason = body.failure_reason or "Unspecified"
        o.status = "DELIVERY_FAILED"
        add_event(db, o, "STATUS_CHANGE", prev, "DELIVERY_FAILED", user, d.failure_reason)
        notify(db, event_type="DELIVERY_FAILED", title=f"Order {o.reference} delivery failed",
               body=d.failure_reason, vendor_id=o.vendor_id, entity_type="order", entity_id=o.id)
    elif to == "RETURNED":
        o.status = "RETURNED_TO_WAREHOUSE"
        from app.modules.inventory import restock_return
        restock_return(db, o.id, user)
        add_event(db, o, "STATUS_CHANGE", prev, "RETURNED_TO_WAREHOUSE", user, "Returned to warehouse")
    elif to == "RETURNING":
        o.status = "RETURN_IN_TRANSIT"
        add_event(db, o, "STATUS_CHANGE", prev, "RETURN_IN_TRANSIT", user, body.note)
    elif to == "PENDING_ASSIGNMENT":
        # Retry after a failed attempt: the order is back out for delivery.
        o.status = "DISPATCHED"
        d.failure_reason = ""
        add_event(db, o, "STATUS_CHANGE", prev, "DISPATCHED", user, body.note or "Re-attempt scheduled")
    else:
        o.status = "IN_TRANSIT" if to in ("DISPATCHED", "IN_TRANSIT", "OUT_FOR_DELIVERY") else o.status
        add_event(db, o, "STATUS_CHANGE", prev, o.status, user, body.note or f"Delivery -> {to}")
    db.commit()
    audit(db, user, "delivery_status", "delivery", d.id, f"Delivery -> {to}")
    db.commit()
    return serialize(d)


@router.get("/riders")
def list_riders(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    riders = db.query(Rider).order_by(Rider.full_name).all()
    zones = {z.id: z.name for z in db.query(DeliveryZone).all()}
    return [serialize(r, zone_name=zones.get(r.zone_id)) for r in riders]


@router.post("/riders")
def create_rider(body: RiderIn, user: User = Depends(require_perm("settings.manage")), db: Session = Depends(get_db)):
    if not body.full_name.strip():
        raise HTTPException(400, "Rider name is required")
    if body.zone_id and not db.get(DeliveryZone, body.zone_id):
        raise HTTPException(400, "Delivery zone not found")
    if body.user_id and not db.get(User, body.user_id):
        raise HTTPException(400, "Linked user not found")
    data = body.model_dump()
    login_email, login_password = data.pop("login_email").strip().lower(), data.pop("login_password")
    if login_email or login_password:
        from app.modules.identity import _check_password, _clean_email
        from app.modules.identity_models import Role
        from app.core.security import hash_password
        if not (login_email and login_password):
            raise HTTPException(400, "Give the rider both a sign-in email and a password, or neither")
        login_email = _clean_email(login_email)
        _check_password(login_password)
        if db.query(User).filter(User.email == login_email).first():
            raise HTTPException(400, "That email already has an account")
        role = db.query(Role).filter(Role.name == "Rider").first()
        u = User(email=login_email, password_hash=hash_password(login_password), full_name=body.full_name,
                 phone=body.phone, role_id=role.id if role else None)
        db.add(u)
        db.flush()
        data["user_id"] = u.id
    r = Rider(**data)
    db.add(r)
    db.commit()
    return serialize(r)


@router.get("/carriers")
def list_carriers(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return serialize_list(db.query(Carrier).order_by(Carrier.name).all())


@router.post("/carriers")
def create_carrier(body: CarrierIn, user: User = Depends(require_perm("settings.manage")), db: Session = Depends(get_db)):
    if not body.name.strip():
        raise HTTPException(400, "Carrier name is required")
    c = Carrier(**body.model_dump())
    db.add(c)
    db.commit()
    return serialize(c)


@router.get("/zones")
def list_zones(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return serialize_list(db.query(DeliveryZone).order_by(DeliveryZone.name).all())


@router.post("/zones")
def create_zone(body: ZoneIn, user: User = Depends(require_perm("settings.manage")), db: Session = Depends(get_db)):
    if not body.name.strip():
        raise HTTPException(400, "Zone name is required")
    if body.base_fee_kobo < 0:
        raise HTTPException(400, "Base fee cannot be negative")
    z = DeliveryZone(**body.model_dump())
    db.add(z)
    db.commit()
    return serialize(z)


@router.get("/waybills")
def list_waybills(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return serialize_list(db.query(Waybill).order_by(Waybill.id.desc()).limit(100).all())


@router.post("/waybills")
def create_waybill(body: WaybillIn, user: User = Depends(require_perm("dispatch.manage")), db: Session = Depends(get_db)):
    if body.carrier_id and not db.get(Carrier, body.carrier_id):
        raise HTTPException(400, "Carrier not found")
    if body.total_parcels < 0:
        raise HTTPException(400, "Parcel count cannot be negative")
    w = Waybill(waybill_no="PENDING", **body.model_dump())
    db.add(w)
    db.flush()
    w.waybill_no = f"WB-{500 + w.id}"
    db.commit()
    return serialize(w)


@router.get("/assignments/me")
def my_assignments(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Rider mobile view: only assigned deliveries (PRD security rule)."""
    rider = db.query(Rider).filter(Rider.user_id == user.id).first()
    if not rider:
        return []
    rows = (db.query(Delivery, Order, Customer)
            .join(Order, Order.id == Delivery.order_id)
            .join(Customer, Customer.id == Order.customer_id)
            .filter(Delivery.rider_id == rider.id,
                    Delivery.status.in_(["ASSIGNED", "PICKED_UP", "DISPATCHED", "IN_TRANSIT", "OUT_FOR_DELIVERY"]))
            .order_by(Delivery.id.desc()).all())
    return [serialize(d, order_reference=o.reference, customer_name=c.name,
                      customer_phone=c.phone, address=", ".join(x.strip() for x in (o.delivery_street, o.delivery_area, o.delivery_city) if x and x.strip()),
                      cod_expected=o.cod_amount_kobo if o.payment_method == "COD" else 0)
            for d, o, c in rows]


class RiderOutcomeIn(BaseModel):
    to_status: str
    failure_reason: str = ""
    proof_ref: str = ""
    note: str = ""


@router.post("/assignments/{delivery_id}/status")
def rider_update_status(delivery_id: int, body: RiderOutcomeIn, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """A rider reports the result of their OWN delivery from their phone."""
    rider = db.query(Rider).filter(Rider.user_id == user.id).first()
    d = db.get(Delivery, delivery_id)
    if not rider or not d or d.rider_id != rider.id:
        raise HTTPException(404, "Delivery not found")
    if body.to_status not in ("IN_TRANSIT", "DELIVERED", "FAILED"):
        raise HTTPException(400, "A rider can mark a delivery as on the way, delivered or failed")
    return update_delivery_status(delivery_id, DeliveryStatusIn(**body.model_dump()), user, db)
