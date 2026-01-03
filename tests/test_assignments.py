from fastapi.testclient import TestClient

from app.main import app
from app.models.user import User
from app.models.employee import Employee
from app.models.rbac import Role, UserRole
from app.models.review_cycle import ReviewCycle


def seed_admin(db_session, email="admin@local.test"):
    role = db_session.query(Role).filter(Role.name == "ADMIN").one_or_none()
    if not role:
        role = Role(name="ADMIN")
        db_session.add(role)
        db_session.commit()
        db_session.refresh(role)

    u = User(email=email, full_name="Admin", is_active=True, is_admin=False)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)

    db_session.add(UserRole(user_id=u.id, role_id=role.id))
    db_session.commit()
    return u


def seed_employee(db_session, num, name, user_id=None):
    e = Employee(employee_number=num, display_name=name, user_id=user_id)
    db_session.add(e)
    db_session.commit()
    db_session.refresh(e)
    return e


def seed_cycle(db_session, created_by_user_id):
    c = ReviewCycle(name="Q4 Reviews", status="DRAFT", created_by_user_id=created_by_user_id)
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


def test_create_assignment_in_active_cycle_fails(db_session):
    """Test that assignments cannot be created in ACTIVE cycle"""
    from tests.helpers import create_user, grant_role, create_employee
    from app.models.review_cycle import ReviewCycle
    
    admin = seed_admin(db_session, "admin@local.test")
    reviewer_emp = seed_employee(db_session, "E200", "Reviewer")
    subject_emp = seed_employee(db_session, "E201", "Subject")
    approver_emp = seed_employee(db_session, "E202", "Approver")

    # Create ACTIVE cycle
    cycle = seed_cycle(db_session, admin.id)
    cycle.status = "ACTIVE"
    db_session.commit()

    client = TestClient(app)
    r = client.post(
        f"/cycles/{cycle.id}/assignments/bulk",
        headers={"X-User-Email": "admin@local.test"},
        json={
            "items": [
                {
                    "reviewer_employee_id": str(reviewer_emp.id),
                    "subject_employee_id": str(subject_emp.id),
                    "approver_employee_id": str(approver_emp.id),
                }
            ]
        },
    )
    # Should fail - can't add assignments to active cycle
    assert r.status_code in [400, 409, 422]


def test_bulk_create_assignments_admin_only(db_session):
    # non-admin user exists
    u = User(email="user@local.test", full_name="User", is_active=True, is_admin=False)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)

    # cycle exists
    c = seed_cycle(db_session, created_by_user_id=u.id)

    client = TestClient(app)
    r = client.post(
        f"/cycles/{c.id}/assignments/bulk",
        headers={"X-User-Email": "user@local.test"},
        json={"items": []},
    )
    # blocked by RBAC (403) before payload validation
    assert r.status_code == 403


def test_bulk_create_assignments_happy_path(db_session):
    admin = seed_admin(db_session, "admin@local.test")

    # employees exist
    reviewer = seed_employee(db_session, "E1", "Reviewer")
    subject = seed_employee(db_session, "E2", "Subject")
    approver = seed_employee(db_session, "E3", "Approver")

    # cycle exists
    c = seed_cycle(db_session, created_by_user_id=admin.id)

    client = TestClient(app)
    r = client.post(
        f"/cycles/{c.id}/assignments/bulk",
        headers={"X-User-Email": "admin@local.test"},
        json={
            "items": [
                {
                    "reviewer_employee_id": str(reviewer.id),
                    "subject_employee_id": str(subject.id),
                    "approver_employee_id": str(approver.id),
                }
            ]
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert len(body) == 1
    assert body[0]["cycle_id"] == str(c.id)

    # list
    r2 = client.get(f"/cycles/{c.id}/assignments", headers={"X-User-Email": "admin@local.test"})
    assert r2.status_code == 200
    assert len(r2.json()) == 1


def test_bulk_create_assignments_duplicate_conflict(db_session):
    admin = seed_admin(db_session, "admin@local.test")
    reviewer = seed_employee(db_session, "E1", "Reviewer")
    subject = seed_employee(db_session, "E2", "Subject")
    approver = seed_employee(db_session, "E3", "Approver")
    c = seed_cycle(db_session, created_by_user_id=admin.id)

    client = TestClient(app)

    payload = {
        "items": [
            {
                "reviewer_employee_id": str(reviewer.id),
                "subject_employee_id": str(subject.id),
                "approver_employee_id": str(approver.id),
            }
        ]
    }

    r1 = client.post(
        f"/cycles/{c.id}/assignments/bulk",
        headers={"X-User-Email": "admin@local.test"},
        json=payload,
    )
    assert r1.status_code == 201

    r2 = client.post(
        f"/cycles/{c.id}/assignments/bulk",
        headers={"X-User-Email": "admin@local.test"},
        json=payload,
    )
    assert r2.status_code == 409
