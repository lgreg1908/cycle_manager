from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.rbac import require_roles
from app.db.session import get_db
from app.models.audit_event import AuditEvent

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def list_audit_events(
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    _=Depends(require_roles("ADMIN")),
):
    q = db.query(AuditEvent)

    if entity_type:
        q = q.filter(AuditEvent.entity_type == entity_type)
    if entity_id:
        q = q.filter(AuditEvent.entity_id == entity_id)

    rows = q.order_by(AuditEvent.created_at.desc()).limit(limit).all()

    return [
        {
            "id": str(r.id),
            "actor_user_id": str(r.actor_user_id) if r.actor_user_id else None,
            "action": r.action,
            "entity_type": r.entity_type,
            "entity_id": str(r.entity_id),
            "metadata": r.event_metadata,
            "created_at": r.created_at,
        }
        for r in rows
    ]
