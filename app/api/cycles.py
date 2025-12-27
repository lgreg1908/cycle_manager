from typing import Union
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.security import get_current_user
from app.core.rbac import require_roles
from app.db.session import get_db
from app.models.review_cycle import ReviewCycle
from app.models.review_assignment import ReviewAssignment
from app.models.form_template import FormTemplate
from app.models.form_template_field import FormTemplateField
from app.models.user import User
from app.schemas.review_cycle import ReviewCycleCreate, ReviewCycleUpdate, ReviewCycleOut
from app.schemas.pagination import PaginatedResponse, PaginationMeta
from app.schemas.cycle_readiness import CycleReadinessCheck
from app.schemas.stats import CycleStats
from app.models.evaluation import Evaluation
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
        form_template_id=str(c.form_template_id) if c.form_template_id else None,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


@router.get("")
def list_cycles(
    search: str | None = Query(default=None, description="Search by name"),
    status: str | None = Query(default=None, description="Filter by status (DRAFT, ACTIVE, CLOSED, ARCHIVED)"),
    limit: int = Query(default=100, ge=1, le=500, description="Maximum number of results"),
    offset: int = Query(default=0, ge=0, description="Number of results to skip"),
    include_pagination: bool = Query(default=False, description="Include pagination metadata"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    List all review cycles with optional search and filtering.
    
    Use ?include_pagination=true to get pagination metadata.
    """
    query = db.query(ReviewCycle)
    
    if search:
        search_term = f"%{search.lower()}%"
        query = query.filter(ReviewCycle.name.ilike(search_term))
    
    if status:
        query = query.filter(ReviewCycle.status == status)
    
    # Get total count before pagination
    total = query.count()
    
    # Apply pagination
    cycles = query.order_by(ReviewCycle.created_at.desc()).offset(offset).limit(limit).all()
    items = [to_out(c) for c in cycles]
    
    if include_pagination:
        return PaginatedResponse(
            items=items,
            pagination=PaginationMeta(
                total=total,
                limit=limit,
                offset=offset,
                has_more=(offset + len(items) < total),
            ),
        )
    return items


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
    )

    db.add(c)
    db.flush()  # ensures c.id exists for audit

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

    before = {
        "name": c.name,
        "start_date": str(c.start_date),
        "end_date": str(c.end_date),
        "status": c.status,
    }

    if payload.name is not None:
        c.name = payload.name
    if payload.start_date is not None:
        c.start_date = payload.start_date
    if payload.end_date is not None:
        c.end_date = payload.end_date

    log_event(
        db=db,
        actor=current_user,
        action="CYCLE_UPDATED",
        entity_type="review_cycle",
        entity_id=c.id,
        metadata={
            "before": before,
            "after": {
                "name": c.name,
                "start_date": str(c.start_date),
                "end_date": str(c.end_date),
                "status": c.status,
            },
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

    # Idempotent success: if already ACTIVE, just return it
    if c.status == "ACTIVE":
        return to_out(c)

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

    # Idempotent success: if already CLOSED, return it
    if c.status == "CLOSED":
        return to_out(c)

    if c.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Only ACTIVE cycles can be closed")

    prev = c.status
    c.status = "CLOSED"

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


@router.post("/{cycle_id}/set-form/{form_template_id}", response_model=ReviewCycleOut)
def set_cycle_form_template(
    cycle_id: str,
    form_template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    c = db.get(ReviewCycle, cycle_id)
    if not c:
        raise HTTPException(status_code=404, detail="Cycle not found")

    form = db.get(FormTemplate, form_template_id)
    if not form or not form.is_active:
        raise HTTPException(status_code=404, detail="Form template not found or inactive")

    before = {"form_template_id": str(c.form_template_id) if c.form_template_id else None}

    c.form_template_id = form.id
    c.updated_at = datetime.utcnow()

    log_event(
        db=db,
        actor=current_user,
        action="CYCLE_FORM_TEMPLATE_SET",
        entity_type="review_cycle",
        entity_id=c.id,
        metadata={"before": before, "after": {"form_template_id": str(form.id)}},
    )

    db.commit()
    db.refresh(c)
    return to_out(c)


@router.get("/{cycle_id}/readiness", response_model=CycleReadinessCheck)
def check_cycle_readiness(
    cycle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """
    Check if a cycle is ready to be activated.
    Returns detailed checks, warnings, and errors.
    """
    cycle = db.get(ReviewCycle, cycle_id)
    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")

    checks: dict[str, bool] = {}
    warnings: list[str] = []
    errors: list[str] = []

    # Check 1: Cycle must be in DRAFT status
    checks["is_draft"] = cycle.status == "DRAFT"
    if not checks["is_draft"]:
        errors.append(f"Cycle is in {cycle.status} status, must be DRAFT to activate")

    # Check 2: Form template must be assigned
    checks["has_form_template"] = cycle.form_template_id is not None
    if not checks["has_form_template"]:
        errors.append("Cycle has no form template assigned")

    # Check 3: Form template must be active
    if cycle.form_template_id:
        form = db.get(FormTemplate, cycle.form_template_id)
        checks["form_template_active"] = form is not None and form.is_active
        if not checks["form_template_active"]:
            errors.append("Assigned form template is not active or not found")
        elif form:
            # Check 4: Form template must have at least one field
            field_count = db.query(FormTemplateField).filter(
                FormTemplateField.form_template_id == form.id
            ).count()
            checks["form_has_fields"] = field_count > 0
            if not checks["form_has_fields"]:
                errors.append("Form template has no fields defined")

    # Check 5: Cycle must have at least one assignment
    assignment_count = db.query(ReviewAssignment).filter(
        ReviewAssignment.cycle_id == cycle.id
    ).count()
    checks["has_assignments"] = assignment_count > 0
    if not checks["has_assignments"]:
        errors.append("Cycle has no review assignments")

    # Warnings (non-blocking)
    if cycle.start_date is None:
        warnings.append("Cycle has no start date set")
    if cycle.end_date is None:
        warnings.append("Cycle has no end date set")
    if cycle.start_date and cycle.end_date and cycle.start_date > cycle.end_date:
        warnings.append("Start date is after end date")

    # Determine if cycle can be activated
    can_activate = all(checks.values()) and len(errors) == 0
    ready = can_activate and len(warnings) == 0

    return CycleReadinessCheck(
        ready=ready,
        can_activate=can_activate,
        checks=checks,
        warnings=warnings,
        errors=errors,
    )


@router.get("/{cycle_id}/stats", response_model=CycleStats)
def get_cycle_stats(
    cycle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get statistics for a review cycle including completion rates.
    """
    cycle = db.get(ReviewCycle, cycle_id)
    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")

    # Get assignments
    assignments = db.query(ReviewAssignment).filter(ReviewAssignment.cycle_id == cycle.id).all()
    total_assignments = len(assignments)
    active_assignments = sum(1 for a in assignments if a.status == "ACTIVE")
    inactive_assignments = total_assignments - active_assignments

    # Get evaluations
    evaluations = db.query(Evaluation).filter(Evaluation.cycle_id == cycle.id).all()
    total_evaluations = len(evaluations)

    # Calculate evaluation stats by status
    evaluations_by_status: dict[str, int] = {}
    for eval in evaluations:
        evaluations_by_status[eval.status] = evaluations_by_status.get(eval.status, 0) + 1

    # Calculate completion rate (assignments with evaluations)
    assignments_with_evaluations = len(set(e.assignment_id for e in evaluations))
    completion_rate = (assignments_with_evaluations / total_assignments * 100) if total_assignments > 0 else 0.0

    # Calculate submitted rate
    submitted_count = evaluations_by_status.get("SUBMITTED", 0) + evaluations_by_status.get("APPROVED", 0) + evaluations_by_status.get("RETURNED", 0)
    submitted_rate = (submitted_count / total_evaluations * 100) if total_evaluations > 0 else 0.0

    # Calculate approved rate
    approved_count = evaluations_by_status.get("APPROVED", 0)
    approved_rate = (approved_count / total_evaluations * 100) if total_evaluations > 0 else 0.0

    return CycleStats(
        cycle_id=str(cycle.id),
        cycle_name=cycle.name,
        cycle_status=cycle.status,
        total_assignments=total_assignments,
        active_assignments=active_assignments,
        inactive_assignments=inactive_assignments,
        total_evaluations=total_evaluations,
        evaluations_by_status=evaluations_by_status,
        completion_rate=round(completion_rate, 2),
        submitted_rate=round(submitted_rate, 2),
        approved_rate=round(approved_rate, 2),
    )