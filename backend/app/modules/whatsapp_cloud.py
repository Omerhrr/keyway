"""WhatsApp Cloud API client (Graph API) - Phase 6A.

Thin, dependency-light adapter around Meta's WhatsApp Cloud API:
- outbound text / template messages
- inbound media download
- webhook signature verification (X-Hub-Signature-256)

Credentials resolve in order: WhatsAppAccount DB row -> env settings.
Nothing here mutates business state: callers decide what a send failure means.
"""
import base64
import hashlib
import hmac
import json
import logging
import httpx
from sqlalchemy.orm import Session
from app.core.config import settings
from app.modules.whatsapp_models import WhatsAppAccount

log = logging.getLogger("keyway.whatsapp")


class CloudAPIError(Exception):
    pass


# ---------------------------------------------------------------------------
# Credential resolution
# ---------------------------------------------------------------------------

def effective_credentials(db: Session) -> dict:
    """Merge DB-stored account config with env settings (DB wins when set)."""
    acc = db.query(WhatsAppAccount).first()
    return {
        "mode": (acc.mode if acc else None) or settings.WHATSAPP_MODE,
        "access_token": (getattr(acc, "access_token_enc", "") if acc else "") or settings.WHATSAPP_ACCESS_TOKEN,
        "phone_number_id": (acc.phone_number_id if acc else "") or settings.WHATSAPP_PHONE_NUMBER_ID,
        "waba_id": (acc.waba_id if acc else "") or settings.WHATSAPP_WABA_ID,
        "app_secret": settings.WHATSAPP_APP_SECRET,
        "verify_token": settings.WHATSAPP_VERIFY_TOKEN,
        "api_version": settings.WHATSAPP_API_VERSION,
    }


def cloud_ready(creds: dict) -> bool:
    return bool(creds.get("access_token") and creds.get("phone_number_id"))


def graph_base(creds: dict) -> str:
    return f"https://graph.facebook.com/{creds.get('api_version') or 'v21.0'}"


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------

def verify_signature(raw_body: bytes, header: str | None, app_secret: str) -> bool:
    """Meta signs every webhook POST with HMAC-SHA256 over the raw body."""
    if not app_secret:
        # No secret configured (dev/simulator): accept but log loudly.
        log.warning("WhatsApp webhook accepted without app secret (KEYWAY_WHATSAPP_APP_SECRET unset)")
        return True
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header[7:], expected)


# ---------------------------------------------------------------------------
# Outbound
# ---------------------------------------------------------------------------

def to_wa_number(local_phone: str) -> str:
    """0803... -> 234803... for Graph API recipients."""
    digits = "".join(ch for ch in (local_phone or "") if ch.isdigit())
    if digits.startswith("234"):
        return digits
    if digits.startswith("0"):
        return "234" + digits[1:]
    return digits


def send_text(db: Session, to_phone: str, text: str) -> dict:
    """Send a freeform text message. Returns {wa_message_id} or raises CloudAPIError.

    Freeform replies are allowed inside the 24-hour customer service window;
    outside it Meta requires approved templates (the caller can catch the
    error and fall back to a template send).
    """
    creds = effective_credentials(db)
    if not cloud_ready(creds):
        raise CloudAPIError("Cloud API not configured (missing access token or phone number id)")
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_number(to_phone),
        "type": "text",
        "text": {"preview_url": False, "body": text[:4096]},
    }
    return _post_message(creds, payload)


def send_template(db: Session, to_phone: str, template_name: str,
                  lang: str = "en", params: list[str] | None = None) -> dict:
    creds = effective_credentials(db)
    if not cloud_ready(creds):
        raise CloudAPIError("Cloud API not configured")
    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_number(to_phone),
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": lang},
        },
    }
    if params:
        payload["template"]["components"] = [{
            "type": "body",
            "parameters": [{"type": "text", "text": p} for p in params],
        }]
    return _post_message(creds, payload)


def _post_message(creds: dict, payload: dict) -> dict:
    url = f"{graph_base(creds)}/{creds['phone_number_id']}/messages"
    headers = {"Authorization": f"Bearer {creds['access_token']}",
               "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as e:
        raise CloudAPIError(f"Graph API unreachable: {e}") from e
    data = {}
    try:
        data = r.json()
    except Exception:
        pass
    if r.status_code >= 400:
        err = (data.get("error") or {}).get("message") or f"HTTP {r.status_code}"
        raise CloudAPIError(f"Cloud API rejected message: {err}")
    wa_id = ((data.get("messages") or [{}])[0]).get("id") or ""
    return {"wa_message_id": wa_id, "raw": data}


# ---------------------------------------------------------------------------
# Inbound media
# ---------------------------------------------------------------------------

def download_media(db: Session, media_id: str) -> dict:
    """Download inbound media (voice notes, images, documents).

    Returns {"bytes": b"...", "mime": str}. Rejects anything above 10 MB."""
    MAX_BYTES = 10 * 1024 * 1024
    creds = effective_credentials(db)
    if not cloud_ready(creds):
        raise CloudAPIError("Cloud API not configured")
    headers = {"Authorization": f"Bearer {creds['access_token']}"}
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        meta = client.get(f"{graph_base(creds)}/{media_id}", headers=headers)
        if meta.status_code >= 400:
            raise CloudAPIError(f"Media metadata fetch failed: HTTP {meta.status_code}")
        url = meta.json().get("url")
        if not url:
            raise CloudAPIError("Media metadata returned no URL")
        # refuse oversized downloads up front when Meta advertises the size
        try:
            declared = int(meta.json().get("file_size") or 0)
        except (TypeError, ValueError):
            declared = 0
        if declared > MAX_BYTES:
            raise CloudAPIError(f"Media too large ({declared} bytes)")
        blob = client.get(url, headers=headers)
        if blob.status_code >= 400:
            raise CloudAPIError(f"Media download failed: HTTP {blob.status_code}")
    if len(blob.content) > MAX_BYTES:
        raise CloudAPIError("Media too large (max 10 MB)")
    mime = meta.json().get("mime_type") or "application/octet-stream"
    return {"bytes": blob.content, "mime": mime}


# ---------------------------------------------------------------------------
# Credential self-test (Settings UI)
# ---------------------------------------------------------------------------

def test_credentials(db: Session) -> dict:
    """Validate stored credentials against Graph API (cheap read, no messages)."""
    creds = effective_credentials(db)
    if not cloud_ready(creds):
        return {"ok": False, "detail": "Access token / phone number id missing"}
    url = f"{graph_base(creds)}/{creds['phone_number_id']}"
    try:
        with httpx.Client(timeout=12.0) as client:
            r = client.get(url, params={"fields": "display_phone_number,verified_name,quality_rating"},
                           headers={"Authorization": f"Bearer {creds['access_token']}"})
    except httpx.HTTPError as e:
        return {"ok": False, "detail": f"Unreachable: {e}"}
    if r.status_code >= 400:
        err = ""
        try:
            err = (r.json().get("error") or {}).get("message") or ""
        except Exception:
            pass
        return {"ok": False, "detail": err or f"HTTP {r.status_code}"}
    d = r.json()
    return {"ok": True, "detail": f"Connected as {d.get('verified_name') or d.get('display_phone_number') or creds['phone_number_id']}",
            "display_phone_number": d.get("display_phone_number"), "quality_rating": d.get("quality_rating")}


def parse_webhook_payload(payload: dict) -> dict:
    """Normalize a Cloud API webhook body into flat event lists.

    Returns {"messages": [...], "statuses": [...]} where each message has
    {from_phone, profile_name, wa_message_id, msg_type, text, media_id, mime}.
    """
    out_msgs, out_status = [], []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            contacts = value.get("contacts") or []
            profile = (contacts[0] or {}).get("profile") or {} if contacts else {}
            for m in value.get("messages") or []:
                mtype = m.get("type") or "unknown"
                text, media_id, mime = "", "", ""
                if mtype == "text":
                    text = (m.get("text") or {}).get("body") or ""
                elif mtype in ("audio", "voice"):
                    mtype = "voice"
                    media_id = (m.get("audio") or {}).get("id") or ""
                    mime = (m.get("audio") or {}).get("mime_type") or ""
                elif mtype == "image":
                    media_id = (m.get("image") or {}).get("id") or ""
                    mime = (m.get("image") or {}).get("mime_type") or ""
                    text = (m.get("image") or {}).get("caption") or ""
                elif mtype == "document":
                    media_id = (m.get("document") or {}).get("id") or ""
                    mime = (m.get("document") or {}).get("mime_type") or ""
                    text = (m.get("document") or {}).get("caption") or ""
                elif mtype == "button":
                    text = (m.get("button") or {}).get("text") or ""
                elif mtype == "interactive":
                    reply = ((m.get("interactive") or {}).get("button_reply")
                             or (m.get("interactive") or {}).get("list_reply") or {})
                    text = reply.get("title") or ""
                out_msgs.append({
                    "from_phone": m.get("from") or "",
                    "profile_name": profile.get("name") or "",
                    "wa_message_id": m.get("id") or "",
                    "msg_type": mtype,
                    "text": text,
                    "media_id": media_id,
                    "mime": mime,
                })
            for s in value.get("statuses") or []:
                out_status.append({
                    "wa_message_id": s.get("id") or "",
                    "status": (s.get("status") or "").upper(),
                    "recipient": s.get("recipient_id") or "",
                    "error": ((s.get("errors") or [{}])[0]).get("message") or "",
                })
    return {"messages": out_msgs, "statuses": out_status}
