from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import Response
from sqlalchemy.orm.exc import StaleDataError

from app.core.optimistic_lock import parse_if_match, assert_version_matches, set_etag
from app.core.access import assert_user_is_reviewer, assert_user_is_approver
from app.core.audit import log_event
from app.core.idempotency import (
    begin_idempotent_request,
    complete_idempotent_request,
    fail_idempotent_request,
)
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.evaluation import Evaluation
from app.models.evaluation_response import EvaluationResponse
from app.models.review_assignment import ReviewAssignment
from app.models.review_cycle import ReviewCycle
from app.models.user import User
from app.schemas.evaluation import (
    EvaluationOut,
    EvaluationWithResponsesOut,
    SaveDraftPayload,
)

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


def _get_assignment_in_cycle_or_404(db: Session, cycle_id: str, assignment_id: str) -> ReviewAssignment:
    assignment = db.get(ReviewAssignment, assignment_id)
    if not assignment or str(assignment.cycle_id) != cycle_id:
        raise HTTPException(status_code=404, detail="Assignment not found in this cycle")
    return assignment


def _lock_evaluation_in_cycle_or_404(db: Session, cycle_id: str, evaluation_id: str) -> Evaluation:
    e = (
        db.query(Evaluation)
        .filter(Evaluation.id == evaluation_id)
        .with_for_update()
        .one_or_none()
    )
    if not e or str(e.cycle_id) != cycle_id:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return e


@router.post("/assignments/{assignment_id}/evaluation", response_model=EvaluationOut, status_code=201)
def create_or_get_evaluation(
    cycle_id: str,
    assignment_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    cycle = _get_cycle_or_404(db, cycle_id)
    if cycle.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Evaluations can only be created/edited while cycle is ACTIVE")

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
        with db.begin_nested():
            existing = db.query(Evaluation).filter(Evaluation.assignment_id == assignment.id).one_or_none()
            if existing:
                out = eval_to_out(existing)
            else:
                e = Evaluation(
                    cycle_id=assignment.cycle_id,
                    assignment_id=assignment.id,
                    status="DRAFT",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                db.add(e)

                try:
                    db.flush()  # get e.id
                except IntegrityError:
                    db.rollback()
                    existing = db.query(Evaluation).filter(Evaluation.assignment_id == assignment.id).one()
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
            with db.begin_nested():
                fail_idempotent_request(db=db, row=idem_row)
        raise


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationWithResponsesOut)
def get_evaluation(
    cycle_id: str,
    evaluation_id: str,
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

    return eval_to_out_with_responses(db, e)

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

    cycle = _get_cycle_or_404(db, cycle_id)
    if cycle.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Drafts can only be edited while cycle is ACTIVE")

    e = db.get(Evaluation, evaluation_id)
    if not e or str(e.cycle_id) != cycle_id:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    if e.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Can only edit draft evaluations")

    assignment = _get_assignment_in_cycle_or_404(db, cycle_id, str(e.assignment_id))
    assert_user_is_reviewer(db, current_user, assignment)

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

            # optimistic lock check
            assert_version_matches(current_version=e2.version, if_match_version=expected_version)

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

            e2.updated_at = datetime.utcnow()

            # IMPORTANT: ensure version increments + responses are queryable
            db.flush()

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
        # DB-level “someone updated between your check and flush”
        if idem_row:
            with db.begin_nested():
                fail_idempotent_request(db=db, row=idem_row)
        raise HTTPException(status_code=409, detail="Stale version")
    except Exception:
        if idem_row:
            with db.begin_nested():
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
        raise HTTPException(status_code=409, detail="Evaluations can only be submitted while cycle is ACTIVE")

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

            # optimistic lock check
            assert_version_matches(current_version=e.version, if_match_version=expected_version)

            if e.status == "SUBMITTED":
                out = eval_to_out(e)
            else:
                if e.status != "DRAFT":
                    raise HTTPException(status_code=409, detail="Only DRAFT evaluations can be submitted")

                prev = e.status
                e.status = "SUBMITTED"
                e.submitted_at = datetime.utcnow()
                e.updated_at = datetime.utcnow()

                db.flush()  # bumps version

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
            with db.begin_nested():
                fail_idempotent_request(db=db, row=idem_row)
        raise HTTPException(status_code=409, detail="Stale version")
    except Exception:
        if idem_row:
            with db.begin_nested():
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
        raise HTTPException(status_code=409, detail="Evaluations can only be returned while cycle is ACTIVE")

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
                    raise HTTPException(status_code=409, detail="Only SUBMITTED evaluations can be returned")

                prev = e.status
                e.status = "RETURNED"
                e.updated_at = datetime.utcnow()

                db.flush()

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
            with db.begin_nested():
                fail_idempotent_request(db=db, row=idem_row)
        raise HTTPException(status_code=409, detail="Stale version")
    except Exception:
        if idem_row:
            with db.begin_nested():
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
        raise HTTPException(status_code=409, detail="Evaluations can only be approved while cycle is ACTIVE")

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
                    raise HTTPException(status_code=409, detail="Only SUBMITTED evaluations can be approved")

                prev = e.status
                e.status = "APPROVED"
                e.approved_at = datetime.utcnow()
                e.updated_at = datetime.utcnow()

                db.flush()

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
            with db.begin_nested():
                fail_idempotent_request(db=db, row=idem_row)
        raise HTTPException(status_code=409, detail="Stale version")
    except Exception:
        if idem_row:
            with db.begin_nested():
                fail_idempotent_request(db=db, row=idem_row)
        raise
