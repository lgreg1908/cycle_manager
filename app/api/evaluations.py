from typing import Union
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Header, Response, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy import func

from app.core.access import assert_user_is_approver, assert_user_is_reviewer, get_employee_for_user
from app.core.audit import log_event
from app.core.evaluation_form_validation import (
    validate_draft_payload,
    validate_submit_from_db,
)
from app.core.idempotency import (
    begin_idempotent_request,
    complete_idempotent_request,
    fail_idempotent_request,
)
from app.core.optimistic_lock import assert_version_matches, parse_if_match, set_etag
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.evaluation import Evaluation
from app.models.evaluation_response import EvaluationResponse
from app.models.review_assignment import ReviewAssignment
from app.models.review_cycle import ReviewCycle
from app.models.user import User
from app.models.employee import Employee
from app.schemas.evaluation import (
    EvaluationOut,
    EvaluationWithResponsesOut,
    SaveDraftPayload,
)
from app.schemas.expanded import EvaluationOutExpanded
from app.schemas.pagination import PaginatedResponse, PaginationMeta
from app.schemas.validation import ValidationPreviewResponse, ValidationError

router = APIRouter(prefix="/cycles/{cycle_id}", tags=["evaluations"])


def eval_to_out(e: Evaluation) -> EvaluationOut:
    return EvaluationOut(
        id=str(e.id),
        cycle_id=str(e.cycle_id),
        assignment_id=str(e.assignment_id),
        status=e.status,
        submitted_at=e.submitted_at,
        approved_at=e.approved_at,
        created_at=e.created_at,
        updated_at=e.updated_at,
        version=e.version,
    )


def eval_to_out_with_responses(db: Session, e: Evaluation) -> EvaluationWithResponsesOut:
    rows = (
        db.query(EvaluationResponse)
        .filter(EvaluationResponse.evaluation_id == e.id)
        .all()
    )
    return EvaluationWithResponsesOut(
        **eval_to_out(e).model_dump(),
        responses={r.question_key: r.value_text for r in rows},
    )


def _get_cycle_or_404(db: Session, cycle_id: str) -> ReviewCycle:
    cycle = db.get(ReviewCycle, cycle_id)
    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")
    return cycle


def _get_assignment_in_cycle_or_404(
    db: Session, cycle_id: str, assignment_id: str
) -> ReviewAssignment:
    assignment = db.get(ReviewAssignment, assignment_id)
    if not assignment or str(assignment.cycle_id) != cycle_id:
        raise HTTPException(status_code=404, detail="Assignment not found in this cycle")
    return assignment


def _lock_evaluation_in_cycle_or_404(
    db: Session, cycle_id: str, evaluation_id: str
) -> Evaluation:
    e = (
        db.query(Evaluation)
        .filter(Evaluation.id == evaluation_id)
        .with_for_update()
        .one_or_none()
    )
    if not e or str(e.cycle_id) != cycle_id:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return e


@router.post(
    "/assignments/{assignment_id}/evaluation",
    response_model=EvaluationOut,
    status_code=201,
)
def create_or_get_evaluation(
    cycle_id: str,
    assignment_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    cycle = _get_cycle_or_404(db, cycle_id)
    if cycle.status != "ACTIVE":
        raise HTTPException(
            status_code=409,
            detail="Evaluations can only be created/edited while cycle is ACTIVE",
        )

    assignment = _get_assignment_in_cycle_or_404(db, cycle_id, assignment_id)
    assert_user_is_reviewer(db, user, assignment)

    idem_row = None
    if idempotency_key:
        idem_row, _ = begin_idempotent_request(
            db=db,
            user=user,
            key=idempotency_key,
            method="POST",
            route="/cycles/{cycle_id}/assignments/{assignment_id}/evaluation",
            payload_for_hash={"cycle_id": cycle_id, "assignment_id": assignment_id},
        )
        if idem_row.status == "COMPLETED":
            return EvaluationOut(**idem_row.response_body)

    try:
        existing = (
            db.query(Evaluation)
            .filter(Evaluation.assignment_id == assignment.id)
            .one_or_none()
        )
        if existing:
            out = eval_to_out(existing)
        else:
            # Use a SAVEPOINT for the insert so an IntegrityError doesn't poison the whole txn.
            try:
                with db.begin_nested():
                    e = Evaluation(
                        cycle_id=assignment.cycle_id,
                        assignment_id=assignment.id,
                        status="DRAFT"
                    )
                    db.add(e)
                    db.flush()  # may raise IntegrityError if unique constraint hits
            except IntegrityError:
                # Savepoint rolled back; safe to query now.
                existing = (
                    db.query(Evaluation)
                    .filter(Evaluation.assignment_id == assignment.id)
                    .one()
                )
                out = eval_to_out(existing)
            else:
                log_event(
                    db=db,
                    actor=user,
                    action="EVALUATION_CREATED",
                    entity_type="evaluation",
                    entity_id=e.id,
                    metadata={
                        "cycle_id": str(e.cycle_id),
                        "assignment_id": str(e.assignment_id),
                        "status": e.status,
                    },
                )
                out = eval_to_out(e)

        if idem_row:
            complete_idempotent_request(
                db=db,
                row=idem_row,
                response_code=201,
                response_body=out.model_dump(mode="json"),
            )

        return out

    except Exception:
        if idem_row:
            # Best-effort: mark idempotency failed within current session/txn.
            # (Commit/rollback is handled by get_db / test override.)
            fail_idempotent_request(db=db, row=idem_row)
        raise


def _eval_to_out_expanded(e: Evaluation, assignment: ReviewAssignment | None, reviewer: Employee | None, subject: Employee | None, approver: Employee | None) -> EvaluationOutExpanded:
    """Convert evaluation to expanded format with assignment context"""
    return EvaluationOutExpanded(
        id=str(e.id),
        cycle_id=str(e.cycle_id),
        assignment_id=str(e.assignment_id),
        status=e.status,
        submitted_at=e.submitted_at.isoformat() if e.submitted_at else None,
        approved_at=e.approved_at.isoformat() if e.approved_at else None,
        created_at=e.created_at.isoformat() if e.created_at else "",
        updated_at=e.updated_at.isoformat() if e.updated_at else "",
        version=e.version,
        reviewer_employee_id=str(assignment.reviewer_employee_id) if assignment else None,
        reviewer_name=reviewer.display_name if reviewer else None,
        subject_employee_id=str(assignment.subject_employee_id) if assignment else None,
        subject_name=subject.display_name if subject else None,
        approver_employee_id=str(assignment.approver_employee_id) if assignment else None,
        approver_name=approver.display_name if approver else None,
    )


@router.get("/evaluations")
def list_evaluations(
    cycle_id: str,
    assignment_id: str | None = Query(default=None, description="Filter by assignment ID"),
    status: str | None = Query(default=None, description="Filter by status (DRAFT, SUBMITTED, APPROVED, RETURNED)"),
    reviewer_employee_id: str | None = Query(default=None, description="Filter by reviewer employee ID"),
    approver_employee_id: str | None = Query(default=None, description="Filter by approver employee ID"),
    subject_employee_id: str | None = Query(default=None, description="Filter by subject employee ID"),
    expand: str | None = Query(default=None, description="Comma-separated list: 'employees' to include employee names"),
    limit: int = Query(default=100, ge=1, le=500, description="Maximum number of results"),
    offset: int = Query(default=0, ge=0, description="Number of results to skip"),
    include_pagination: bool = Query(default=False, description="Include pagination metadata"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    List evaluations in a cycle with optional filters, pagination, and employee name expansion.
    Non-admin users can only see evaluations they're involved in (as reviewer, approver, or subject).
    
    Use ?expand=employees to include employee names in the response.
    Use ?include_pagination=true to get pagination metadata.
    """
    cycle = _get_cycle_or_404(db, cycle_id)
    
    query = db.query(Evaluation).filter(Evaluation.cycle_id == cycle.id)
    
    # Apply filters
    if assignment_id:
        query = query.filter(Evaluation.assignment_id == assignment_id)
    if status:
        query = query.filter(Evaluation.status == status)
    
    # Determine if we need to join with assignments
    needs_join = False
    if reviewer_employee_id or approver_employee_id or subject_employee_id:
        needs_join = True
    
    # Non-admin users: filter to only their evaluations
    from app.core.rbac import get_user_role_names
    role_names = get_user_role_names(db, user)
    if "ADMIN" not in role_names:
        needs_join = True
    
    expand_employees = expand and "employees" in expand.split(",")
    if expand_employees:
        needs_join = True  # Need assignment to get employee IDs
    
    # Join with assignments if needed
    if needs_join:
        query = query.join(ReviewAssignment, ReviewAssignment.id == Evaluation.assignment_id)
        
        # Employee filters
        if reviewer_employee_id:
            query = query.filter(ReviewAssignment.reviewer_employee_id == reviewer_employee_id)
        if approver_employee_id:
            query = query.filter(ReviewAssignment.approver_employee_id == approver_employee_id)
        if subject_employee_id:
            query = query.filter(ReviewAssignment.subject_employee_id == subject_employee_id)
        
        # Non-admin users: filter to only their evaluations
        if "ADMIN" not in role_names:
            employee = get_employee_for_user(db, user)
            if not employee:
                # User has no employee record, return empty
                if include_pagination:
                    return PaginatedResponse(
                        items=[],
                        pagination=PaginationMeta(total=0, limit=limit, offset=offset, has_more=False),
                    )
                return []
    
    # Get total count before pagination
    total = query.count()
    
    # Apply pagination
    evaluations = query.order_by(Evaluation.created_at.desc()).offset(offset).limit(limit).all()
    
    # Expand employees if requested
    if expand_employees:
        # Get assignments for evaluations
        assignment_ids = [str(e.assignment_id) for e in evaluations]
        assignments = {str(a.id): a for a in db.query(ReviewAssignment).filter(ReviewAssignment.id.in_(assignment_ids)).all()}
        
        # Collect employee IDs
        employee_ids = set()
        for e in evaluations:
            a = assignments.get(str(e.assignment_id))
            if a:
                employee_ids.add(a.reviewer_employee_id)
                employee_ids.add(a.subject_employee_id)
                employee_ids.add(a.approver_employee_id)
        
        # Batch load employees
        employees = {str(e.id): e for e in db.query(Employee).filter(Employee.id.in_(list(employee_ids))).all()}
        
        # Build expanded responses
        items = [
            _eval_to_out_expanded(
                e,
                assignments.get(str(e.assignment_id)),
                employees.get(str(assignments.get(str(e.assignment_id)).reviewer_employee_id)) if assignments.get(str(e.assignment_id)) else None,
                employees.get(str(assignments.get(str(e.assignment_id)).subject_employee_id)) if assignments.get(str(e.assignment_id)) else None,
                employees.get(str(assignments.get(str(e.assignment_id)).approver_employee_id)) if assignments.get(str(e.assignment_id)) else None,
            )
            for e in evaluations
        ]
    else:
        items = [eval_to_out(e) for e in evaluations]
    
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


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationWithResponsesOut)
def get_evaluation(
    cycle_id: str,
    evaluation_id: str,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    e = db.get(Evaluation, evaluation_id)
    if not e or str(e.cycle_id) != cycle_id:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    assignment = _get_assignment_in_cycle_or_404(db, cycle_id, str(e.assignment_id))

    try:
        assert_user_is_reviewer(db, user, assignment)
    except HTTPException:
        assert_user_is_approver(db, user, assignment)

    out = eval_to_out_with_responses(db, e)
    set_etag(response, out.version)
    return out

@router.post("/evaluations/{evaluation_id}/draft", response_model=EvaluationWithResponsesOut)
def save_draft(
    cycle_id: str,
    evaluation_id: str,
    payload: SaveDraftPayload,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    expected_version = parse_if_match(if_match)

    # Require concurrency token
    if expected_version is None:
        raise HTTPException(status_code=428, detail="If-Match required")

    cycle = _get_cycle_or_404(db, cycle_id)
    if cycle.status != "ACTIVE":
        raise HTTPException(
            status_code=409, detail="Drafts can only be edited while cycle is ACTIVE"
        )

    e = db.get(Evaluation, evaluation_id)
    if not e or str(e.cycle_id) != cycle_id:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    if e.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Can only edit draft evaluations")

    assignment = _get_assignment_in_cycle_or_404(db, cycle_id, str(e.assignment_id))
    assert_user_is_reviewer(db, current_user, assignment)

    # ✅ draft: keys exist + type sanity only
    validate_draft_payload(
        db=db,
        cycle=cycle,
        responses=[r.model_dump() for r in payload.responses],
    )

    idem_row = None
    if idempotency_key:
        idem_row, _ = begin_idempotent_request(
            db=db,
            user=current_user,
            key=idempotency_key,
            method="POST",
            route="/cycles/{cycle_id}/evaluations/{evaluation_id}/draft",
            payload_for_hash={
                "evaluation_id": evaluation_id,
                "if_match": expected_version,
                "responses": [r.model_dump() for r in payload.responses],
            },
        )
        if idem_row.status == "COMPLETED":
            out = EvaluationWithResponsesOut(**idem_row.response_body)
            set_etag(response, out.version)
            return out

    try:
        with db.begin_nested():
            e2 = db.get(Evaluation, evaluation_id)
            if not e2 or str(e2.cycle_id) != cycle_id:
                raise HTTPException(status_code=404, detail="Evaluation not found")

            if e2.status != "DRAFT":
                raise HTTPException(status_code=409, detail="Can only edit draft evaluations")

            # optimistic lock check (fast failure)
            assert_version_matches(
                current_version=e2.version, if_match_version=expected_version
            )

            # upsert responses
            for r in payload.responses:
                existing = (
                    db.query(EvaluationResponse)
                    .filter(
                        EvaluationResponse.evaluation_id == e2.id,
                        EvaluationResponse.question_key == r.question_key,
                    )
                    .one_or_none()
                )
                if existing:
                    existing.value_text = r.value_text
                    # optional, since model has onupdate; harmless to keep
                    existing.updated_at = datetime.utcnow()
                else:
                    db.add(
                        EvaluationResponse(
                            evaluation_id=e2.id,
                            question_key=r.question_key,
                            value_text=r.value_text,
                            updated_at=datetime.utcnow(),
                        )
                    )

            # IMPORTANT: touch parent row so version increments (optimistic locking)
            e2.updated_at = datetime.utcnow()

            db.flush()  # bumps version + ensures responses are queryable
            # Refresh to ensure we have the latest version after flush
            db.refresh(e2)

            log_event(
                db=db,
                actor=current_user,
                action="EVALUATION_DRAFT_SAVED",
                entity_type="evaluation",
                entity_id=e2.id,
                metadata={
                    "cycle_id": str(e2.cycle_id),
                    "assignment_id": str(e2.assignment_id),
                    "status": e2.status,
                    "response_count": len(payload.responses),
                    "version": e2.version,
                },
            )

            out = eval_to_out_with_responses(db, e2)

            if idem_row:
                complete_idempotent_request(
                    db=db,
                    row=idem_row,
                    response_code=200,
                    response_body=out.model_dump(mode="json"),
                )

        set_etag(response, out.version)
        return out

    except StaleDataError:
        if idem_row:
            fail_idempotent_request(db=db, row=idem_row)
        raise HTTPException(status_code=409, detail="Stale version")
    except Exception:
        if idem_row:
            fail_idempotent_request(db=db, row=idem_row)
        raise

@router.post("/evaluations/{evaluation_id}/submit", response_model=EvaluationOut)
def submit_evaluation(
    cycle_id: str,
    evaluation_id: str,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    expected_version = parse_if_match(if_match)

    cycle = _get_cycle_or_404(db, cycle_id)
    if cycle.status != "ACTIVE":
        raise HTTPException(
            status_code=409,
            detail="Evaluations can only be submitted while cycle is ACTIVE",
        )

    idem_row = None
    if idempotency_key:
        idem_row, _ = begin_idempotent_request(
            db=db,
            user=current_user,
            key=idempotency_key,
            method="POST",
            route="/cycles/{cycle_id}/evaluations/{evaluation_id}/submit",
            payload_for_hash={"evaluation_id": evaluation_id, "if_match": expected_version},
        )
        if idem_row.status == "COMPLETED":
            out = EvaluationOut(**idem_row.response_body)
            set_etag(response, out.version)
            return out

    try:
        with db.begin_nested():
            e = _lock_evaluation_in_cycle_or_404(db, cycle_id, evaluation_id)
            assignment = _get_assignment_in_cycle_or_404(db, cycle_id, str(e.assignment_id))
            assert_user_is_reviewer(db, current_user, assignment)

            assert_version_matches(current_version=e.version, if_match_version=expected_version)

            rows = (
                db.query(EvaluationResponse)
                .filter(EvaluationResponse.evaluation_id == e.id)
                .all()
            )
            stored = {r.question_key: r.value_text for r in rows}
            validate_submit_from_db(db=db, cycle=cycle, stored_responses=stored)

            if e.status == "SUBMITTED":
                out = eval_to_out(e)
            else:
                if e.status != "DRAFT":
                    raise HTTPException(
                        status_code=409, detail="Only DRAFT evaluations can be submitted"
                    )

                prev = e.status
                e.status = "SUBMITTED"
                e.submitted_at = datetime.utcnow()
                e.updated_at = datetime.utcnow()

                db.flush()  # bumps version
                # Refresh to ensure we have the latest version after flush
                db.refresh(e)

                log_event(
                    db=db,
                    actor=current_user,
                    action="EVALUATION_SUBMITTED",
                    entity_type="evaluation",
                    entity_id=e.id,
                    metadata={
                        "cycle_id": str(e.cycle_id),
                        "assignment_id": str(e.assignment_id),
                        "from": prev,
                        "to": e.status,
                        "version": e.version,
                    },
                )
                out = eval_to_out(e)

            if idem_row:
                complete_idempotent_request(
                    db=db,
                    row=idem_row,
                    response_code=200,
                    response_body=out.model_dump(mode="json"),
                )

        set_etag(response, out.version)
        return out

    except StaleDataError:
        if idem_row:
            fail_idempotent_request(db=db, row=idem_row)
        raise HTTPException(status_code=409, detail="Stale version")
    except Exception:
        if idem_row:
            fail_idempotent_request(db=db, row=idem_row)
        raise


@router.post("/evaluations/{evaluation_id}/return", response_model=EvaluationOut)
def return_evaluation(
    cycle_id: str,
    evaluation_id: str,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    expected_version = parse_if_match(if_match)

    cycle = _get_cycle_or_404(db, cycle_id)
    if cycle.status != "ACTIVE":
        raise HTTPException(
            status_code=409, detail="Evaluations can only be returned while cycle is ACTIVE"
        )

    idem_row = None
    if idempotency_key:
        idem_row, _ = begin_idempotent_request(
            db=db,
            user=current_user,
            key=idempotency_key,
            method="POST",
            route="/cycles/{cycle_id}/evaluations/{evaluation_id}/return",
            payload_for_hash={"evaluation_id": evaluation_id, "if_match": expected_version},
        )
        if idem_row.status == "COMPLETED":
            out = EvaluationOut(**idem_row.response_body)
            set_etag(response, out.version)
            return out

    try:
        with db.begin_nested():
            e = _lock_evaluation_in_cycle_or_404(db, cycle_id, evaluation_id)
            assignment = _get_assignment_in_cycle_or_404(db, cycle_id, str(e.assignment_id))
            assert_user_is_approver(db, current_user, assignment)

            assert_version_matches(current_version=e.version, if_match_version=expected_version)

            if e.status == "RETURNED":
                out = eval_to_out(e)
            else:
                if e.status != "SUBMITTED":
                    raise HTTPException(
                        status_code=409, detail="Only SUBMITTED evaluations can be returned"
                    )

                prev = e.status
                e.status = "RETURNED"
                e.updated_at = datetime.utcnow()

                db.flush()  # bumps version
                # Refresh to ensure we have the latest version after flush
                db.refresh(e)

                log_event(
                    db=db,
                    actor=current_user,
                    action="EVALUATION_RETURNED",
                    entity_type="evaluation",
                    entity_id=e.id,
                    metadata={
                        "cycle_id": str(e.cycle_id),
                        "assignment_id": str(e.assignment_id),
                        "from": prev,
                        "to": e.status,
                        "version": e.version,
                    },
                )
                out = eval_to_out(e)

            if idem_row:
                complete_idempotent_request(
                    db=db,
                    row=idem_row,
                    response_code=200,
                    response_body=out.model_dump(mode="json"),
                )

        set_etag(response, out.version)
        return out

    except StaleDataError:
        if idem_row:
            fail_idempotent_request(db=db, row=idem_row)
        raise HTTPException(status_code=409, detail="Stale version")
    except Exception:
        if idem_row:
            fail_idempotent_request(db=db, row=idem_row)
        raise


@router.post("/evaluations/{evaluation_id}/approve", response_model=EvaluationOut)
def approve_evaluation(
    cycle_id: str,
    evaluation_id: str,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    expected_version = parse_if_match(if_match)

    cycle = _get_cycle_or_404(db, cycle_id)
    if cycle.status != "ACTIVE":
        raise HTTPException(
            status_code=409, detail="Evaluations can only be approved while cycle is ACTIVE"
        )

    idem_row = None
    if idempotency_key:
        idem_row, _ = begin_idempotent_request(
            db=db,
            user=current_user,
            key=idempotency_key,
            method="POST",
            route="/cycles/{cycle_id}/evaluations/{evaluation_id}/approve",
            payload_for_hash={"evaluation_id": evaluation_id, "if_match": expected_version},
        )
        if idem_row.status == "COMPLETED":
            out = EvaluationOut(**idem_row.response_body)
            set_etag(response, out.version)
            return out

    try:
        with db.begin_nested():
            e = _lock_evaluation_in_cycle_or_404(db, cycle_id, evaluation_id)
            assignment = _get_assignment_in_cycle_or_404(db, cycle_id, str(e.assignment_id))
            assert_user_is_approver(db, current_user, assignment)

            assert_version_matches(current_version=e.version, if_match_version=expected_version)

            if e.status == "APPROVED":
                out = eval_to_out(e)
            else:
                if e.status != "SUBMITTED":
                    raise HTTPException(
                        status_code=409, detail="Only SUBMITTED evaluations can be approved"
                    )

                prev = e.status
                e.status = "APPROVED"
                e.approved_at = datetime.utcnow()
                e.updated_at = datetime.utcnow()

                db.flush()  # bumps version
                # Refresh to ensure we have the latest version after flush
                db.refresh(e)

                log_event(
                    db=db,
                    actor=current_user,
                    action="EVALUATION_APPROVED",
                    entity_type="evaluation",
                    entity_id=e.id,
                    metadata={
                        "cycle_id": str(e.cycle_id),
                        "assignment_id": str(e.assignment_id),
                        "from": prev,
                        "to": e.status,
                        "version": e.version,
                    },
                )
                out = eval_to_out(e)

            if idem_row:
                complete_idempotent_request(
                    db=db,
                    row=idem_row,
                    response_code=200,
                    response_body=out.model_dump(mode="json"),
                )

        set_etag(response, out.version)
        return out

    except StaleDataError:
        if idem_row:
            fail_idempotent_request(db=db, row=idem_row)
        raise HTTPException(status_code=409, detail="Stale version")
    except Exception:
        if idem_row:
            fail_idempotent_request(db=db, row=idem_row)
        raise


@router.post("/evaluations/{evaluation_id}/validate", response_model=ValidationPreviewResponse)
def validate_evaluation(
    cycle_id: str,
    evaluation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Preview validation errors for an evaluation without submitting.
    Useful for showing users what needs to be fixed before submission.
    """
    cycle = _get_cycle_or_404(db, cycle_id)
    evaluation = db.get(Evaluation, evaluation_id)
    if not evaluation or str(evaluation.cycle_id) != cycle_id:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    # Check access
    assignment = _get_assignment_in_cycle_or_404(db, cycle_id, str(evaluation.assignment_id))
    try:
        assert_user_is_reviewer(db, current_user, assignment)
    except HTTPException:
        assert_user_is_approver(db, current_user, assignment)

    # Get stored responses
    responses = (
        db.query(EvaluationResponse)
        .filter(EvaluationResponse.evaluation_id == evaluation.id)
        .all()
    )
    stored_responses = {r.question_key: r.value_text for r in responses}

    # Use validation logic but catch errors instead of raising
    from app.core.evaluation_form_validation import (
        _load_form_for_cycle_or_409,
        _load_form_fields_map,
        _full_validate_one,
    )

    try:
        form = _load_form_for_cycle_or_409(db, cycle)
    except HTTPException as e:
        return ValidationPreviewResponse(
            valid=False,
            errors=[ValidationError(field="", code="form_missing", message=e.detail)],
            warnings=[],
        )

    spec_map = _load_form_fields_map(db, form)
    validation_errors: list[dict] = []

    # Check for unknown keys
    for key in stored_responses.keys():
        if key not in spec_map:
            validation_errors.append({"field": key, "code": "unknown_key", "message": "Not in form"})

    # Validate all fields
    for key, spec in spec_map.items():
        value = stored_responses.get(key)
        validation_errors.extend(_full_validate_one(db, spec, value))

    # Convert to ValidationError objects
    errors = [
        ValidationError(field=e["field"], code=e["code"], message=e["message"])
        for e in validation_errors
    ]

    # Warnings (non-blocking)
    warnings: list[str] = []
    if evaluation.status == "DRAFT" and len(errors) == 0:
        warnings.append("Evaluation is ready to submit")

    return ValidationPreviewResponse(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
