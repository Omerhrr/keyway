"""WhatsApp integration module (Phase 6A/6C).

Two inbound paths feed ONE identical pipeline (idempotency, identity match,
intent, extraction, drafts, replies):
- SIMULATOR mode: /api/whatsapp/simulator/send (accepts text and media)
- CLOUD_API mode: /api/whatsapp/webhook (Meta Cloud API, signature-verified)

Outbound replies go through the Cloud API when configured, otherwise they are
recorded as simulated messages so the pipeline never breaks in demo mode.
"""
import base64
import json
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.db import get_db, utcnow
from app.core.config import settings
from app.core.deps import require_staff, require_perm
from app.core.serialize import serialize, serialize_list
from app.core.audit import audit
from app.core.ids import next_ref
from app.core.money import fmt_naira
from app.modules.identity_models import User
from app.modules.vendors_models import Vendor, VendorContact
from app.modules.conversations_models import (Conversation, Message, MessageProcessingAttempt,
                                              MessageAttachment, VendorIdentityMatch)
from app.modules.orders_models import OrderDraft, Order, OrderItem
from app.modules.whatsapp_models import WhatsAppAccount, MessageTemplate
from app.modules.recognition import analyze_message, media_to_text
from app.modules.notify import notify
from app.modules.conversations import send_outbound_text
from app.modules import whatsapp_cloud as cloud

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

# Intents that produce order drafts
DRAFT_INTENTS = {"NEW_ORDER"}
MEDIA_DIR = Path(settings.DATABASE_URL.replace("sqlite:///", "")).parent / "media"


def normalize_phone(p: str) -> str:
    digits = "".join(ch for ch in (p or "") if ch.isdigit())
    if digits.startswith("234"):
        digits = "0" + digits[3:]
    return digits


def get_account(db: Session) -> WhatsAppAccount:
    acc = db.query(WhatsAppAccount).first()
    if not acc:
        acc = WhatsAppAccount(display_name="Keyway Logistics", mode=settings.WHATSAPP_MODE,
                              status="CONNECTED" if settings.WHATSAPP_MODE == "CLOUD_API" else "SIMULATED",
                              phone_number_id=settings.WHATSAPP_PHONE_NUMBER_ID,
                              waba_id=settings.WHATSAPP_WABA_ID,
                              access_token_enc=settings.WHATSAPP_ACCESS_TOKEN)
        db.add(acc)
        db.commit()
    return acc


def store_media(db: Session, msg: Message, msg_type: str, media_bytes: bytes, mime: str) -> str:
    """Persist inbound media under db/media/ and attach it to the message."""
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    ext = {"voice": ".ogg", "audio": ".ogg", "image": ".jpg", "document": ".bin"}.get(msg_type, ".bin")
    if "png" in mime:
        ext = ".png"
    elif "jpeg" in mime or "jpg" in mime:
        ext = ".jpg"
    elif "mpeg" in mime or "mp3" in mime:
        ext = ".mp3"
    elif "ogg" in mime:
        ext = ".ogg"
    fname = f"{uuid.uuid4().hex}{ext}"
    path = MEDIA_DIR / fname
    path.write_bytes(media_bytes)
    ref = f"db/media/{fname}"
    db.add(MessageAttachment(message_id=msg.id, kind=msg_type, mime=mime or "",
                             file_name=fname, storage_ref=ref, size_bytes=len(media_bytes)))
    return ref


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
                   text: str = "", media_ref: str = "", media_bytes: bytes | None = None,
                   mime: str = "", contact_name: str = "") -> dict:
    """The core inbound pipeline (identical for simulator and Cloud API webhook)."""
    phone = normalize_phone(from_phone)
    if not phone:
        raise HTTPException(400, "A valid sender phone number is required")
    # 1. Idempotency: never process the same WhatsApp message twice
    if wa_message_id:
        existing = db.query(Message).filter(Message.wa_message_id == wa_message_id).first()
        if existing:
            return {"duplicate": True, "message_id": existing.id, "conversation_id": existing.conversation_id}
    vendor, contact, method = match_vendor(db, phone)
    conv = find_or_create_conversation(db, phone, vendor, contact_name or (contact.name if contact else ""))
    media_engine = "none"
    media_error = ""
    # 2. Media understanding first (voice -> transcript, image -> description);
    #    the result then flows through the exact same text pipeline.
    if vendor and media_bytes and msg_type in ("voice", "audio", "image", "document"):
        mres = media_to_text(db, vendor, msg_type, media_bytes, mime, caption=text)
        media_engine = mres.get("engine") or "none"
        media_error = mres.get("detail") or ""
        text = mres.get("text") or text
    msg = Message(conversation_id=conv.id, direction="IN",
                  wa_message_id=wa_message_id or f"SIM-{uuid.uuid4().hex[:20]}",
                  msg_type=msg_type, body_text=text or "", media_ref=media_ref or "",
                  status="RECEIVED")
    db.add(msg)
    db.flush()
    if media_bytes and msg_type in ("voice", "audio", "image", "document"):
        try:
            msg.media_ref = store_media(db, msg, msg_type, media_bytes, mime)
        except Exception:
            pass  # storage failure must not block order intake
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
                                            "llm_used": analysis.get("llm_used", False),
                                            "media_engine": media_engine},
                                    error=media_error))
    db.commit()
    return {"ok": True, "conversation_id": conv.id, "message_id": msg.id,
            "draft_id": draft.id if draft else None, "intent": analysis["intent"],
            "confidence": analysis.get("confidence", 0), "vendor_id": vendor.id if vendor else None,
            "media_engine": media_engine}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

class SimIn(BaseModel):
    from_phone: str
    text: str = ""
    msg_type: str = "text"                 # text | voice | image | document
    media_b64: str = ""                    # base64 or data-URL media payload (simulated attachment)
    mime: str = ""
    wa_message_id: str | None = None
    contact_name: str = ""


def _decode_media(data_url: str) -> tuple[bytes, str]:
    """Accept raw base64 or a data: URL; returns (bytes, mime)."""
    raw = (data_url or "").strip()
    mime = ""
    if raw.startswith("data:"):
        head, _, raw = raw.partition(",")
        mime = head[5:].split(";")[0]
    try:
        blob = base64.b64decode(raw, validate=False)
    except Exception:
        raise HTTPException(400, "media_b64 is not valid base64")
    if not blob:
        raise HTTPException(400, "media_b64 decoded to empty payload")
    return blob, mime


@router.get("/account")
def account(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    acc = get_account(db)
    return serialize(acc, access_token_set=bool(acc.access_token_enc))


@router.get("/templates")
def templates(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return serialize_list(db.query(MessageTemplate).order_by(MessageTemplate.id).all())


@router.post("/simulator/send")
def simulator_send(body: SimIn, user: User = Depends(require_perm("whatsapp.manage")), db: Session = Depends(get_db)):
    """Inject an inbound vendor message (text or media) into the real pipeline."""
    media_bytes, mime = None, body.mime
    if body.msg_type in ("voice", "audio", "image", "document") and body.media_b64:
        media_bytes, mime = _decode_media(body.media_b64)
        mime = mime or body.mime
    result = ingest_message(db, from_phone=body.from_phone, wa_message_id=body.wa_message_id,
                            msg_type=body.msg_type, text=body.text, media_bytes=media_bytes,
                            mime=mime, contact_name=body.contact_name)
    audit(db, user, "simulate", "whatsapp", result.get("conversation_id"),
          f"Simulated inbound {body.msg_type} message from {body.from_phone}")
    db.commit()
    return result


class AccountIn(BaseModel):
    mode: str | None = None               # SIMULATOR | CLOUD_API
    phone_number_id: str | None = None
    waba_id: str | None = None
    access_token: str | None = None       # write-only; never returned


@router.put("/account")
def update_account(body: AccountIn, user: User = Depends(require_perm("whatsapp.manage")),
                   db: Session = Depends(get_db)):
    acc = get_account(db)
    changes = []
    if body.mode in ("SIMULATOR", "CLOUD_API") and body.mode != acc.mode:
        acc.mode = body.mode
        acc.status = "CONNECTED" if body.mode == "CLOUD_API" else "SIMULATED"
        changes.append(f"mode->{body.mode}")
    if body.phone_number_id is not None:
        acc.phone_number_id = body.phone_number_id.strip()
        changes.append("phone_number_id")
    if body.waba_id is not None:
        acc.waba_id = body.waba_id.strip()
        changes.append("waba_id")
    if body.access_token:
        acc.access_token_enc = body.access_token.strip()
        changes.append("access_token(set)")
    audit(db, user, "update", "whatsapp_account", acc.id, f"WhatsApp account updated: {', '.join(changes) or 'no-op'}")
    db.commit()
    return serialize(acc, access_token_set=bool(acc.access_token_enc))


@router.post("/account/test")
def test_account(user: User = Depends(require_perm("whatsapp.manage")), db: Session = Depends(get_db)):
    """Validate Cloud API credentials against Graph API (no message sent)."""
    res = cloud.test_credentials(db)
    audit(db, user, "test", "whatsapp_account", None, f"Cloud API credential test: {'ok' if res.get('ok') else 'failed'}")
    db.commit()
    return res


@router.get("/webhook")
def webhook_verify(request: Request, db: Session = Depends(get_db)):
    """Meta webhook subscription handshake: echo hub.challenge when the verify
    token matches."""
    creds = cloud.effective_credentials(db)
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == creds["verify_token"]:
        return int(params.get("hub.challenge") or 0) if (params.get("hub.challenge") or "").isdigit() \
            else (params.get("hub.challenge") or "")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """WhatsApp Cloud API webhook: signature-verified inbound messages + statuses."""
    raw = await request.body()
    creds = cloud.effective_credentials(db)
    if creds["mode"] != "CLOUD_API":
        raise HTTPException(status_code=503, detail="Webhook disabled in simulator mode")
    if not cloud.verify_signature(raw, request.headers.get("X-Hub-Signature-256"), creds["app_secret"]):
        raise HTTPException(status_code=403, detail="Invalid signature")
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    events = cloud.parse_webhook_payload(payload)
    results = []
    for m in events["messages"]:
        media_bytes = None
        mime = m.get("mime") or ""
        if m.get("media_id"):
            try:
                dl = cloud.download_media(db, m["media_id"])
                media_bytes, mime = dl["bytes"], dl["mime"]
            except cloud.CloudAPIError as e:
                results.append({"wa_message_id": m["wa_message_id"], "error": f"media download failed: {e}"})
        res = ingest_message(db, from_phone=m["from_phone"], wa_message_id=m["wa_message_id"] or None,
                             msg_type=m["msg_type"], text=m["text"], media_bytes=media_bytes,
                             mime=mime, contact_name=m.get("profile_name") or "")
        results.append(res)
    for s in events["statuses"]:
        _apply_status(db, s)
    if not events["messages"]:
        db.commit()
    return {"received": True, "processed": len(results), "statuses": len(events["statuses"])}


def _apply_status(db: Session, s: dict) -> None:
    """Mirror Cloud API delivery statuses onto the outbound message record."""
    wa_id = s.get("wa_message_id")
    if not wa_id:
        return
    msg = db.query(Message).filter(Message.wa_message_id == wa_id).first()
    if not msg:
        return
    new_status = s.get("status") or ""
    if new_status in ("SENT", "DELIVERED", "READ", "FAILED"):
        msg.status = new_status
        db.commit()
