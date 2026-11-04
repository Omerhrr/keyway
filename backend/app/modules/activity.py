"""Notifications + audit trail endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.db import get_db, utcnow
from app.core.deps import require_staff, get_current_user
from app.core.serialize import serialize_list
from app.modules.identity_models import User
from app.modules.activity_models import AuditLog, Notification

router = APIRouter(prefix="/api", tags=["activity"])


@router.get("/notifications")
def notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db), unread_only: bool = False):
    q = db.query(Notification)
    if unread_only:
        q = q.filter(Notification.status == "UNREAD")
    rows = q.order_by(Notification.id.desc()).limit(50).all()
    return serialize_list(rows)


@router.post("/notifications/read-all")
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.status == "UNREAD").update({"status": "READ", "read_at": utcnow()})
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
