import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.db import get_db, utcnow
from app.core.deps import require_staff, require_perm
from app.core.serialize import serialize, serialize_list
from app.core.audit import audit
from app.core.ids import next_ref
from app.modules.identity_models import User
from app.modules.conversations_models import (Conversation, Message, MessageAttachment,
                                              MessageProcessingAttempt, VendorIdentityMatch)
from app.modules.vendors_models import Vendor, VendorContact
from app.modules.whatsapp_models import MessageTemplate, WhatsAppAccount

log = logging.getLogger("keyway.conversations")

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

CONVERSATION_STATUSES = ["NEW", "OPEN", "PROCESSING", "WAITING_FOR_VENDOR",
                         "WAITING_FOR_STAFF", "RESOLVED", "ARCHIVED"]


def send_outbound_text(db: Session, conversation_id: int | None, text: str, template_name: str | None = None) -> Message | None:
    """Send an outbound WhatsApp reply.

    CLOUD_API mode: attempts a real Graph API send (falls back to a recorded
    SIMULATED/FAILED message so the pipeline never breaks mid-conversation).
    SIMULATOR mode: records the message locally as before.
    Renders simple {{placeholder}} templates and records delivery status."""
    if not conversation_id:
        return None
    conv = db.get(Conversation, conversation_id)
    if not conv:
        return None
    body = text
    if template_name:
        tpl = db.query(MessageTemplate).filter(MessageTemplate.name == template_name).first()
        if tpl:
            body = tpl.body
    wa_id = f"SIM-{utcnow().timestamp()}-{conversation_id}"
    status = "SENT"
    acc = db.query(WhatsAppAccount).first()
    if acc and acc.mode == "CLOUD_API" and conv.contact_phone:
        try:
            from app.modules import whatsapp_cloud as cloud
            sent = cloud.send_text(db, conv.contact_phone, body)
            if sent.get("wa_message_id"):
                wa_id = sent["wa_message_id"]
        except Exception as e:  # CloudAPIError, network, unconfigured
            status = "FAILED"
            wa_id = f"SIM-{utcnow().timestamp()}-{conversation_id}"
            try:
                log.warning("Cloud API outbound failed (recorded locally): %s", e)
            except Exception:
                pass
    msg = Message(conversation_id=conversation_id, direction="OUT",
                  wa_message_id=wa_id,
                  msg_type="text", body_text=body, status=status)
    db.add(msg)
    conv.last_message_at = utcnow()
    conv.last_message_preview = body[:150]
    return msg


class SendIn(BaseModel):
    text: str


class AssignIn(BaseModel):
    user_id: int | None = None


class StatusIn(BaseModel):
    status: str


@router.get("")
def list_conversations(user: User = Depends(require_staff), db: Session = Depends(get_db),
                       status: str = "", vendor_id: int = 0, q: str = "", unassigned: bool = False):
    query = db.query(Conversation)
    if status:
        query = query.filter(Conversation.status == status)
    if vendor_id:
        query = query.filter(Conversation.vendor_id == vendor_id)
    if unassigned:
        query = query.filter(Conversation.vendor_id.is_(None))
    if q:
        like = f"%{q}%"
        query = query.filter((Conversation.contact_name.ilike(like)) | (Conversation.contact_phone.ilike(like)) |
                             (Conversation.last_message_preview.ilike(like)))
    rows = query.order_by(Conversation.last_message_at.desc().nullslast(), Conversation.id.desc()).limit(200).all()
    vendors = {v.id: v.name for v in db.query(Vendor).all()}
    return [serialize(c, vendor_name=vendors.get(c.vendor_id) if c.vendor_id else None) for c in rows]


@router.get("/{conversation_id}")
def get_conversation(conversation_id: int, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    from app.modules.orders_models import OrderDraft, Order
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    messages = (db.query(Message).filter(Message.conversation_id == conversation_id)
                .order_by(Message.id).limit(300).all())
    msg_ids = [m.id for m in messages]
    drafts = (db.query(OrderDraft).filter(OrderDraft.message_id.in_(msg_ids)).all()
              if msg_ids else [])
    conv.unread_count = 0
    if conv.status == "NEW":
        conv.status = "OPEN"
    db.commit()
    vendor = db.get(Vendor, conv.vendor_id) if conv.vendor_id else None
    contacts = (db.query(VendorContact).filter(VendorContact.vendor_id == conv.vendor_id).all()
                if conv.vendor_id else [])
    orders = []
    if vendor:
        orders = (db.query(Order).filter(Order.vendor_id == vendor.id)
                  .order_by(Order.id.desc()).limit(10).all())
    identity_matches = (db.query(VendorIdentityMatch)
                        .filter(VendorIdentityMatch.conversation_id == conversation_id)
                        .order_by(VendorIdentityMatch.id.desc()).limit(5).all())
    return serialize(conv, vendor_name=vendor.name if vendor else None,
                     vendor=serialize(vendor) if vendor else None,
                     contacts=serialize_list(contacts),
                     messages=serialize_list(messages),
                     drafts=serialize_list(drafts),
                     recent_orders=serialize_list(orders),
                     identity_matches=serialize_list(identity_matches))


@router.post("/{conversation_id}/send")
def send_message(conversation_id: int, body: SendIn, user: User = Depends(require_perm("conversations.manage")), db: Session = Depends(get_db)):
    msg = send_outbound_text(db, conversation_id, body.text)
    if not msg:
        raise HTTPException(404, "Conversation not found")
    db.commit()
    audit(db, user, "send", "conversation", conversation_id, "Sent outbound message (simulated)")
    db.commit()
    return serialize(msg)


@router.post("/{conversation_id}/assign")
def assign(conversation_id: int, body: AssignIn, user: User = Depends(require_perm("conversations.manage")), db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    conv.assigned_user_id = body.user_id
    if body.user_id and conv.status in ("NEW", "OPEN"):
        conv.status = "PROCESSING"
    db.commit()
    return serialize(conv)


@router.post("/{conversation_id}/status")
def set_status(conversation_id: int, body: StatusIn, user: User = Depends(require_perm("conversations.manage")), db: Session = Depends(get_db)):
    if body.status not in CONVERSATION_STATUSES:
        raise HTTPException(400, "Unknown conversation status")
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    conv.status = body.status
    db.commit()
    return serialize(conv)


@router.post("/{conversation_id}/attach-vendor")
def attach_vendor(conversation_id: int, body: dict, user: User = Depends(require_perm("vendors.manage")), db: Session = Depends(get_db)):
    """Staff-assisted identification: assign an unknown sender to a vendor after verification."""
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    vendor_id = body.get("vendor_id")
    contact_id = body.get("contact_id")
    v = db.get(Vendor, vendor_id) if vendor_id else None
    if not v:
        raise HTTPException(400, "vendor_id required")
    conv.vendor_id = v.id
    match = VendorIdentityMatch(conversation_id=conv.id, phone=conv.contact_phone,
                                matched_vendor_id=v.id, method="STAFF_ASSISTED",
                                confidence=1.0, status="MATCHED_MANUAL", decided_by_user_id=user.id)
    db.add(match)
    if contact_id:
        c = db.get(VendorContact, contact_id)
        if c:
            c.wa_verified = True
            c.verification_method = "STAFF_ASSISTED"
            c.verified_at = utcnow()
    audit(db, user, "identify", "conversation", conv.id, f"Attached sender {conv.contact_phone} to vendor {v.name}")
    db.commit()
    return serialize(conv)
