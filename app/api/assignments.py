from fastapi import APIRouter, Depends, HTTPException, Query, status, Header
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.rbac import require_roles
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.review_cycle import ReviewCycle
from app.models.review_assignment import ReviewAssignment
from app.models.employee import Employee
from app.models.user import User
from app.schemas.review_assignment import AssignmentBulkCreate, AssignmentOut
from app.core.audit import log_event
from app.core.idempotency import (
    begin_idempotent_request,
    complete_idempotent_request,
    fail_idempotent_request,
)

router = APIRouter(prefix="/cycles/{cycle_id}/assignments", tags=["assignments"])


def to_out(a: ReviewAssignment) -> AssignmentOut:
    return AssignmentOut(
        id=str(a.id),
        cycle_id=str(a.cycle_id),
        reviewer_employee_id=str(a.reviewer_employee_id),
        subject_employee_id=str(a.subject_employee_id),
        approver_employee_id=str(a.approver_employee_id),
        status=a.status,
        created_at=a.created_at,
    )


@router.get("", response_model=list[AssignmentOut])
def list_assignments(
    cycle_id: str,
    reviewer_employee_id: str | None = Query(default=None),
    subject_employee_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),  # tightened: admin-only for now
):
    cycle = db.get(ReviewCycle, cycle_id)
    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")

    q = db.query(ReviewAssignment).filter(ReviewAssignment.cycle_id == cycle_id)

    if reviewer_employee_id:
        q = q.filter(ReviewAssignment.reviewer_employee_id == reviewer_employee_id)
    if subject_employee_id:
        q = q.filter(ReviewAssignment.subject_employee_id == subject_employee_id)
    if status_filter:
        q = q.filter(ReviewAssignment.status == status_filter)

    rows = q.order_by(ReviewAssignment.created_at.desc()).all()
    return [to_out(r) for r in rows]


@router.post("/bulk", response_model=list[AssignmentOut], status_code=status.HTTP_201_CREATED)
def bulk_create_assignments(
    cycle_id: str,
    payload: AssignmentBulkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    cycle = db.get(ReviewCycle, cycle_id)
    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")

    if cycle.status != "DRAFT":
        raise HTTPException(
            status_code=409,
            detail="Assignments can only be created while cycle is DRAFT",
        )

    # ---- idempotency (recommended for bulk) ----
    idem_row = None
    if idempotency_key:
        idem_row, _ = begin_idempotent_request(
            db=db,
            user=current_user,
            key=idempotency_key,
            method="POST",
            route="/cycles/{cycle_id}/assignments/bulk",
            payload_for_hash={
                "cycle_id": cycle_id,
                # make hashing deterministic even if client order changes slightly
                "items": sorted([i.model_dump() for i in payload.items], key=lambda x: (
                    x["reviewer_employee_id"],
                    x["subject_employee_id"],
                    x["approver_employee_id"],
                )),
            },
        )
        if idem_row.status == "COMPLETED":
            return [AssignmentOut(**row) for row in (idem_row.response_body or [])]

    # Validate employee ids exist (avoid FK errors with opaque messages)
    ids: set[str] = set()
    for item in payload.items:
        ids.update([item.reviewer_employee_id, item.subject_employee_id, item.approver_employee_id])

    existing_ids = {
        str(r[0]) for r in db.query(Employee.id).filter(Employee.id.in_(list(ids))).all()
    }
    missing = sorted([eid for eid in ids if eid not in existing_ids])
    if missing:
        raise HTTPException(status_code=400, detail={"missing_employee_ids": missing})

    created: list[ReviewAssignment] = []

    try:
        # One atomic unit: assignments + audits (+ optional idempotency completion)
        with db.begin_nested():
            for item in payload.items:
                a = ReviewAssignment(
                    cycle_id=cycle.id,
                    reviewer_employee_id=item.reviewer_employee_id,
                    subject_employee_id=item.subject_employee_id,
                    approver_employee_id=item.approver_employee_id,
                    status="ACTIVE",
                )
                db.add(a)
                created.append(a)

            # get IDs before writing audits
            db.flush()

            for a in created:
                log_event(
                    db=db,
                    actor=current_user,
                    action="ASSIGNMENT_CREATED",
                    entity_type="review_assignment",
                    entity_id=a.id,
                    metadata={
                        "cycle_id": str(a.cycle_id),
                        "reviewer_employee_id": str(a.reviewer_employee_id),
                        "subject_employee_id": str(a.subject_employee_id),
                        "approver_employee_id": str(a.approver_employee_id),
                    },
                )

            out = [to_out(a) for a in created]

            if idem_row:
                complete_idempotent_request(
                    db=db,
                    row=idem_row,
                    response_code=201,
                    response_body=[o.model_dump(mode="json") for o in out],
                )

        return out

    except IntegrityError:
        # NOTE: dependency get_db will rollback, but rollback here is fine too
        if idem_row:
            with db.begin_nested():
                fail_idempotent_request(db=db, row=idem_row)
        raise HTTPException(
            status_code=409,
            detail="Duplicate assignment(s) detected for this cycle",
        )
    except Exception:
        if idem_row:
            with db.begin_nested():
                fail_idempotent_request(db=db, row=idem_row)
        raise
