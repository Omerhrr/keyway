"""Notifications, notification rules + audit trail endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.db import get_db, utcnow
from app.core.deps import require_staff, get_current_user, require_perm
from app.core.serialize import serialize, serialize_list
from app.modules.identity_models import User, Role
from app.modules.activity_models import AuditLog, Notification, NotificationRule
from app.modules import notify as notify_mod

router = APIRouter(prefix="/api", tags=["activity"])


def _audit(db, *args, **kwargs):
    # lazy import: app.core.audit imports this module's models (circular at module load)
    from app.core.audit import audit as audit_fn
    audit_fn(db, *args, **kwargs)


def _visible_notifications(q, user: User):
    """Vendor portal users only see their vendor's rows; staff see staff-wide +
    personally-addressed rows. (PRD: no vendor can retrieve another vendor's records.)"""
    if user.is_vendor:
        return q.filter(Notification.vendor_id == (user.vendor_id or -1))
    return q.filter((Notification.user_id == None) | (Notification.user_id == user.id))  # noqa: E711


@router.get("/notifications")
def notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db),
                  unread_only: bool = False, limit: int = 50):
    q = _visible_notifications(db.query(Notification), user)
    if unread_only:
        q = q.filter(Notification.status == "UNREAD")
    rows = q.order_by(Notification.id.desc()).limit(min(limit, 200)).all()
    return serialize_list(rows)


@router.get("/notifications/unread-count")
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = _visible_notifications(db.query(Notification), user)
    return {"count": q.filter(Notification.status == "UNREAD").count()}


@router.post("/notifications/read-all")
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = _visible_notifications(db.query(Notification), user)
    q.filter(Notification.status == "UNREAD").update({"status": "READ", "read_at": utcnow()},
                                                     synchronize_session=False)
    db.commit()
    return {"ok": True}


@router.post("/notifications/{notification_id}/read")
def read_one(notification_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = _visible_notifications(db.query(Notification), user)
    n = q.filter(Notification.id == notification_id).first()
    if not n:
        raise HTTPException(404, "Notification not found")
    if n.status == "UNREAD":
        n.status = "READ"
        n.read_at = utcnow()
        db.commit()
    return serialize(n)


@router.post("/notifications/{notification_id}/retry")
def retry_one(notification_id: int, user: User = Depends(require_perm("settings.manage")),
              db: Session = Depends(get_db)):
    """PRD: failed notifications must be retryable."""
    n = db.get(Notification, notification_id)
    if not n:
        raise HTTPException(404, "Notification not found")
    ok = notify_mod.retry_notification(db, n)
    if not ok:
        raise HTTPException(400, f"Only FAILED notifications can be retried (status: {n.status})")
    db.commit()
    _audit(db, user, "retry", "notification", n.id, f"Retry delivery of notification #{n.id} ({n.channel})")
    db.commit()
    return serialize(n)


# ---- automation checks (low stock, unconfirmed orders) ----------------------

@router.post("/notifications/run-checks")
def run_checks(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    created = notify_mod.run_automation_checks(db)
    return {"created": created, "total": sum(created.values())}


# ---- notification rules (Settings -> Notifications) -------------------------

class RuleIn(BaseModel):
    name: str
    event_type: str
    enabled: bool = True
    target_scope: str = "ALL_STAFF"  # ALL_STAFF | ROLE | USER
    role_name: str = ""
    user_id: int | None = None
    channel: str = "IN_APP"  # IN_APP | WHATSAPP | EMAIL | SMS


def _validate_rule(db: Session, body: RuleIn):
    if body.event_type not in notify_mod.EVENT_TYPES:
        raise HTTPException(400, f"Unknown event type. Valid: {', '.join(notify_mod.EVENT_TYPES)}")
    if body.target_scope not in ("ALL_STAFF", "ROLE", "USER"):
        raise HTTPException(400, "target_scope must be ALL_STAFF, ROLE or USER")
    if body.channel not in ("IN_APP", "WHATSAPP", "EMAIL", "SMS"):
        raise HTTPException(400, "channel must be IN_APP, WHATSAPP, EMAIL or SMS")
    if body.target_scope == "ROLE" and not db.query(Role).filter(Role.name == body.role_name).first():
        raise HTTPException(400, f"Role '{body.role_name}' does not exist")
    if body.target_scope == "USER" and not db.query(User).filter(User.id == body.user_id).first():
        raise HTTPException(404, "Target user not found")


@router.get("/notification-rules")
def list_rules(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    rules = db.query(NotificationRule).order_by(NotificationRule.id).all()
    return {"rules": serialize_list(rules), "events": notify_mod.EVENT_CATALOG,
            "channels": ["IN_APP", "WHATSAPP", "EMAIL", "SMS"]}


@router.post("/notification-rules")
def create_rule(body: RuleIn, user: User = Depends(require_perm("settings.manage")),
                db: Session = Depends(get_db)):
    if db.query(NotificationRule).filter(NotificationRule.name == body.name).first():
        raise HTTPException(400, "A rule with this name already exists")
    _validate_rule(db, body)
    r = NotificationRule(**body.model_dump())
    db.add(r)
    db.commit()
    _audit(db, user, "create", "notification_rule", r.id,
          f"Notification rule '{r.name}' ({r.event_type} -> {r.target_scope}/{r.channel})")
    db.commit()
    return serialize(r)


@router.patch("/notification-rules/{rule_id}")
def update_rule(rule_id: int, body: dict, user: User = Depends(require_perm("settings.manage")),
                db: Session = Depends(get_db)):
    r = db.get(NotificationRule, rule_id)
    if not r:
        raise HTTPException(404, "Rule not found")
    changes = {}
    for f in ("enabled", "target_scope", "role_name", "user_id", "channel", "name", "event_type"):
        if f in body:
            setattr(r, f, body[f])
            changes[f] = body[f]
    _validate_rule(db, RuleIn(name=r.name, event_type=r.event_type, target_scope=r.target_scope,
                              role_name=r.role_name, user_id=r.user_id, channel=r.channel,
                              enabled=r.enabled))
    db.commit()
    _audit(db, user, "update", "notification_rule", r.id, f"Notification rule '{r.name}' updated",
          data=changes)
    db.commit()
    return serialize(r)


@router.delete("/notification-rules/{rule_id}")
def delete_rule(rule_id: int, user: User = Depends(require_perm("settings.manage")),
                db: Session = Depends(get_db)):
    r = db.get(NotificationRule, rule_id)
    if not r:
        raise HTTPException(404, "Rule not found")
    db.delete(r)
    db.commit()
    _audit(db, user, "delete", "notification_rule", r.id, f"Notification rule '{r.name}' deleted")
    db.commit()
    return {"ok": True}


@router.get("/audit")
def audit_logs(user: User = Depends(require_staff), db: Session = Depends(get_db),
               entity_type: str = "", limit: int = 200):
    q = db.query(AuditLog)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    rows = q.order_by(AuditLog.id.desc()).limit(min(limit, 500)).all()
    return serialize_list(rows)
