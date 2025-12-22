from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.security import get_current_user
from app.core.rbac import require_roles
from app.core.access import assert_user_is_reviewer, assert_user_is_approver
from app.db.session import get_db
from app.models.user import User
from app.models.review_cycle import ReviewCycle
from app.models.review_assignment import ReviewAssignment
from app.models.evaluation import Evaluation
from app.models.evaluation_response import EvaluationResponse
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
    )


def eval_to_out_with_responses(db: Session, e: Evaluation) -> EvaluationWithResponsesOut:
    rows = db.query(EvaluationResponse).filter(EvaluationResponse.evaluation_id == e.id).all()
    return EvaluationWithResponsesOut(
        **eval_to_out(e).model_dump(),
        responses={r.question_key: r.value_text for r in rows},
    )


@router.post("/assignments/{assignment_id}/evaluation", response_model=EvaluationOut, status_code=201)
def create_or_get_evaluation(
    cycle_id: str,
    assignment_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Must exist
    cycle = db.get(ReviewCycle, cycle_id)
    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")
    if cycle.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Evaluations can only be created/edited while cycle is ACTIVE")

    assignment = db.get(ReviewAssignment, assignment_id)
    if not assignment or str(assignment.cycle_id) != cycle_id:
        raise HTTPException(status_code=404, detail="Assignment not found in this cycle")

    # Reviewer only (admin handled later)
    assert_user_is_reviewer(db, user, assignment)

    existing = db.query(Evaluation).filter(Evaluation.assignment_id == assignment.id).one_or_none()
    if existing:
        return eval_to_out(existing)

    e = Evaluation(
        cycle_id=assignment.cycle_id,
        assignment_id=assignment.id,
        status="DRAFT",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(e)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # race condition: someone else created it
        e = db.query(Evaluation).filter(Evaluation.assignment_id == assignment.id).one()
        return eval_to_out(e)

    db.refresh(e)
    return eval_to_out(e)


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

    assignment = db.get(ReviewAssignment, e.assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    # allow reviewer or approver; admin later
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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    e = db.get(Evaluation, evaluation_id)
    if not e or str(e.cycle_id) != cycle_id:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    if e.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Can only edit draft evaluations")

    assignment = db.get(ReviewAssignment, e.assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    assert_user_is_reviewer(db, user, assignment)

    for r in payload.responses:
        existing = (
            db.query(EvaluationResponse)
            .filter(EvaluationResponse.evaluation_id == e.id, EvaluationResponse.question_key == r.question_key)
            .one_or_none()
        )
        if existing:
            existing.value_text = r.value_text
            existing.updated_at = datetime.utcnow()
        else:
            db.add(
                EvaluationResponse(
                    evaluation_id=e.id,
                    question_key=r.question_key,
                    value_text=r.value_text,
                    updated_at=datetime.utcnow(),
                )
            )

    e.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(e)

    return eval_to_out_with_responses(db, e)


@router.post("/evaluations/{evaluation_id}/submit", response_model=EvaluationOut)
def submit_evaluation(
    cycle_id: str,
    evaluation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    e = db.get(Evaluation, evaluation_id)
    if not e or str(e.cycle_id) != cycle_id:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    if e.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only DRAFT evaluations can be submitted")

    assignment = db.get(ReviewAssignment, e.assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    assert_user_is_reviewer(db, user, assignment)

    e.status = "SUBMITTED"
    e.submitted_at = datetime.utcnow()
    e.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(e)
    return eval_to_out(e)


@router.post("/evaluations/{evaluation_id}/return", response_model=EvaluationOut)
def return_evaluation(
    cycle_id: str,
    evaluation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    e = db.get(Evaluation, evaluation_id)
    if not e or str(e.cycle_id) != cycle_id:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    if e.status != "SUBMITTED":
        raise HTTPException(status_code=409, detail="Only SUBMITTED evaluations can be returned")

    assignment = db.get(ReviewAssignment, e.assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    assert_user_is_approver(db, user, assignment)

    e.status = "RETURNED"
    e.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(e)
    return eval_to_out(e)


@router.post("/evaluations/{evaluation_id}/approve", response_model=EvaluationOut)
def approve_evaluation(
    cycle_id: str,
    evaluation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    e = db.get(Evaluation, evaluation_id)
    if not e or str(e.cycle_id) != cycle_id:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    if e.status != "SUBMITTED":
        raise HTTPException(status_code=409, detail="Only SUBMITTED evaluations can be approved")

    assignment = db.get(ReviewAssignment, e.assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    assert_user_is_approver(db, user, assignment)

    e.status = "APPROVED"
    e.approved_at = datetime.utcnow()
    e.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(e)
    return eval_to_out(e)
