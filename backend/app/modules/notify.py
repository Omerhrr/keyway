"""In-app notification helper (channel routing is simulated for other channels)."""
from app.core.db import utcnow
from app.modules.activity_models import Notification


def notify(db, *, event_type: str, title: str, body: str = "", user_id=None, vendor_id=None,
           conversation_id=None, entity_type: str = "", entity_id=None, channel: str = "IN_APP"):
    n = Notification(channel=channel, user_id=user_id, vendor_id=vendor_id,
                     conversation_id=conversation_id, event_type=event_type, title=title,
                     body=body, entity_type=entity_type,
                     entity_id=str(entity_id) if entity_id is not None else None,
                     status="UNREAD" if channel == "IN_APP" else "SENT")
    db.add(n)
    return n
