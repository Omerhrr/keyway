from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.db import get_db, utcnow
from app.core.deps import require_staff, require_perm
from app.core.serialize import serialize, serialize_list
from app.core.audit import audit
from app.modules.identity_models import User
from app.modules.charges_models import ChargeRule, Charge
from app.modules.vendors_models import Vendor
from app.modules.orders_models import Order

router = APIRouter(prefix="/api/charges", tags=["charges"])

CHARGE_TYPES = ["ORDER_PROCESSING", "LOCAL_DELIVERY", "INTERSTATE_DISPATCH", "WAYBILL",
                "STORAGE", "COD_HANDLING", "RETURN_HANDLING", "SPECIAL_HANDLING", "OTHER"]


class RuleIn(BaseModel):
    name: str
    charge_type: str
    scope: str = "GLOBAL"
    vendor_id: int | None = None
    zone_id: int | None = None
    basis: str = "FIXED"
    amount_kobo: int = 0
    percent: float = 0.0
    effective_from: str | None = None
    effective_to: str | None = None
    is_active: bool = True
    requires_approval: bool = False


class ApplyIn(BaseModel):
    order_id: int
    charge_type: str = "OTHER"
    amount_kobo: int = 0
    reason: str = ""


def find_rule(db: Session, vendor_id: int, charge_type: str) -> ChargeRule | None:
    """Vendor-specific overrides take precedence over the default schedule."""
    now = utcnow()
    rules = (db.query(ChargeRule)
             .filter(ChargeRule.charge_type == charge_type, ChargeRule.is_active.is_(True),
                     ChargeRule.effective_from <= now)
             .order_by(ChargeRule.id.desc()).all())
    vendor_rule = next((r for r in rules if r.scope == "VENDOR" and r.vendor_id == vendor_id
                        and (not r.effective_to or r.effective_to >= now)), None)
    if vendor_rule:
        return vendor_rule
    return next((r for r in rules if r.scope == "GLOBAL" and (not r.effective_to or r.effective_to >= now)), None)


def apply_charge(db: Session, *, vendor_id: int, order_id: int | None, charge_type: str,
                 amount_kobo: int | None = None, reason: str = "", actor=None, commit: bool = True) -> Charge:
    """Apply a charge to an order, recording the pricing rule + version used (PRD rule)."""
    rule = find_rule(db, vendor_id, charge_type)
    amount = amount_kobo if amount_kobo else (rule.amount_kobo if rule else 0)
    if amount <= 0:
        raise ValueError(f"No active pricing rule for {charge_type} and no amount given")
    ch = Charge(vendor_id=vendor_id, order_id=order_id, charge_type=charge_type,
                basis=rule.basis if rule else "FIXED", amount_kobo=amount,
                rule_id=rule.id if rule else None, rule_version=rule.version if rule else None,
                reason=reason or f"{charge_type} charge", status="APPLIED",
                applied_by_user_id=actor.id if actor else None)
    db.add(ch)
    db.flush()
    if commit:
        db.commit()
    return ch


@router.get("/rules")
def list_rules(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    rules = db.query(ChargeRule).order_by(ChargeRule.charge_type, ChargeRule.scope).all()
    vendors = {v.id: v.name for v in db.query(Vendor).all()}
    return [serialize(r, vendor_name=vendors.get(r.vendor_id)) for r in rules]


@router.post("/rules")
def create_rule(body: RuleIn, user: User = Depends(require_perm("charges.manage")), db: Session = Depends(get_db)):
    if body.charge_type not in CHARGE_TYPES:
        raise HTTPException(400, "Unknown charge type")
    if body.scope == "VENDOR" and not body.vendor_id:
        raise HTTPException(400, "Vendor scope requires a vendor_id")
    r = ChargeRule(version=1, created_by_user_id=user.id, **body.model_dump())
    db.add(r)
    db.commit()
    audit(db, user, "create", "charge_rule", r.id, f"Created pricing rule {r.name}")
    db.commit()
    return serialize(r)


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: int, body: RuleIn, user: User = Depends(require_perm("charges.manage")), db: Session = Depends(get_db)):
    """Editing a rule creates a new version; charges already applied are never silently changed."""
    r = db.get(ChargeRule, rule_id)
    if not r:
        raise HTTPException(404, "Rule not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
    r.version += 1
    db.commit()
    audit(db, user, "update", "charge_rule", r.id, f"Pricing rule {r.name} updated to v{r.version}")
    db.commit()
    return serialize(r)


@router.get("/order/{order_id}")
def order_charges(order_id: int, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return serialize_list(db.query(Charge).filter(Charge.order_id == order_id).order_by(Charge.id).all())


@router.post("/apply")
def apply_manual(body: ApplyIn, user: User = Depends(require_perm("charges.manage")), db: Session = Depends(get_db)):
    o = db.get(Order, body.order_id)
    if not o:
        raise HTTPException(404, "Order not found")
    if not body.reason.strip():
        raise HTTPException(400, "Every charge needs a recorded reason")
    try:
        ch = apply_charge(db, vendor_id=o.vendor_id, order_id=o.id, charge_type=body.charge_type,
                          amount_kobo=body.amount_kobo, reason=body.reason, actor=user)
    except ValueError as e:
        raise HTTPException(400, str(e))
    audit(db, user, "apply", "charge", ch.id, f"Charge {body.charge_type} applied to {o.reference}")
    db.commit()
    return serialize(ch)
