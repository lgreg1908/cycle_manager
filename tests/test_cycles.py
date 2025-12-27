from fastapi.testclient import TestClient

from app.main import app
from app.models.user import User
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


def seed_user(db_session, email="user@local.test"):
    u = User(email=email, full_name="User", is_active=True, is_admin=False)
    db_session.add(u)
    db_session.commit()
    return u


def test_create_cycle_requires_admin(db_session):
    seed_user(db_session, "user@local.test")

    client = TestClient(app)
    r = client.post(
        "/cycles",
        headers={"X-User-Email": "user@local.test"},
        json={"name": "Q4 2024 Reviews"},
    )
    assert r.status_code == 403


def test_cycle_lifecycle(db_session):
    seed_admin(db_session, "admin@local.test")

    client = TestClient(app)

    # create
    r = client.post(
        "/cycles",
        headers={"X-User-Email": "admin@local.test"},
        json={"name": "Q4 2024 Reviews"},
    )
    assert r.status_code == 201
    cycle = r.json()
    assert cycle["status"] == "DRAFT"
    cycle_id = cycle["id"]

    # update allowed in draft
    r = client.patch(
        f"/cycles/{cycle_id}",
        headers={"X-User-Email": "admin@local.test"},
        json={"name": "Q4 2024 Performance Reviews"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Q4 2024 Performance Reviews"

    # activate
    r = client.post(
        f"/cycles/{cycle_id}/activate",
        headers={"X-User-Email": "admin@local.test"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ACTIVE"

    # update no longer allowed
    r = client.patch(
        f"/cycles/{cycle_id}",
        headers={"X-User-Email": "admin@local.test"},
        json={"name": "should fail"},
    )
    assert r.status_code == 409

    # close
    r = client.post(
        f"/cycles/{cycle_id}/close",
        headers={"X-User-Email": "admin@local.test"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "CLOSED"

    # activate again should fail
    r = client.post(
        f"/cycles/{cycle_id}/activate",
        headers={"X-User-Email": "admin@local.test"},
    )
    assert r.status_code == 409


def test_list_cycles_requires_auth(db_session):
    # No header => 401
    client = TestClient(app)
    r = client.get("/cycles")
    assert r.status_code == 401


def test_cycle_includes_form_template_id(db_session):
    """Test that cycle responses include form_template_id field"""
    from tests.helpers import create_form_template, set_cycle_form_template
    
    admin = seed_admin(db_session, "admin@local.test")
    client = TestClient(app)

    # Create cycle
    r = client.post(
        "/cycles",
        headers={"X-User-Email": "admin@local.test"},
        json={"name": "Q4 2024 Reviews"},
    )
    assert r.status_code == 201
    cycle = r.json()
    cycle_id = cycle["id"]
    
    # Initially should have no form_template_id
    assert cycle.get("form_template_id") is None
    
    # Get cycle directly
    r = client.get(f"/cycles/{cycle_id}", headers={"X-User-Email": "admin@local.test"})
    assert r.status_code == 200
    cycle = r.json()
    assert cycle.get("form_template_id") is None
    
    # Assign a form template
    form = create_form_template(db_session, name="Review Form", version=1)
    set_cycle_form_template(db_session, cycle=db_session.get(ReviewCycle, cycle_id), form=form)
    
    # Get cycle again - should now have form_template_id
    r = client.get(f"/cycles/{cycle_id}", headers={"X-User-Email": "admin@local.test"})
    assert r.status_code == 200
    cycle = r.json()
    assert cycle.get("form_template_id") == str(form.id)


def test_set_cycle_form_template_requires_admin(db_session):
    """Test that setting form template requires admin role"""
    from tests.helpers import create_cycle, create_form_template
    from app.models.review_cycle import ReviewCycle
    
    user = seed_user(db_session, "user@local.test")
    admin = seed_admin(db_session, "admin@local.test")
    
    cycle = create_cycle(db_session, admin)
    form = create_form_template(db_session, name="Test Form", version=1)
    
    client = TestClient(app)
    r = client.post(
        f"/cycles/{cycle.id}/set-form/{form.id}",
        headers={"X-User-Email": "user@local.test"},
    )
    assert r.status_code == 403


def test_set_cycle_form_template_success(db_session):
    """Test successfully setting a form template on a cycle"""
    from tests.helpers import create_form_template
    
    admin = seed_admin(db_session, "admin@local.test")
    client = TestClient(app)

    # Create cycle
    r = client.post(
        "/cycles",
        headers={"X-User-Email": "admin@local.test"},
        json={"name": "Q4 2024 Reviews"},
    )
    assert r.status_code == 201
    cycle_id = r.json()["id"]
    
    # Create form template
    form = create_form_template(db_session, name="Review Form", version=1)
    
    # Set form template
    r = client.post(
        f"/cycles/{cycle_id}/set-form/{form.id}",
        headers={"X-User-Email": "admin@local.test"},
    )
    assert r.status_code == 200
    cycle = r.json()
    assert cycle["form_template_id"] == str(form.id)
    
    # Verify it's persisted
    r = client.get(f"/cycles/{cycle_id}", headers={"X-User-Email": "admin@local.test"})
    assert r.status_code == 200
    cycle = r.json()
    assert cycle["form_template_id"] == str(form.id)


def test_set_cycle_form_template_cycle_not_found(db_session):
    """Test setting form template on non-existent cycle returns 404"""
    from tests.helpers import create_form_template
    import uuid
    
    admin = seed_admin(db_session, "admin@local.test")
    form = create_form_template(db_session, name="Test Form", version=1)
    fake_cycle_id = str(uuid.uuid4())
    
    client = TestClient(app)
    r = client.post(
        f"/cycles/{fake_cycle_id}/set-form/{form.id}",
        headers={"X-User-Email": "admin@local.test"},
    )
    assert r.status_code == 404


def test_set_cycle_form_template_form_not_found(db_session):
    """Test setting non-existent form template returns 404"""
    from tests.helpers import create_cycle
    import uuid
    
    admin = seed_admin(db_session, "admin@local.test")
    cycle = create_cycle(db_session, admin)
    fake_form_id = str(uuid.uuid4())
    
    client = TestClient(app)
    r = client.post(
        f"/cycles/{cycle.id}/set-form/{fake_form_id}",
        headers={"X-User-Email": "admin@local.test"},
    )
    assert r.status_code == 404


def test_set_cycle_form_template_inactive_form(db_session):
    """Test that inactive form templates cannot be assigned"""
    from tests.helpers import create_form_template
    
    admin = seed_admin(db_session, "admin@local.test")
    client = TestClient(app)

    # Create cycle
    r = client.post(
        "/cycles",
        headers={"X-User-Email": "admin@local.test"},
        json={"name": "Q4 2024 Reviews"},
    )
    assert r.status_code == 201
    cycle_id = r.json()["id"]
    
    # Create and deactivate form template
    form = create_form_template(db_session, name="Inactive Form", version=1)
    form.is_active = False
    db_session.commit()
    
    # Try to set inactive form - should fail
    r = client.post(
        f"/cycles/{cycle_id}/set-form/{form.id}",
        headers={"X-User-Email": "admin@local.test"},
    )
    assert r.status_code == 404


def test_list_cycles_with_search_and_pagination(db_session):
    """Test cycle list with search and pagination"""
    admin = seed_admin(db_session, "admin@local.test")
    client = TestClient(app)

    # Create multiple cycles
    for i in range(3):
        r = client.post(
            "/cycles",
            headers={"X-User-Email": "admin@local.test"},
            json={"name": f"Q{i+1} 2024 Reviews"},
        )
        assert r.status_code == 201

    # Search
    r = client.get("/cycles?search=Q1", headers={"X-User-Email": "admin@local.test"})
    assert r.status_code == 200
    cycles = r.json()
    assert len(cycles) == 1
    assert "Q1" in cycles[0]["name"]

    # Pagination
    r = client.get("/cycles?limit=2&offset=0", headers={"X-User-Email": "admin@local.test"})
    assert r.status_code == 200
    cycles = r.json()
    assert len(cycles) == 2

    # Status filter
    r = client.get("/cycles?status=DRAFT", headers={"X-User-Email": "admin@local.test"})
    assert r.status_code == 200
    cycles = r.json()
    assert all(c["status"] == "DRAFT" for c in cycles)


# ===== Cycle Readiness Check Tests =====

def test_cycle_readiness_not_found(client: TestClient, db_session):
    """Test cycle readiness check for non-existent cycle"""
    import uuid
    from tests.helpers import create_user, grant_role
    
    admin = create_user(db_session, email="admin@example.com", is_admin=True)
    grant_role(db_session, admin, "ADMIN")
    
    # Use a valid UUID format that doesn't exist
    fake_id = str(uuid.uuid4())
    response = client.get(
        f"/cycles/{fake_id}/readiness",
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 404


def test_cycle_readiness_not_draft(client: TestClient, db_session):
    """Test cycle readiness check for non-DRAFT cycle"""
    from tests.helpers import create_user, grant_role, create_cycle
    
    admin = create_user(db_session, email="admin@example.com", is_admin=True)
    grant_role(db_session, admin, "ADMIN")
    
    cycle = create_cycle(db_session, created_by=admin, status="ACTIVE")
    
    response = client.get(
        f"/cycles/{cycle.id}/readiness",
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["can_activate"] is False
    assert data["ready"] is False
    assert "is_draft" in data["checks"]
    assert data["checks"]["is_draft"] is False
    assert len(data["errors"]) > 0


def test_cycle_readiness_no_form_template(client: TestClient, db_session):
    """Test cycle readiness check when no form template is assigned"""
    from tests.helpers import create_user, grant_role, create_cycle
    
    admin = create_user(db_session, email="admin@example.com", is_admin=True)
    grant_role(db_session, admin, "ADMIN")
    
    cycle = create_cycle(db_session, created_by=admin, status="DRAFT")
    
    response = client.get(
        f"/cycles/{cycle.id}/readiness",
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["can_activate"] is False
    assert data["checks"]["has_form_template"] is False
    assert any("form template" in err.lower() for err in data["errors"])


def test_cycle_readiness_no_assignments(client: TestClient, db_session):
    """Test cycle readiness check when no assignments exist"""
    from tests.helpers import (
        create_user, grant_role, create_cycle, create_form_template,
        create_field_definition, attach_field_to_form, set_cycle_form_template,
    )
    
    admin = create_user(db_session, email="admin@example.com", is_admin=True)
    grant_role(db_session, admin, "ADMIN")
    
    cycle = create_cycle(db_session, created_by=admin, status="DRAFT")
    form = create_form_template(db_session, name="Test Form")
    field = create_field_definition(db_session, key="q1", field_type="text")
    attach_field_to_form(db_session, form=form, field=field, position=1)
    set_cycle_form_template(db_session, cycle=cycle, form=form)
    
    response = client.get(
        f"/cycles/{cycle.id}/readiness",
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["can_activate"] is False
    assert data["checks"]["has_assignments"] is False
    assert any("assignment" in err.lower() for err in data["errors"])


def test_cycle_readiness_form_without_fields(client: TestClient, db_session):
    """Test cycle readiness check when form has no fields"""
    from tests.helpers import (
        create_user, grant_role, create_cycle, create_form_template,
        set_cycle_form_template, create_employee, create_assignment,
    )
    
    admin = create_user(db_session, email="admin@example.com", is_admin=True)
    grant_role(db_session, admin, "ADMIN")
    
    cycle = create_cycle(db_session, created_by=admin, status="DRAFT")
    form = create_form_template(db_session, name="Test Form")
    set_cycle_form_template(db_session, cycle=cycle, form=form)
    
    reviewer = create_employee(db_session, employee_number="R001", display_name="Reviewer")
    subject = create_employee(db_session, employee_number="S001", display_name="Subject")
    approver = create_employee(db_session, employee_number="A001", display_name="Approver")
    create_assignment(db_session, cycle=cycle, reviewer=reviewer, subject=subject, approver=approver)
    
    response = client.get(
        f"/cycles/{cycle.id}/readiness",
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["can_activate"] is False
    assert data["checks"]["form_has_fields"] is False
    assert any("field" in err.lower() for err in data["errors"])


def test_cycle_readiness_ready(client: TestClient, db_session):
    """Test cycle readiness check when cycle is ready"""
    from tests.helpers import (
        create_user, grant_role, create_cycle, create_form_for_cycle_with_fields,
        create_employee, create_assignment,
    )
    
    admin = create_user(db_session, email="admin@example.com", is_admin=True)
    grant_role(db_session, admin, "ADMIN")
    
    cycle = create_cycle(db_session, created_by=admin, status="DRAFT")
    create_form_for_cycle_with_fields(
        db_session,
        cycle=cycle,
        fields=[{"key": "q1", "field_type": "text"}],
    )
    
    reviewer = create_employee(db_session, employee_number="R001", display_name="Reviewer")
    subject = create_employee(db_session, employee_number="S001", display_name="Subject")
    approver = create_employee(db_session, employee_number="A001", display_name="Approver")
    create_assignment(db_session, cycle=cycle, reviewer=reviewer, subject=subject, approver=approver)
    
    response = client.get(
        f"/cycles/{cycle.id}/readiness",
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["can_activate"] is True
    assert all(data["checks"].values())
    assert len(data["errors"]) == 0


def test_cycle_readiness_warnings(client: TestClient, db_session):
    """Test cycle readiness check with warnings (non-blocking)"""
    from tests.helpers import (
        create_user, grant_role, create_cycle, create_form_for_cycle_with_fields,
        create_employee, create_assignment,
    )
    
    admin = create_user(db_session, email="admin@example.com", is_admin=True)
    grant_role(db_session, admin, "ADMIN")
    
    cycle = create_cycle(db_session, created_by=admin, status="DRAFT")
    create_form_for_cycle_with_fields(
        db_session,
        cycle=cycle,
        fields=[{"key": "q1", "field_type": "text"}],
    )
    
    reviewer = create_employee(db_session, employee_number="R001", display_name="Reviewer")
    subject = create_employee(db_session, employee_number="S001", display_name="Subject")
    approver = create_employee(db_session, employee_number="A001", display_name="Approver")
    create_assignment(db_session, cycle=cycle, reviewer=reviewer, subject=subject, approver=approver)
    
    response = client.get(
        f"/cycles/{cycle.id}/readiness",
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["can_activate"] is True
    # Should have warnings about missing dates
    assert len(data["warnings"]) > 0
    assert any("date" in w.lower() for w in data["warnings"])


# ===== Cycle Stats Tests =====

def test_cycle_stats(client: TestClient, db_session):
    """Test /cycles/{id}/stats endpoint"""
    from datetime import datetime
    from app.models.evaluation import Evaluation
    from tests.helpers import create_user, grant_role, create_cycle, create_employee, create_assignment
    
    admin = create_user(db_session, email="admin@example.com", is_admin=True)
    grant_role(db_session, admin, "ADMIN")
    
    cycle = create_cycle(db_session, created_by=admin, status="ACTIVE")
    
    approver = create_employee(db_session, employee_number="A001", display_name="Approver")
    
    # Create 3 assignments with different employees (unique constraint)
    assignments = []
    for i in range(3):
        reviewer = create_employee(db_session, employee_number=f"R{i:03d}", display_name=f"Reviewer {i}")
        subject = create_employee(db_session, employee_number=f"S{i:03d}", display_name=f"Subject {i}")
        assignments.append(create_assignment(
            db_session,
            cycle=cycle,
            reviewer=reviewer,
            subject=subject,
            approver=approver,
        ))
    
    # Create 2 evaluations
    for i in range(2):
        evaluation = Evaluation(
            cycle_id=cycle.id,
            assignment_id=assignments[i].id,
            status="DRAFT" if i == 0 else "SUBMITTED",
            submitted_at=datetime.utcnow() if i == 1 else None,
        )
        db_session.add(evaluation)
    db_session.commit()
    
    response = client.get(
        f"/cycles/{cycle.id}/stats",
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["cycle_id"] == str(cycle.id)
    assert data["cycle_name"] == cycle.name
    assert data["total_assignments"] == 3
    assert data["total_evaluations"] == 2
    assert data["evaluations_by_status"]["DRAFT"] == 1
    assert data["evaluations_by_status"]["SUBMITTED"] == 1
    assert data["completion_rate"] > 0  # 2/3 = 66.67%


def test_cycle_stats_not_found(client: TestClient, db_session):
    """Test /cycles/{id}/stats for non-existent cycle"""
    import uuid
    from tests.helpers import create_user
    
    user = create_user(db_session, email="user@example.com")
    
    fake_id = str(uuid.uuid4())
    response = client.get(
        f"/cycles/{fake_id}/stats",
        headers={"X-User-Email": "user@example.com"},
    )
    assert response.status_code == 404
