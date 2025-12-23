from datetime import date
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import User
from app.models.employee import Employee
from app.models.rbac import Role, UserRole
from app.models.review_cycle import ReviewCycle
from app.models.review_assignment import ReviewAssignment


def get_or_create_user(db: Session, email: str, full_name: str, is_admin_flag: bool = False) -> User:
    u = db.query(User).filter(User.email == email).one_or_none()
    if u:
        return u
    u = User(email=email, full_name=full_name, is_active=True, is_admin=is_admin_flag)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def get_or_create_role(db: Session, name: str) -> Role:
    r = db.query(Role).filter(Role.name == name).one_or_none()
    if r:
        return r
    r = Role(name=name)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def ensure_user_role(db: Session, user_id, role_id):
    ur = (
        db.query(UserRole)
        .filter(UserRole.user_id == user_id, UserRole.role_id == role_id)
        .one_or_none()
    )
    if ur:
        return ur
    ur = UserRole(user_id=user_id, role_id=role_id)
    db.add(ur)
    db.commit()
    db.refresh(ur)
    return ur


def get_or_create_employee(db: Session, employee_number: str, display_name: str, user_id=None) -> Employee:
    e = db.query(Employee).filter(Employee.employee_number == employee_number).one_or_none()
    if e:
        # ensure link if provided
        if user_id and e.user_id != user_id:
            e.user_id = user_id
            db.commit()
            db.refresh(e)
        return e

    e = Employee(employee_number=employee_number, display_name=display_name, user_id=user_id)
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def get_or_create_cycle(db: Session, name: str, created_by_user_id) -> ReviewCycle:
    c = db.query(ReviewCycle).filter(ReviewCycle.name == name).one_or_none()
    if c:
        return c
    c = ReviewCycle(
        name=name,
        start_date=date(2024, 10, 1),
        end_date=date(2024, 12, 31),
        status="DRAFT",
        created_by_user_id=created_by_user_id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def get_or_create_assignment(db: Session, cycle_id, reviewer_emp_id, subject_emp_id, approver_emp_id) -> ReviewAssignment:
    a = (
        db.query(ReviewAssignment)
        .filter(
            ReviewAssignment.cycle_id == cycle_id,
            ReviewAssignment.reviewer_employee_id == reviewer_emp_id,
            ReviewAssignment.subject_employee_id == subject_emp_id,
        )
        .one_or_none()
    )
    if a:
        # update approver if different
        if a.approver_employee_id != approver_emp_id:
            a.approver_employee_id = approver_emp_id
            db.commit()
            db.refresh(a)
        return a

    a = ReviewAssignment(
        cycle_id=cycle_id,
        reviewer_employee_id=reviewer_emp_id,
        subject_employee_id=subject_emp_id,
        approver_employee_id=approver_emp_id,
        status="ACTIVE",
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def main():
    db = SessionLocal()
    try:
        # ---- Roles ----
        admin_role = get_or_create_role(db, "ADMIN")
        get_or_create_role(db, "REVIEWER")
        get_or_create_role(db, "APPROVER")

        # ---- Users ----
        admin_user = get_or_create_user(db, "admin@local.test", "Admin Local", is_admin_flag=True)
        reviewer_user = get_or_create_user(db, "reviewer@local.test", "Reviewer Local")
        approver_user = get_or_create_user(db, "approver@local.test", "Approver Local")

        ensure_user_role(db, admin_user.id, admin_role.id)

        # ---- Employees ----
        admin_emp = get_or_create_employee(db, "E100", "Admin Local", user_id=admin_user.id)
        reviewer_emp = get_or_create_employee(db, "E200", "Reviewer Local", user_id=reviewer_user.id)
        approver_emp = get_or_create_employee(db, "E300", "Approver Local", user_id=approver_user.id)
        subject_emp = get_or_create_employee(db, "E400", "Subject Local", user_id=None)

        # ---- Cycle (DRAFT) ----
        cycle = get_or_create_cycle(db, "Demo Cycle - Q4 2024", created_by_user_id=admin_user.id)

        # ---- Assignment ----
        assignment = get_or_create_assignment(
            db,
            cycle_id=cycle.id,
            reviewer_emp_id=reviewer_emp.id,
            subject_emp_id=subject_emp.id,
            approver_emp_id=approver_emp.id,
        )

        print("\n=== Demo Seed Complete ===")
        print("Base users (use as X-User-Email header):")
        print(f"  admin:    {admin_user.email}")
        print(f"  reviewer: {reviewer_user.email}")
        print(f"  approver: {approver_user.email}")

        print("\nCycle:")
        print(f"  cycle_id: {cycle.id}")
        print(f"  name:     {cycle.name}")
        print(f"  status:   {cycle.status}  (must be DRAFT for assignments; activate for evaluations)")

        print("\nEmployees:")
        print(f"  reviewer_employee_id: {reviewer_emp.id}")
        print(f"  subject_employee_id:  {subject_emp.id}")
        print(f"  approver_employee_id: {approver_emp.id}")

        print("\nAssignment:")
        print(f"  assignment_id: {assignment.id}")

        print("\nNext actions:")
        print("  1) (Admin) Activate cycle: POST /cycles/{cycle_id}/activate")
        print("  2) (Reviewer) Create/get evaluation: POST /cycles/{cycle_id}/assignments/{assignment_id}/evaluation")
        print("  3) (Reviewer) Save draft: POST /cycles/{cycle_id}/evaluations/{evaluation_id}/draft")
        print("  4) (Reviewer) Submit: POST /cycles/{cycle_id}/evaluations/{evaluation_id}/submit")
        print("  5) (Approver) Approve: POST /cycles/{cycle_id}/evaluations/{evaluation_id}/approve")
        print()

    finally:
        db.close()


if __name__ == "__main__":
    main()
