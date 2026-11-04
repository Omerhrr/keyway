"""Notification engine (PRD: notifications_and_automation).

Rules:
- Automation must be idempotent -> dedup_key on (event_type, entity) rows.
- Failed notifications must be retryable -> status FAILED + /retry endpoint.
- Important actions must be logged -> callers use app.core.audit separately.
- Financial actions are never triggered by notifications (display only).
"""
from app.core.db import utcnow
from app.modules.activity_models import Notification, NotificationRule

# Event catalog shown in Settings -> Notifications (label + default audience hint).
EVENT_CATALOG = [
    {"event_type": "NEW_WHATSAPP_ORDER", "label": "New WhatsApp order detected", "audience": "Staff"},
    {"event_type": "ORDER_CREATED", "label": "Order registered", "audience": "Vendor + staff"},
    {"event_type": "ORDER_CHANGE_REQUEST", "label": "Customer requested an order change", "audience": "Staff"},
    {"event_type": "ORDER_DISPATCHED", "label": "Order dispatched", "audience": "Vendor"},
    {"event_type": "ORDER_DELIVERED", "label": "Order delivered", "audience": "Vendor"},
    {"event_type": "DELIVERY_FAILED", "label": "Delivery failed", "audience": "Managers"},
    {"event_type": "COD_RECORDED", "label": "COD collection recorded", "audience": "Finance"},
    {"event_type": "COD_DISCREPANCY", "label": "COD amount discrepancy", "audience": "Finance"},
    {"event_type": "SETTLEMENT_READY", "label": "Vendor settlement ready", "audience": "Vendor + finance"},
    {"event_type": "SETTLEMENT_PAID", "label": "Vendor settlement paid", "audience": "Vendor"},
    {"event_type": "UNASSIGNED_SENDER", "label": "Unrecognized WhatsApp sender", "audience": "Staff"},
    {"event_type": "LOW_STOCK", "label": "Stock at or below reorder level", "audience": "Warehouse"},
    {"event_type": "ORDER_UNCONFIRMED", "label": "Order awaiting customer confirmation", "audience": "Staff"},
]
EVENT_TYPES = [e["event_type"] for e in EVENT_CATALOG]


def _dedup_exists(db, key: str) -> bool:
    if not key:
        return False
    return db.query(Notification).filter(Notification.dedup_key == key,
                                          Notification.status.in_(["UNREAD", "SENT"])).first() is not None


def _deliver_external(db, channel: str, n: Notification) -> str:
    """Attempt the real channel send. WhatsApp uses the Cloud API when configured;
    other channels are accepted but simulated until their providers are wired up."""
    if channel == "WHATSAPP":
        try:
            from app.modules import whatsapp_cloud
            phone = ""
            if n.vendor_id:
                from app.modules.vendors_models import Vendor
                v = db.get(Vendor, n.vendor_id)
                phone = v.phone if v else ""
            elif n.user_id:
                from app.modules.identity_models import User
                u = db.get(User, n.user_id)
                phone = u.phone if u else ""
            if not phone:
                return "FAILED"
            whatsapp_cloud.send_text(db, phone, f"{n.title}\n{n.body}".strip())
            return "SENT"
        except Exception:
            return "FAILED"
    return "SENT"


def notify(db, *, event_type: str, title: str, body: str = "", user_id=None, vendor_id=None,
           conversation_id=None, entity_type: str = "", entity_id=None, channel: str = "IN_APP",
           dedup_key: str | None = None):
    """Create notification rows, routed by enabled NotificationRule rows.

    - explicit vendor_id  -> one row for the vendor portal (any channel).
    - explicit user_id    -> one row for that user (any channel).
    - otherwise           -> rules for event_type; no matching rule = ALL_STAFF in-app.
    Idempotent: a live row with the same dedup key suppresses duplicates.
    """
    key = dedup_key
    if key is None and entity_id is not None:
        key = f"{event_type}:{entity_type}:{entity_id}"
    if vendor_id or user_id or not db.query(NotificationRule).filter(
            NotificationRule.event_type == event_type, NotificationRule.enabled.is_(True)).count():
        if _dedup_exists(db, key or f"{event_type}:{entity_type}:{entity_id or 'x'}"):
            return None
        n = Notification(channel=channel, user_id=user_id, vendor_id=vendor_id,
                         conversation_id=conversation_id, event_type=event_type, title=title,
                         body=body, entity_type=entity_type,
                         entity_id=str(entity_id) if entity_id is not None else None,
                         dedup_key=key or "", retries=0)
        if channel != "IN_APP":
            n.status = _deliver_external(db, channel, n)
        else:
            n.status = "UNREAD"
        db.add(n)
        return n

    from app.modules.identity_models import User, Role
    rules = db.query(NotificationRule).filter(
        NotificationRule.event_type == event_type, NotificationRule.enabled.is_(True)).all()
    created = []
    for rule in rules:
        ch = rule.channel or "IN_APP"
        targets: list[int | None]
        if rule.target_scope == "USER":
            targets = [rule.user_id] if rule.user_id else []
        elif rule.target_scope == "ROLE":
            if not rule.role_name:
                continue
            targets = [u.id for u in db.query(User).join(Role, User.role_id == Role.id)
                       .filter(Role.name == rule.role_name, User.is_active.is_(True)).all()]
        else:
            targets = [None]  # staff-wide row (user_id NULL)
        for uid in targets:
            row_key = f"{key}:u{uid}" if key else ""
            if _dedup_exists(db, row_key or f"{event_type}:{entity_type}:{entity_id or 'x'}:u{uid}"):
                continue
            n = Notification(channel=ch, user_id=uid, vendor_id=None,
                             conversation_id=conversation_id, event_type=event_type, title=title,
                             body=body, entity_type=entity_type,
                             entity_id=str(entity_id) if entity_id is not None else None,
                             dedup_key=row_key, retries=0,
                             status="UNREAD" if ch == "IN_APP" else "SENT")
            if ch != "IN_APP":
                n.status = _deliver_external(db, ch, n)
            db.add(n)
            created.append(n)
    return created or None


def retry_notification(db, n: Notification) -> bool:
    """PRD: failed notifications must be retryable."""
    if n.status != "FAILED":
        return False
    n.retries = (n.retries or 0) + 1
    n.status = _deliver_external(db, n.channel, n) if n.channel != "IN_APP" else "UNREAD"
    return True


def run_automation_checks(db) -> dict:
    """Idempotent background checks: low stock + orders stuck awaiting confirmation.
    Safe to run repeatedly - dedup keys stop duplicate alerts while a previous
    alert is still unread."""
    from app.modules.inventory_models import InventoryBalance
    from app.modules.catalog_models import Product
    from app.modules.vendors_models import Vendor

    created = {"LOW_STOCK": 0, "ORDER_UNCONFIRMED": 0}

    # ---- low stock: available <= reorder level per product+warehouse ----
    rows = (db.query(InventoryBalance, Product, Vendor)
            .join(Product, Product.id == InventoryBalance.product_id)
            .join(Vendor, Vendor.id == Product.vendor_id).all())
    for b, p, v in rows:
        available = b.qty_physical - b.qty_reserved
        if available > p.reorder_level:
            continue
        key = f"LOW_STOCK:product:{p.id}:wh:{b.warehouse_id}"
        if _dedup_exists(db, key):
            continue
        db.add(Notification(channel="IN_APP", user_id=None, event_type="LOW_STOCK",
                            title=f"Low stock: {p.name}",
                            body=f"{v.name}: {available} available at warehouse (reorder level {p.reorder_level})",
                            entity_type="inventory_balance", entity_id=str(b.id), dedup_key=key))
        created["LOW_STOCK"] += 1

    # ---- orders awaiting confirmation (vendor or customer) - PRD automation ----
    from app.modules.orders_models import Order
    stuck = db.query(Order).filter(
        Order.status.in_(["PENDING_VENDOR_CONFIRMATION", "PENDING_CUSTOMER_CONFIRMATION"])
    ).limit(50).all()
    for o in stuck:
        key = f"ORDER_UNCONFIRMED:order:{o.id}"
        if _dedup_exists(db, key):
            continue
        db.add(Notification(channel="IN_APP", user_id=None, event_type="ORDER_UNCONFIRMED",
                            title=f"Order {o.reference} awaiting confirmation",
                            body="Customer confirmation is still pending - follow up with the customer.",
                            entity_type="order", entity_id=str(o.id), dedup_key=key))
        created["ORDER_UNCONFIRMED"] += 1

    db.commit()
    return created
