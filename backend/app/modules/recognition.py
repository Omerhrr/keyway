"""Hybrid message understanding: deterministic rules first, LLM for messy messages.

PRD boundaries honored here:
- AI is an assistive interpretation layer, never the authority.
- Product matching is restricted to the identified vendor's inventory.
- Never fabricate prices or customer details; extracted values carry provenance.
"""
import re
import base64
import httpx
from rapidfuzz import fuzz
from app.core.config import settings

# ---------------------------------------------------------------------------
# Reference geography (lightweight)
NG_STATES = [
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno",
    "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "FCT", "Gombe", "Imo",
    "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi", "Kwara", "Lagos", "Nasarawa",
    "Niger", "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers", "Sokoto", "Taraba",
    "Yobe", "Zamfara",
]
CITIES = [
    "Lagos", "Ikeja", "Lekki", "Surulere", "Yaba", "Ibadan", "Abuja", "Kano", "Kaduna", "Zaria",
    "Port Harcourt", "Enugu", "Benin", "Onitsha", "Aba", "Abeokuta", "Jos", "Ilorin", "Owerri",
    "Uyo", "Calabar", "Warri", "Akure", "Minna", "Lokoja", "Makurdi", "Sokoto", "Katsina",
    "Nnewi", "Asaba", "Oshogbo", "Ado Ekiti", "Gwagwalada", "Nyanya", "Kubwa", "Maitama", "Wuse",
]
_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
              "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "a": 1, "an": 1}

# ---------------------------------------------------------------------------
# Intent classification (deterministic rules, evaluated in order)
_INTENT_RULES = [
    ("ORDER_CANCELLATION_REQUEST", [r"\bcancel", r"\bstop (the )?(order|delivery)\b", r"don.?t want"]),
    ("ORDER_STATUS_ENQUIRY", [r"\bwhere is\b", r"\bstatus\b", r"\btrack\b", r"\bkw-\d+", r"has (my|the) order",
                              r"when will .* (arrive|deliver)"]),
    ("ORDER_UPDATE", [r"\bchange\b", r"\bupdate\b", r"\bmodify\b", r"\binstead\b", r"\badd to\b", r"\bmake it\b"]),
    ("INVENTORY_ENQUIRY", [r"\bstock\b", r"\bavailable\b", r"do you have", r"\bin stock\b"]),
    ("PAYMENT_ENQUIRY", [r"\bpayment\b", r"\bpaid\b", r"\bcod\b", r"\btransfer\b.*\bmoney\b", r"\brefund\b"]),
    ("SETTLEMENT_ENQUIRY", [r"\bsettle", r"\bbalance\b", r"\bowe\b", r"\bpayout\b", r"\bremittance\b"]),
    ("NEW_ORDER", [r"\bsend\b", r"\bdeliver\b", r"\bnew order\b", r"\border\b", r"\bship\b", r"\bdispatch\b",
                   r"\banother order\b", r"\bbuy\b", r"\bprocess\b"]),
]

PHONE_RE = re.compile(r"(?:\+?234|0)([789]\d{9})")
ORDER_REF_RE = re.compile(r"\bKW-\d{3,6}\b", re.IGNORECASE)
QTY_RE = re.compile(r"\b(\d{1,3})\s*(?:pcs|pieces|piece|units?|x)\b", re.IGNORECASE)
AMOUNT_K_RE = re.compile(r"\b(\d{1,3})\s*k\b", re.IGNORECASE)
AMOUNT_RE = re.compile(r"(?:\u20a6|ngn|n)\s?(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d{3,7}(?:\.\d{1,2})?)", re.IGNORECASE)


def classify_intent(text: str) -> tuple[str, float]:
    t = (text or "").lower()
    for intent, patterns in _INTENT_RULES:
        for p in patterns:
            if re.search(p, t):
                return intent, 0.8
    if len(t.split()) <= 2:
        return "UNKNOWN_INTENT", 0.3
    return "GENERAL_MESSAGE", 0.5


def extract_phones(text: str) -> list[str]:
    """Normalize Nigerian numbers to 080X XXX XXXX (11-digit local form)."""
    out = []
    for m in PHONE_RE.finditer(text or ""):
        out.append("0" + m.group(1))
    return out


def _num(s: str) -> int:
    return int(round(float(s.replace(",", ""))))


def extract_amounts(text: str) -> list[int]:
    """Amount candidates in kobo. '45k' shorthand and comma-formatted numbers."""
    text = text or ""
    kobo = []
    for m in AMOUNT_K_RE.finditer(text):
        kobo.append(int(m.group(1)) * 1000 * 100)
    for m in AMOUNT_RE.finditer(text):
        kobo.append(_num(m.group(1)) * 100)
    return kobo


def extract_qty(text: str) -> int | None:
    text = text or ""
    m = QTY_RE.search(text)
    if m:
        return min(int(m.group(1)), 999)
    for w, n in _NUM_WORDS.items():
        if re.search(rf"\b{w}\b", text.lower()):
            return n
    # bare small number before a product-ish word ("2 black sneakers")
    m = re.search(r"\b(\d{1,2})\s+[a-z]", text.lower())
    if m:
        return int(m.group(1))
    return None


def extract_customer_name(text: str) -> str | None:
    text = text or ""
    m = re.search(r"\b(?:to|for)\s+([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)", text)
    if m:
        return m.group(1)
    # Name directly before a phone number: "Musa, 08012345678"
    m = re.search(r"([A-Z][a-z]{2,})\s*[,;]?\s*(?:\+?234|0)[789]", text)
    if m and m.group(1).lower() not in {s.lower() for s in NG_STATES + CITIES}:
        return m.group(1)
    return None


def extract_place(text: str) -> dict:
    text = text or ""
    result = {"state": None, "city": None}
    for st in NG_STATES:
        if re.search(rf"\b{re.escape(st)}\b", text, re.IGNORECASE):
            result["state"] = st
            break
    if result["state"] == "FCT":
        result["state"] = "FCT"
    for c in sorted(CITIES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(c)}\b", text, re.IGNORECASE):
            result["city"] = c
            break
    return result


def extract_order_ref(text: str) -> str | None:
    m = ORDER_REF_RE.search(text or "")
    return m.group(0).upper() if m else None


def strip_noise(text: str) -> str:
    """Remove phones, amounts, qty markers and place names to isolate product wording."""
    t = text or ""
    t = PHONE_RE.sub(" ", t)
    t = AMOUNT_RE.sub(" ", t)
    t = AMOUNT_K_RE.sub(" ", t)
    t = QTY_RE.sub(" ", t)
    t = ORDER_REF_RE.sub(" ", t)
    for w in NG_STATES + CITIES:
        t = re.sub(rf"\b{re.escape(w)}\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(?:to|for|send|deliver|order|new|another|please|pls|abeg|price|is|at|of|and|the|my|customer)\b",
               " ", t, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", t).strip(" ,.:-")


def match_products(db, vendor_id: int, text: str) -> list[dict]:
    """Fuzzy-match the message against the VENDOR's own catalog only (PRD rule)."""
    from app.modules.catalog_models import Product, ProductVariant, ProductAlias
    query = strip_noise(text)
    if not query:
        query = text or ""
    candidates: list[dict] = []
    products = db.query(Product).filter(Product.vendor_id == vendor_id, Product.status == "ACTIVE").all()
    aliases = db.query(ProductAlias).filter(ProductAlias.vendor_id == vendor_id).all()
    alias_by_product: dict[int, list[tuple[str, int]]] = {}
    for a in aliases:
        alias_by_product.setdefault(a.product_id, []).append((a.alias, a.weight))
    variants_by_product: dict[int, list] = {}
    if products:
        vs = db.query(ProductVariant).filter(ProductVariant.product_id.in_([p.id for p in products])).all()
        for v in vs:
            variants_by_product.setdefault(v.product_id, []).append(v)

    for p in products:
        best_score = 0.0
        best_label = p.name
        best_variant_id = 0
        names = [(p.name, 100), (p.sku, 95)] + alias_by_product.get(p.id, [])
        for name, weight in names:
            score = max(fuzz.token_set_ratio(query.lower(), name.lower()),
                        fuzz.partial_ratio(query.lower(), name.lower())) * (weight / 100.0)
            if score > best_score:
                best_score = score
                best_label = name
        for v in variants_by_product.get(p.id, []):
            score = fuzz.token_set_ratio(query.lower(), f"{p.name} {v.name}".lower())
            if score > best_score:
                best_score = score
                best_label = f"{p.name} ({v.name})"
                best_variant_id = v.id
        if best_score >= 60:
            candidates.append({
                "product_id": p.id, "variant_id": best_variant_id, "sku": p.sku,
                "name": p.name, "matched_label": best_label, "score": round(min(best_score, 100), 1),
            })
    candidates.sort(key=lambda c: (-c["score"], c["name"]))
    return candidates[:5]


def llm_extract(text: str, catalog: list[dict]) -> dict | None:
    """Ask the LLM mini-service to parse a messy message. Returns dict or None.

    The LLM never creates anything; its output is merged into deterministic
    validation downstream and always carries extracted provenance."""
    if not settings.LLM_ENABLED:
        return None
    try:
        with httpx.Client(timeout=12.0) as client:
            r = client.post(f"{settings.LLM_SERVICE_URL}/v1/extract",
                            json={"text": text, "catalog": catalog})
            if r.status_code == 200:
                return r.json()
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# Media understanding (Phase 6C): voice notes -> text, images -> description.
# Same assistive boundary as text extraction: transcription output is treated
# as message text and flows through the identical rules+LLM pipeline.
# ---------------------------------------------------------------------------

def llm_transcribe(file_b64: str, mime: str = "") -> str | None:
    """Speech-to-text via the LLM mini-service. Returns transcript or None."""
    if not settings.LLM_ENABLED:
        return None
    try:
        with httpx.Client(timeout=45.0) as client:
            r = client.post(f"{settings.LLM_SERVICE_URL}/v1/transcribe",
                            json={"file_base64": file_b64, "mime": mime})
            if r.status_code == 200:
                return (r.json() or {}).get("text") or None
    except Exception:
        return None
    return None


def llm_vision(image_b64: str, mime: str = "image/jpeg", question: str = "", catalog: list[dict] | None = None) -> dict | None:
    """Vision extraction via the LLM mini-service. Returns dict or None."""
    if not settings.LLM_ENABLED:
        return None
    try:
        with httpx.Client(timeout=100.0) as client:
            r = client.post(f"{settings.LLM_SERVICE_URL}/v1/vision",
                            json={"image_base64": image_b64, "mime": mime,
                                  "question": question, "catalog": catalog or []})
            if r.status_code == 200:
                return r.json()
    except Exception:
        return None
    return None


def media_to_text(db, vendor, msg_type: str, media_bytes: bytes, mime: str = "",
                  caption: str = "") -> dict:
    """Convert an inbound media payload into message text for the pipeline.

    voice/audio -> ASR transcript; image -> caption + vision description with a
    catalog-aware product hint; document -> caption only (contents not parsed).
    Returns {"text": str, "engine": str, "detail": str}.
    """
    mime = (mime or "").lower()
    engine, detail, extra = "none", "", ""
    if msg_type in ("voice", "audio"):
        b64 = base64.b64encode(media_bytes).decode()
        transcript = llm_transcribe(b64, mime)
        if transcript:
            engine, extra = "asr", transcript.strip()
            detail = f"Transcribed {len(media_bytes)} bytes via ASR"
        else:
            detail = "ASR unavailable or failed"
    elif msg_type == "image":
        catalog = []
        if vendor:
            from app.modules.catalog_models import Product
            catalog = [{"product_id": p.id, "sku": p.sku, "name": p.name}
                       for p in db.query(Product)
                       .filter(Product.vendor_id == vendor.id, Product.status == "ACTIVE").all()]
        b64 = base64.b64encode(media_bytes).decode()
        vision = llm_vision(b64, mime or "image/jpeg", catalog=catalog)
        if vision:
            engine = "vision"
            desc = (vision.get("description") or "").strip()
            extra = desc
            detail = f"Vision: {vision.get('suggested_product_query') or desc[:60]}"
        else:
            detail = "Vision unavailable or failed"
    if msg_type == "document":
        engine, detail = "caption-only", "Document contents are not parsed; caption used"
    parts = [p for p in (caption or "", extra or "") if p]
    return {"text": " \n".join(parts), "engine": engine, "detail": detail}


def analyze_message(db, vendor, text: str) -> dict:
    """Full hybrid analysis of one vendor message."""
    intent, intent_conf = classify_intent(text)
    phones = extract_phones(text)
    amounts = extract_amounts(text)
    qty = extract_qty(text)
    name = extract_customer_name(text)
    place = extract_place(text)
    order_ref = extract_order_ref(text)
    candidates = match_products(db, vendor.id, text) if vendor else []

    resolved = None
    if candidates:
        top = candidates[0]
        second = candidates[1] if len(candidates) > 1 else None
        if top["score"] >= 85 and (not second or top["score"] - second["score"] >= 10):
            resolved = top

    # Hybrid: if rules look weak, consult the LLM (availability permitting)
    llm_used = False
    llm_conf = 0.0
    weak_rules = intent in ("GENERAL_MESSAGE", "UNKNOWN_INTENT") or not resolved or not name or not phones
    if vendor and weak_rules:
        from app.modules.catalog_models import Product
        catalog = [{"product_id": p.id, "sku": p.sku, "name": p.name}
                   for p in db.query(Product).filter(Product.vendor_id == vendor.id, Product.status == "ACTIVE").all()]
        llm = llm_extract(text, catalog)
        if llm:
            llm_used = True
            llm_conf = float(llm.get("confidence") or 0)
            if llm.get("customer_name") and not name:
                name = llm["customer_name"]
            if llm.get("customer_phone") and not phones:
                norm = re.sub(r"\D", "", str(llm["customer_phone"]))
                if norm.startswith("234"):
                    norm = "0" + norm[3:]
                if len(norm) == 11:
                    phones = [norm]
            if llm.get("quantity") and not qty:
                try:
                    qty = int(llm["quantity"])
                except (TypeError, ValueError):
                    pass
            if llm.get("state") and not place["state"]:
                place["state"] = llm["state"]
            if llm.get("city") and not place["city"]:
                place["city"] = llm["city"]
            if llm.get("intent") and intent in ("GENERAL_MESSAGE", "UNKNOWN_INTENT"):
                intent = llm["intent"]
                intent_conf = max(intent_conf, 0.6)
            if not resolved and llm.get("product_query"):
                extra = match_products(db, vendor.id, llm["product_query"])
                if extra:
                    candidates = extra + [c for c in candidates if c not in extra]
                    if extra[0]["score"] >= 85:
                        resolved = extra[0]

    missing = []
    if not name:
        missing.append("customer_name")
    if not phones:
        missing.append("customer_phone")
    if not resolved:
        missing.append("product")
    if not qty:
        missing.append("quantity")
    if not (place["city"] or place["state"]):
        missing.append("delivery_address")

    confidence = (
        (0.25 if phones else 0) +
        (0.15 if name else 0) +
        (0.30 if resolved else (0.12 if candidates else 0)) +
        (0.15 if qty else 0) +
        (0.05 if amounts else 0) +
        (0.10 if (place["city"] or place["state"]) else 0)
    )
    if resolved is None and candidates:
        confidence *= 0.85
    if llm_used:
        confidence = max(confidence, llm_conf * 0.9)
    confidence = round(min(confidence, 0.99), 2)

    return {
        "intent": intent,
        "intent_confidence": round(intent_conf, 2),
        "customer_name": name,
        "customer_phone": phones[0] if phones else None,
        "customer_phone_alt": phones[1] if len(phones) > 1 else None,
        "quantity": qty,
        "amount_kobo": amounts[0] if amounts else None,
        "state": place["state"],
        "city": place["city"],
        "order_ref": order_ref,
        "product": resolved,
        "candidates": candidates,
        "missing": missing,
        "confidence": confidence,
        "llm_used": llm_used,
    }
