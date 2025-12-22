from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    _: User = Depends(get_current_user),
):
    # Must exist
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
    _: User = Depends(require_roles("ADMIN")),
):
    cycle = db.get(ReviewCycle, cycle_id)
    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")

    # Optional rule: only allow bulk assignment while cycle is DRAFT
    # (I recommend this to avoid chaos mid-cycle)
    if cycle.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Assignments can only be created while cycle is DRAFT")

    # Validate referenced employees exist
    ids = set()
    for item in payload.items:
        ids.update([item.reviewer_employee_id, item.subject_employee_id, item.approver_employee_id])

    existing = {str(e.id) for e in db.query(Employee.id).filter(Employee.id.in_(list(ids))).all()}
    missing = [eid for eid in ids if eid not in existing]
    if missing:
        raise HTTPException(status_code=400, detail={"missing_employee_ids": missing})

    created: list[ReviewAssignment] = []

    try:
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

        db.commit()
    except IntegrityError:
        db.rollback()
        # Most likely uniqueness violation (duplicate assignment)
        raise HTTPException(status_code=409, detail="Duplicate assignment(s) detected for this cycle")

    # refresh to get ids/timestamps
    for a in created:
        db.refresh(a)

    return [to_out(a) for a in created]
