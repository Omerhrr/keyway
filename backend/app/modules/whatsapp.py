"""WhatsApp integration module.

This build runs in SIMULATOR mode: inbound vendor messages enter through
/api/whatsapp/simulator/send and flow through the exact same ingestion pipeline
a WhatsApp Cloud API webhook would use (idempotency, identity match, intent,
extraction, drafts, replies). The webhook endpoint exists as a stub so the
Cloud API can be switched on later without touching the pipeline.
"""
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.db import get_db, utcnow
from app.core.deps import require_staff, require_perm
from app.core.serialize import serialize, serialize_list
from app.core.audit import audit
from app.core.ids import next_ref
from app.core.money import fmt_naira
from app.modules.identity_models import User
from app.modules.vendors_models import Vendor, VendorContact
from app.modules.conversations_models import (Conversation, Message, MessageProcessingAttempt,
                                              VendorIdentityMatch)
from app.modules.orders_models import OrderDraft, Order, OrderItem
from app.modules.whatsapp_models import WhatsAppAccount, MessageTemplate
from app.modules.recognition import analyze_message
from app.modules.notify import notify
from app.modules.conversations import send_outbound_text

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

# Intents that produce order drafts
DRAFT_INTENTS = {"NEW_ORDER"}


def normalize_phone(p: str) -> str:
    digits = "".join(ch for ch in (p or "") if ch.isdigit())
    if digits.startswith("234"):
        digits = "0" + digits[3:]
    return digits


def get_account(db: Session) -> WhatsAppAccount:
    acc = db.query(WhatsAppAccount).first()
    if not acc:
        acc = WhatsAppAccount(display_name="Keyway Logistics", mode="SIMULATOR", status="CONNECTED")
        db.add(acc)
        db.commit()
    return acc


def match_vendor(db: Session, phone: str) -> tuple[Vendor | None, VendorContact | None, str]:
    """Identity recognition - priority 1: registered verified WhatsApp number."""
    contact = (db.query(VendorContact)
               .filter(VendorContact.phone == phone, VendorContact.is_whatsapp.is_(True))
               .first())
    if contact:
        vendor = db.get(Vendor, contact.vendor_id)
        if vendor:
            return vendor, contact, ("PHONE_NUMBER" if contact.wa_verified else "PHONE_NUMBER")
    return None, None, "NONE"


def find_or_create_conversation(db: Session, phone: str, vendor: Vendor | None, contact_name: str = "") -> Conversation:
    conv = (db.query(Conversation)
            .filter(Conversation.contact_phone == phone)
            .order_by(Conversation.id.desc()).first())
    if not conv:
        conv = Conversation(channel="WHATSAPP", vendor_id=vendor.id if vendor else None,
                            contact_phone=phone, contact_name=contact_name or (vendor.name if vendor else ""),
                            wa_contact_id=f"wa.{phone}", status="NEW")
        db.add(conv)
        db.flush()
    elif vendor and conv.vendor_id != vendor.id:
        conv.vendor_id = vendor.id
    if vendor:
        conv.contact_name = conv.contact_name or vendor.name
    return conv


def detect_duplicate(db, vendor_id: int, x: dict) -> int | None:
    from datetime import timedelta
    product = x.get("product") or {}
    product_id = product.get("product_id")
    qty = x.get("quantity")
    phone = x.get("customer_phone")
    if not (product_id and qty and phone):
        return None
    cutoff = utcnow() - timedelta(hours=48)
    rows = (db.query(Order, OrderItem)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .filter(Order.vendor_id == vendor_id, Order.created_at >= cutoff,
                    Order.status.notin_(["CANCELLED"]), OrderItem.product_id == product_id,
                    OrderItem.qty == qty).all())
    for o, _ in rows:
        from app.modules.orders_models import Customer
        c = db.get(Customer, o.customer_id)
        if c and c.phone == phone:
            return o.id
    return None


def build_reply_for_analysis(db, conv, vendor, analysis: dict, draft: OrderDraft | None) -> str:
    """Compose the vendor-facing reply (simulated outbound)."""
    intent = analysis["intent"]
    if intent == "NEW_ORDER":
        if draft is None:
            return "Thank you! Our team is reviewing your message and will confirm your order shortly."
        x = draft.extracted or {}
        missing = draft.missing_fields or []
        if missing:
            questions = {
                "customer_name": "the customer's full name",
                "customer_phone": "the customer's phone number",
                "product": "which product you want (exact name)",
                "quantity": "the quantity",
                "delivery_address": "the delivery location (city/area)",
            }
            asked = ", ".join(questions.get(m, m) for m in missing)
            return (f"Thank you! We captured part of your order. Please provide: {asked}. "
                    f"We will prepare the order as soon as we have these.")
        candidates = analysis.get("candidates") or []
        if not x.get("product") and candidates:
            opts = " / ".join(c["matched_label"] for c in candidates[:3])
            return f"Which product do you mean: {opts}?"
        prod = (x.get("product") or {}).get("name", "item")
        qty = x.get("quantity", "?")
        price = x.get("unit_price_kobo") or 0
        price_txt = f" at {fmt_naira(price)}" if price else ""
        return (f"Order draft ready: {qty} x {prod}{price_txt} for {x.get('customer_name')} "
                f"({x.get('city') or x.get('state') or 'location pending'}). "
                f"Reply YES to confirm or tell us what to change.")
    if intent == "ORDER_STATUS_ENQUIRY":
        ref = analysis.get("order_ref")
        if ref:
            o = db.query(Order).filter(Order.reference == ref.upper()).first()
            if o and o.vendor_id == (vendor.id if vendor else None):
                return (f"Order {o.reference} is currently {o.status.replace('_', ' ').title()}. "
                        f"We will notify you as soon as there is an update.")
            if o:
                return "I cannot share details of that order from this number."
        return "Please send the order reference (e.g. KW-1024) and we will check right away."
    if intent == "ORDER_UPDATE":
        return "We have noted your requested change. For security, our staff will confirm the exact change with you before updating the order."
    if intent == "ORDER_CANCELLATION_REQUEST":
        return "Your cancellation request has been logged. A staff member will confirm the cancellation with you before it is processed."
    if intent == "INVENTORY_ENQUIRY":
        return "Our team will send you your current stock summary shortly."
    if intent in ("PAYMENT_ENQUIRY", "SETTLEMENT_ENQUIRY"):
        return "Our finance team will respond with your account balance shortly."
    if intent == "UNKNOWN_INTENT":
        return "Sorry, we could not understand that. Send an order (e.g. 'Send 2 black sneakers size 42 to Musa, 08012345678, Kaduna') or a question about your orders."
    return "Thank you for your message. Our team will get back to you shortly."


def ingest_message(db: Session, *, from_phone: str, wa_message_id: str | None, msg_type: str = "text",
                   text: str = "", media_ref: str = "") -> dict:
    """The core inbound pipeline (identical for simulator and future webhook)."""
    phone = normalize_phone(from_phone)
    if not phone:
        raise HTTPException(400, "A valid sender phone number is required")
    # 1. Idempotency: never process the same WhatsApp message twice
    if wa_message_id:
        existing = db.query(Message).filter(Message.wa_message_id == wa_message_id).first()
        if existing:
            return {"duplicate": True, "message_id": existing.id, "conversation_id": existing.conversation_id}
    vendor, contact, method = match_vendor(db, phone)
    conv = find_or_create_conversation(db, phone, vendor, contact.name if contact else "")
    msg = Message(conversation_id=conv.id, direction="IN",
                  wa_message_id=wa_message_id or f"SIM-{uuid.uuid4().hex[:20]}",
                  msg_type=msg_type, body_text=text or "", media_ref=media_ref or "",
                  status="RECEIVED")
    db.add(msg)
    db.flush()
    db.add(VendorIdentityMatch(conversation_id=conv.id, message_id=msg.id, phone=phone,
                               matched_vendor_id=vendor.id if vendor else None,
                               method=method, confidence=1.0 if vendor else 0.0,
                               status="AUTO" if vendor else "PENDING"))
    conv.last_message_at = utcnow()
    conv.last_message_preview = (text or f"[{msg_type}]")[:150]
    conv.unread_count += 1
    if conv.status in ("RESOLVED", "ARCHIVED"):
        conv.status = "OPEN"

    analysis = analyze_message(db, vendor, text) if vendor else {
        "intent": "UNKNOWN_INTENT", "confidence": 0.0, "missing": ["vendor_identity"],
        "candidates": [], "llm_used": False,
    }
    msg.intent = analysis["intent"]
    msg.processed_at = utcnow()

    draft = None
    result_status = "OK"
    if vendor is None:
        result_status = "NEEDS_REVIEW"
        notify(db, event_type="UNASSIGNED_SENDER", title="Unknown WhatsApp sender",
               body=f"Message from {phone} could not be matched to a vendor. "
                    f"Assign it in the inbox to proceed.",
               entity_type="conversation", entity_id=conv.id)
        reply = ("Your number is not registered with Keyway. Please contact support to link "
                 "this number to your store.")
    elif analysis["intent"] in DRAFT_INTENTS:
        x = {
            "customer_name": analysis.get("customer_name"),
            "customer_phone": analysis.get("customer_phone"),
            "customer_phone_alt": analysis.get("customer_phone_alt"),
            "quantity": analysis.get("quantity"),
            "unit_price_kobo": analysis.get("amount_kobo"),
            "price_source": "EXTRACTED" if analysis.get("amount_kobo") else None,
            "state": analysis.get("state"),
            "city": analysis.get("city"),
            "product": analysis.get("product"),
            "payment_method": "COD",
            "original_text": text,
            "extracted_by": "llm" if analysis.get("llm_used") else "rules",
        }
        dup = detect_duplicate(db, vendor.id, x)
        draft = OrderDraft(draft_ref="PENDING", vendor_id=vendor.id, conversation_id=conv.id,
                           message_id=msg.id, source="WHATSAPP", extracted=x,
                           product_candidates=analysis.get("candidates") or [],
                           missing_fields=analysis.get("missing") or [],
                           duplicate_of_order_id=dup,
                           confidence=analysis.get("confidence", 0))
        db.add(draft)
        db.flush()
        draft.draft_ref = next_ref(db, OrderDraft, "draft_ref", "DRF")
        if dup:
            draft.status = "PENDING_REVIEW"
            draft.review_notes = f"Possible duplicate of order id {dup}"
        elif analysis.get("missing"):
            draft.status = "AWAITING_VENDOR"
        elif analysis.get("confidence", 0) >= 0.45:
            draft.status = "PENDING_REVIEW"
        else:
            draft.status = "PENDING_REVIEW"
        result_status = "OK" if not analysis.get("missing") else "NEEDS_REVIEW"
        notify(db, event_type="NEW_WHATSAPP_ORDER", title=f"Order draft {draft.draft_ref} from {vendor.name}",
               body=(text or "")[:120], vendor_id=vendor.id, entity_type="order_draft", entity_id=draft.id)

        # PRD: high-confidence auto-create only when vendor explicitly enabled it
        if (vendor.auto_confirm_orders and not analysis.get("missing")
                and analysis.get("confidence", 0) >= 0.75 and not dup):
            from app.modules.orders import create_order_from_draft
            try:
                order = create_order_from_draft(db, draft, None)
                db.commit()
                send_outbound_text(db, conv.id, f"Order {order.reference} has been registered automatically. "
                                                f"Thank you for your business!")
                db.commit()
                return {"ok": True, "auto_created_order": order.reference,
                        "conversation_id": conv.id, "message_id": msg.id, "draft_id": draft.id}
            except HTTPException:
                pass  # fall through to manual review
    elif analysis["intent"] in ("ORDER_UPDATE", "ORDER_CANCELLATION_REQUEST"):
        result_status = "NEEDS_REVIEW"
        notify(db, event_type="ORDER_CHANGE_REQUEST", title=f"{analysis['intent']} from {vendor.name}",
               body=(text or "")[:120], vendor_id=vendor.id, entity_type="conversation", entity_id=conv.id)
    else:
        result_status = "OK"

    reply = build_reply_for_analysis(db, conv, vendor, analysis, draft)
    if reply:
        send_outbound_text(db, conv.id, reply)
    db.add(MessageProcessingAttempt(message_id=msg.id, attempt_no=1, status=result_status,
                                    result={"intent": analysis["intent"],
                                            "confidence": analysis.get("confidence", 0),
                                            "missing": analysis.get("missing", []),
                                            "llm_used": analysis.get("llm_used", False)}))
    db.commit()
    return {"ok": True, "conversation_id": conv.id, "message_id": msg.id,
            "draft_id": draft.id if draft else None, "intent": analysis["intent"],
            "confidence": analysis.get("confidence", 0), "vendor_id": vendor.id if vendor else None}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

class SimIn(BaseModel):
    from_phone: str
    text: str = ""
    msg_type: str = "text"
    wa_message_id: str | None = None
    contact_name: str = ""


@router.get("/account")
def account(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    acc = get_account(db)
    return serialize(acc, access_token_set=bool(acc.access_token_enc))


@router.get("/templates")
def templates(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return serialize_list(db.query(MessageTemplate).order_by(MessageTemplate.id).all())


@router.post("/simulator/send")
def simulator_send(body: SimIn, user: User = Depends(require_perm("whatsapp.manage")), db: Session = Depends(get_db)):
    """Inject an inbound vendor message into the real ingestion pipeline."""
    result = ingest_message(db, from_phone=body.from_phone, wa_message_id=body.wa_message_id,
                            msg_type=body.msg_type, text=body.text)
    audit(db, user, "simulate", "whatsapp", result.get("conversation_id"),
          f"Simulated inbound message from {body.from_phone}")
    db.commit()
    return result


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """Cloud API webhook stub. Signature verification activates when mode=CLOUD_API
    and credentials are configured. Disabled in SIMULATOR mode by design."""
    acc = get_account(db)
    if acc.mode != "CLOUD_API":
        raise HTTPException(status_code=503, detail="Webhook disabled in simulator mode")
    raise HTTPException(status_code=501, detail="Cloud API not configured in this build")
