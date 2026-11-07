"""Switching parts of the product on or off, and one place that decides who may read what."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.audit import audit
from app.core.deps import bearer, get_current_user, get_user_permissions, require_perm
from app.modules.appearance_models import AppSetting
from app.modules.identity_models import User

router = APIRouter(prefix="/api", tags=["modules"])

# key -> (name, what it covers). Everything else (orders, products, stock, vendors, customers, settings) is always on.
MODULES = {
    "whatsapp": ("WhatsApp inbox and order drafts", "Messages from vendors, order drafts made from messages, and the WhatsApp settings."),
    "confirmations": ("Customer confirmations", "The queue for calling customers to confirm orders before dispatch."),
    "dispatch": ("Dispatch and delivery", "Riders, carriers, delivery zones and delivery tracking."),
    "cod": ("Cash on delivery", "Checking and recording cash collected from customers and riders."),
    "settlements": ("Vendor settlements", "Paying vendors what they are owed."),
    "finance": ("Finance and books", "Accounts, entries, expenses and bank records."),
    "reports": ("Reports", "Performance and money reports with downloads."),
    "audit": ("Activity log", "The record of who did what and when."),
    "portal": ("Vendor portal", "The separate area where vendors see their own orders, stock and statements."),
}

# path prefix -> (module or None, permissions where holding ANY one allows reading)
RULES: list[tuple[str, str | None, list[str]]] = [
    ("/api/conversations", "whatsapp", ["conversations.view", "conversations.manage"]),
    ("/api/whatsapp", "whatsapp", ["conversations.view", "conversations.manage", "whatsapp.manage", "settings.manage"]),
    ("/api/orders/drafts", "whatsapp", ["orders.view", "orders.manage"]),
    ("/api/confirmations", "confirmations", ["confirmations.manage", "orders.view"]),
    ("/api/orders", None, ["orders.view", "orders.manage", "confirmations.manage", "dispatch.view", "cod.manage",
                           "settlements.manage", "finance.manage"]),
    ("/api/customers", None, ["orders.view", "orders.manage", "confirmations.manage"]),
    ("/api/dispatch", "dispatch", ["dispatch.view", "dispatch.manage", "orders.view", "orders.manage"]),
    ("/api/cod", "cod", []),
    ("/api/settlements", "settlements", []),
    ("/api/ledger", "finance", []),
    ("/api/reports", "reports", []),
    ("/api/audit", "audit", []),
    ("/api/portal", "portal", []),
    ("/api/vendors", None, ["vendors.view", "vendors.manage", "orders.view", "orders.manage", "catalog.view",
                            "inventory.view", "settlements.manage", "finance.manage", "conversations.view",
                            "conversations.manage"]),
    ("/api/catalog", None, ["catalog.view", "catalog.manage", "orders.view", "orders.manage", "inventory.view"]),
    ("/api/inventory", None, ["inventory.view", "inventory.manage", "orders.view", "orders.manage", "catalog.view"]),
    ("/api/charges", None, ["charges.manage", "orders.view", "orders.manage", "settings.manage"]),
    ("/api/users", None, ["settings.manage", "conversations.view", "conversations.manage", "orders.view"]),
    ("/api/roles", None, ["settings.manage"]),
    ("/api/notification-rules", None, ["settings.manage"]),
]
OPEN_PATHS = ("/webhook", "/assignments/me")


def module_states(db: Session) -> dict[str, bool]:
    row = db.get(AppSetting, "modules")
    saved = row.value if row and isinstance(row.value, dict) else {}
    return {k: bool(saved.get(k, True)) for k in MODULES}


def _rule_for(path: str):
    best = None
    for prefix, module, perms in RULES:
        if (path == prefix or path.startswith(prefix + "/")) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, module, perms)
    return best


def access_gate(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                db: Session = Depends(get_db)):
    """App-wide check: switched-off features are gone for everyone, and reads need a matching permission."""
    path = request.url.path.rstrip("/")
    if request.method == "OPTIONS" or any(path.endswith(p) for p in OPEN_PATHS):
        return
    rule = _rule_for(path)
    if not rule:
        return
    _, module, perms = rule
    if module and not module_states(db).get(module, True):
        raise HTTPException(404, "This feature is turned off")
    if request.method in ("GET", "HEAD") and perms:
        user = get_current_user(creds, db)
        if user.is_vendor or user.is_superuser:
            return
        if not (get_user_permissions(db, user) & set(perms)):
            raise HTTPException(403, "You do not have access to this")


@router.get("/settings/modules")
def get_modules(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    st = module_states(db)
    return {"modules": [{"key": k, "name": v[0], "description": v[1], "enabled": st[k]} for k, v in MODULES.items()]}


class ModulesIn(BaseModel):
    enabled: dict[str, bool]


@router.put("/settings/modules")
def save_modules(body: ModulesIn, user: User = Depends(require_perm("settings.manage")), db: Session = Depends(get_db)):
    unknown = [k for k in body.enabled if k not in MODULES]
    if unknown:
        raise HTTPException(400, f"Unknown feature: {unknown[0]}")
    cur = module_states(db)
    cur.update(body.enabled)
    row = db.get(AppSetting, "modules")
    if row:
        row.value = cur
        row.updated_by = user.full_name or user.email
    else:
        db.add(AppSetting(key="modules", value=cur, updated_by=user.full_name or user.email))
    off = [MODULES[k][0] for k, v in cur.items() if not v]
    audit(db, user, "update", "setting", "modules", "Switched off: " + (", ".join(off) or "nothing"))
    db.commit()
    return get_modules(user, db)
