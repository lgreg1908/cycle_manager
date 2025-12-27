from typing import Union
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.security import get_current_user
from app.core.access import get_employee_for_user
from app.db.session import get_db
from app.models.user import User
from app.models.evaluation import Evaluation
from app.models.review_assignment import ReviewAssignment
from app.models.employee import Employee
from app.schemas.evaluation import EvaluationOut
from app.schemas.review_assignment import AssignmentOut
from app.schemas.expanded import AssignmentOutExpanded
from app.schemas.pagination import PaginatedResponse, PaginationMeta

router = APIRouter(tags=["auth"])


@router.get("/me")
def me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user information including linked employee ID"""
    employee = get_employee_for_user(db, current_user)
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "is_admin": current_user.is_admin,
        "is_active": current_user.is_active,
        "employee_id": str(employee.id) if employee else None,
    }


@router.get("/me/evaluations", response_model=list[EvaluationOut])
def my_evaluations(
    cycle_id: str | None = Query(default=None, description="Filter by cycle ID"),
    status: str | None = Query(default=None, description="Filter by status"),
    role: str | None = Query(default=None, description="Filter by role: reviewer, approver, or subject"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get evaluations where the current user is involved as reviewer, approver, or subject.
    """
    employee = get_employee_for_user(db, current_user)
    if not employee:
        return []
    
    query = db.query(Evaluation).join(
        ReviewAssignment, ReviewAssignment.id == Evaluation.assignment_id
    )
    
    # Filter by user's role in the assignment
    if role == "reviewer":
        query = query.filter(ReviewAssignment.reviewer_employee_id == employee.id)
    elif role == "approver":
        query = query.filter(ReviewAssignment.approver_employee_id == employee.id)
    elif role == "subject":
        query = query.filter(ReviewAssignment.subject_employee_id == employee.id)
    else:
        # Default: show all roles
        query = query.filter(
            (ReviewAssignment.reviewer_employee_id == employee.id)
            | (ReviewAssignment.approver_employee_id == employee.id)
            | (ReviewAssignment.subject_employee_id == employee.id)
        )
    
    if cycle_id:
        query = query.filter(Evaluation.cycle_id == cycle_id)
    
    if status:
        query = query.filter(Evaluation.status == status)
    
    evaluations = query.order_by(Evaluation.created_at.desc()).offset(offset).limit(limit).all()
    
    return [
        EvaluationOut(
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
        for e in evaluations
    ]


def _assignment_to_out_expanded(a: ReviewAssignment, reviewer: Employee | None, subject: Employee | None, approver: Employee | None) -> AssignmentOutExpanded:
    """Helper to convert assignment to expanded format"""
    return AssignmentOutExpanded(
        id=str(a.id),
        cycle_id=str(a.cycle_id),
        reviewer_employee_id=str(a.reviewer_employee_id),
        reviewer_name=reviewer.display_name if reviewer else None,
        reviewer_employee_number=reviewer.employee_number if reviewer else None,
        subject_employee_id=str(a.subject_employee_id),
        subject_name=subject.display_name if subject else None,
        subject_employee_number=subject.employee_number if subject else None,
        approver_employee_id=str(a.approver_employee_id),
        approver_name=approver.display_name if approver else None,
        approver_employee_number=approver.employee_number if approver else None,
        status=a.status,
        created_at=a.created_at.isoformat() if a.created_at else "",
    )


@router.get("/me/assignments")
def my_assignments(
    cycle_id: str | None = Query(default=None, description="Filter by cycle ID"),
    status: str | None = Query(default=None, description="Filter by status"),
    role: str | None = Query(default=None, description="Filter by role: reviewer, approver, or subject"),
    expand: str | None = Query(default=None, description="Comma-separated list: 'employees' to include employee names"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    include_pagination: bool = Query(default=False, description="Include pagination metadata"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get assignments where the current user is involved as reviewer, approver, or subject.
    
    Use ?expand=employees to include employee names in the response.
    Use ?include_pagination=true to get pagination metadata.
    """
    employee = get_employee_for_user(db, current_user)
    if not employee:
        if include_pagination:
            return PaginatedResponse(
                items=[],
                pagination=PaginationMeta(total=0, limit=limit, offset=offset, has_more=False),
            )
        return []
    
    query = db.query(ReviewAssignment)
    
    # Filter by user's role in the assignment
    if role == "reviewer":
        query = query.filter(ReviewAssignment.reviewer_employee_id == employee.id)
    elif role == "approver":
        query = query.filter(ReviewAssignment.approver_employee_id == employee.id)
    elif role == "subject":
        query = query.filter(ReviewAssignment.subject_employee_id == employee.id)
    else:
        # Default: show all roles
        query = query.filter(
            (ReviewAssignment.reviewer_employee_id == employee.id)
            | (ReviewAssignment.approver_employee_id == employee.id)
            | (ReviewAssignment.subject_employee_id == employee.id)
        )
    
    if cycle_id:
        query = query.filter(ReviewAssignment.cycle_id == cycle_id)
    
    if status:
        query = query.filter(ReviewAssignment.status == status)
    
    # Get total count before pagination
    total = query.count()
    
    # Apply pagination
    assignments = query.order_by(ReviewAssignment.created_at.desc()).offset(offset).limit(limit).all()
    
    # Expand employees if requested
    expand_employees = expand and "employees" in expand.split(",")
    if expand_employees:
        # Collect employee IDs
        employee_ids = set()
        for a in assignments:
            employee_ids.add(a.reviewer_employee_id)
            employee_ids.add(a.subject_employee_id)
            employee_ids.add(a.approver_employee_id)
        
        # Batch load employees
        employees = {str(e.id): e for e in db.query(Employee).filter(Employee.id.in_(list(employee_ids))).all()}
        
        items = [
            _assignment_to_out_expanded(
                a,
                employees.get(str(a.reviewer_employee_id)),
                employees.get(str(a.subject_employee_id)),
                employees.get(str(a.approver_employee_id)),
            )
            for a in assignments
        ]
    else:
        items = [
            AssignmentOut(
                id=str(a.id),
                cycle_id=str(a.cycle_id),
                reviewer_employee_id=str(a.reviewer_employee_id),
                subject_employee_id=str(a.subject_employee_id),
                approver_employee_id=str(a.approver_employee_id),
                status=a.status,
                created_at=a.created_at,
            )
            for a in assignments
        ]
    
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
