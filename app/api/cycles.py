from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.core.rbac import require_roles
from app.db.session import get_db
from app.models.review_cycle import ReviewCycle
from app.models.user import User
from app.schemas.review_cycle import ReviewCycleCreate, ReviewCycleUpdate, ReviewCycleOut
from app.core.audit import log_event

router = APIRouter(prefix="/cycles", tags=["review-cycles"])


def to_out(c: ReviewCycle) -> ReviewCycleOut:
    return ReviewCycleOut(
        id=str(c.id),
        name=c.name,
        start_date=c.start_date,
        end_date=c.end_date,
        status=c.status,
        created_by_user_id=str(c.created_by_user_id),
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


@router.get("", response_model=list[ReviewCycleOut])
def list_cycles(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cycles = db.query(ReviewCycle).order_by(ReviewCycle.created_at.desc()).all()
    return [to_out(c) for c in cycles]


@router.get("/{cycle_id}", response_model=ReviewCycleOut)
def get_cycle(
    cycle_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    c = db.get(ReviewCycle, cycle_id)
    if not c:
        raise HTTPException(status_code=404, detail="Cycle not found")
    return to_out(c)


@router.post("", response_model=ReviewCycleOut, status_code=status.HTTP_201_CREATED)
def create_cycle(
    payload: ReviewCycleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    c = ReviewCycle(
        name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status="DRAFT",
        created_by_user_id=current_user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(c)
    db.flush()

    log_event(
        db=db,
        actor=current_user,
        action="CYCLE_CREATED",
        entity_type="review_cycle",
        entity_id=c.id,
        metadata={
            "name": payload.name,
            "start_date": str(payload.start_date),
            "end_date": str(payload.end_date),
            "status": "DRAFT",
        },
    )

    db.commit()
    db.refresh(c)
    return to_out(c)


@router.patch("/{cycle_id}", response_model=ReviewCycleOut)
def update_cycle(
    cycle_id: str,
    payload: ReviewCycleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    c = db.get(ReviewCycle, cycle_id)
    if not c:
        raise HTTPException(status_code=404, detail="Cycle not found")

    if c.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only DRAFT cycles can be updated")

    before = {"name": c.name, "start_date": str(c.start_date), "end_date": str(c.end_date), "status": c.status}

    if payload.name is not None:
        c.name = payload.name
    # NOTE: your original code had `or payload.start_date is None` which always evaluates True.
    # This is the correct nullable-update pattern:
    if payload.start_date is not None:
        c.start_date = payload.start_date
    if payload.end_date is not None:
        c.end_date = payload.end_date

    c.updated_at = datetime.utcnow()

    log_event(
        db=db,
        actor=current_user,
        action="CYCLE_UPDATED",
        entity_type="review_cycle",
        entity_id=c.id,
        metadata={
            "before": before,
            "after": {"name": c.name, "start_date": str(c.start_date), "end_date": str(c.end_date), "status": c.status},
        },
    )

    db.commit()
    db.refresh(c)
    return to_out(c)


@router.post("/{cycle_id}/activate", response_model=ReviewCycleOut)
def activate_cycle(
    cycle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    c = db.get(ReviewCycle, cycle_id)
    if not c:
        raise HTTPException(status_code=404, detail="Cycle not found")

    if c.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only DRAFT cycles can be activated")

    prev = c.status
    c.status = "ACTIVE"
    c.updated_at = datetime.utcnow()

    log_event(
        db=db,
        actor=current_user,
        action="CYCLE_ACTIVATED",
        entity_type="review_cycle",
        entity_id=c.id,
        metadata={"from": prev, "to": c.status},
    )

    db.commit()
    db.refresh(c)
    return to_out(c)


@router.post("/{cycle_id}/close", response_model=ReviewCycleOut)
def close_cycle(
    cycle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    c = db.get(ReviewCycle, cycle_id)
    if not c:
        raise HTTPException(status_code=404, detail="Cycle not found")

    if c.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Only ACTIVE cycles can be closed")

    prev = c.status
    c.status = "CLOSED"
    c.updated_at = datetime.utcnow()

    log_event(
        db=db,
        actor=current_user,
        action="CYCLE_CLOSED",
        entity_type="review_cycle",
        entity_id=c.id,
        metadata={"from": prev, "to": c.status},
    )

    db.commit()
    db.refresh(c)
    return to_out(c)
