from sqlalchemy.orm import Session
from typing import Any

from app.models.audit_event import AuditEvent
from app.models.user import User


def log_event(
    *,
    db: Session,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id,
    metadata: dict[str, Any] | None = None,
):
    event = AuditEvent(
        actor_user_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        event_metadata=metadata,
    )
    db.add(event)
