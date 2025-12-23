from app.models.user import User
from app.models.employee import Employee
from app.models.rbac import Role, UserRole
from app.models.review_cycle import ReviewCycle
from app.models.review_assignment import ReviewAssignment

def ensure_role(db, name: str) -> Role:
    r = db.query(Role).filter(Role.name == name).one_or_none()
    if r:
        return r
    r = Role(name=name)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r

def create_user(db, email: str, full_name="User", is_admin=False) -> User:
    u = User(email=email, full_name=full_name, is_active=True, is_admin=is_admin)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u

def grant_role(db, user: User, role_name: str):
    role = ensure_role(db, role_name)
    exists = db.query(UserRole).filter(UserRole.user_id == user.id, UserRole.role_id == role.id).one_or_none()
    if not exists:
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()

def create_employee(db, employee_number: str, display_name: str, user: User | None = None) -> Employee:
    e = Employee(employee_number=employee_number, display_name=display_name, user_id=(user.id if user else None))
    db.add(e)
    db.commit()
    db.refresh(e)
    return e

def create_cycle(db, created_by: User, status="DRAFT") -> ReviewCycle:
    c = ReviewCycle(name="Q4 Reviews", status=status, created_by_user_id=created_by.id)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c

def create_assignment(db, cycle: ReviewCycle, reviewer: Employee, subject: Employee, approver: Employee, status="ACTIVE") -> ReviewAssignment:
    a = ReviewAssignment(
        cycle_id=cycle.id,
        reviewer_employee_id=reviewer.id,
        subject_employee_id=subject.id,
        approver_employee_id=approver.id,
        status=status,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a
