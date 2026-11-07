from datetime import datetime, timedelta
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


class RulePatch(BaseModel):
    name: str | None = None
    charge_type: str | None = None
    scope: str | None = None
    vendor_id: int | None = None
    zone_id: int | None = None
    basis: str | None = None
    amount_kobo: int | None = None
    percent: float | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    is_active: bool | None = None
    requires_approval: bool | None = None


BASES = ("FIXED", "PERCENT", "PER_QTY")
SCOPES = ("GLOBAL", "VENDOR")


def _parse_dt(v, field):
    if v in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(400, f"{field} must be an ISO date, e.g. 2026-11-07")


def _validate_rule(d: dict, db: Session):
    if "charge_type" in d and d["charge_type"] not in CHARGE_TYPES:
        raise HTTPException(400, "Unknown charge type")
    if "scope" in d and d["scope"] not in SCOPES:
        raise HTTPException(400, f"scope must be one of {', '.join(SCOPES)}")
    if "basis" in d and d["basis"] not in BASES:
        raise HTTPException(400, f"basis must be one of {', '.join(BASES)}")
    if d.get("amount_kobo") is not None and d["amount_kobo"] < 0:
        raise HTTPException(400, "Amount cannot be negative")
    if d.get("percent") is not None and not (0 <= d["percent"] <= 100):
        raise HTTPException(400, "Percent must be between 0 and 100")
    if d.get("vendor_id") and not db.get(Vendor, d["vendor_id"]):
        raise HTTPException(400, "Unknown vendor")


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
    if amount_kobo:
        amount = amount_kobo
    elif rule and rule.basis == "PERCENT" and order_id:
        o = db.get(Order, order_id)
        amount = int(round((o.items_total_kobo if o else 0) * (rule.percent or 0) / 100))
    elif rule and rule.basis == "PER_QTY" and order_id:
        from app.modules.orders_models import OrderItem
        qty = sum(i.qty for i in db.query(OrderItem).filter(OrderItem.order_id == order_id).all())
        amount = rule.amount_kobo * qty
    else:
        amount = rule.amount_kobo if rule else 0
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
    data = body.model_dump()
    _validate_rule(data, db)
    if not body.name.strip():
        raise HTTPException(400, "A rule name is required")
    if body.scope == "VENDOR" and not body.vendor_id:
        raise HTTPException(400, "Vendor scope requires a vendor_id")
    data["effective_from"] = _parse_dt(data["effective_from"], "effective_from") or utcnow()
    data["effective_to"] = _parse_dt(data["effective_to"], "effective_to")
    r = ChargeRule(version=1, created_by_user_id=user.id, **data)
    db.add(r)
    db.commit()
    audit(db, user, "create", "charge_rule", r.id, f"Created pricing rule {r.name}")
    db.commit()
    return serialize(r)


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: int, body: RulePatch, user: User = Depends(require_perm("charges.manage")), db: Session = Depends(get_db)):
    """Editing a rule creates a new version; charges already applied are never silently changed."""
    r = db.get(ChargeRule, rule_id)
    if not r:
        raise HTTPException(404, "Rule not found")
    data = body.model_dump(exclude_unset=True)
    _validate_rule(data, db)
    if "effective_from" in data:
        data["effective_from"] = _parse_dt(data["effective_from"], "effective_from") or utcnow()
    if "effective_to" in data:
        data["effective_to"] = _parse_dt(data["effective_to"], "effective_to")
    for k, v in data.items():
        setattr(r, k, v)
    if r.scope == "VENDOR" and not r.vendor_id:
        db.rollback()
        raise HTTPException(400, "Vendor scope requires a vendor_id")
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
    if body.charge_type not in CHARGE_TYPES:
        raise HTTPException(400, "Unknown charge type")
    if body.amount_kobo < 0:
        raise HTTPException(400, "Amount cannot be negative")
    try:
        ch = apply_charge(db, vendor_id=o.vendor_id, order_id=o.id, charge_type=body.charge_type,
                          amount_kobo=body.amount_kobo, reason=body.reason, actor=user)
    except ValueError as e:
        raise HTTPException(400, str(e))
    audit(db, user, "apply", "charge", ch.id, f"Charge {body.charge_type} applied to {o.reference}")
    db.commit()
    return serialize(ch)
