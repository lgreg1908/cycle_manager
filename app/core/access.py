from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.review_assignment import ReviewAssignment
from app.models.user import User


def get_employee_for_user(db: Session, user: User) -> Employee | None:
    return db.query(Employee).filter(Employee.user_id == user.id).one_or_none()


def assert_user_is_reviewer(db: Session, user: User, assignment: ReviewAssignment):
    emp = get_employee_for_user(db, user)
    if not emp or emp.id != assignment.reviewer_employee_id:
        raise HTTPException(status_code=403, detail="Only the assigned reviewer can perform this action")


def assert_user_is_approver(db: Session, user: User, assignment: ReviewAssignment):
    emp = get_employee_for_user(db, user)
    if not emp or emp.id != assignment.approver_employee_id:
        raise HTTPException(status_code=403, detail="Only the assigned approver can perform this action")
