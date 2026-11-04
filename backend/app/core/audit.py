from app.modules.activity import AuditLog


def audit(db, actor_user, action: str, entity_type: str, entity_id=None, summary: str = "", data: dict | None = None, ip: str | None = None):
    """Record an audit trail entry. Never raises (audit must not break operations)."""
    try:
        db.add(AuditLog(
            actor_user_id=actor_user.id if actor_user else None,
            actor_label=(actor_user.full_name or actor_user.email) if actor_user else "system",
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            summary=summary,
            data=(data or {}),
            ip=ip,
        ))
    except Exception:
        pass
