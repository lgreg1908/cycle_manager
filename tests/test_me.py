from fastapi.testclient import TestClient
from app.main import app
from app.models.user import User
from tests.helpers import (
    create_user,
    create_employee,
    create_cycle,
    create_assignment,
    create_form_template,
    set_cycle_form_template,
)


def test_me_requires_header(db_session):
    client = TestClient(app)
    r = client.get("/me")
    assert r.status_code == 401


def test_me_returns_user(db_session):
    # seed user
    u = User(email="admin@local.test", full_name="Admin Local", is_admin=True)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)

    client = TestClient(app)
    r = client.get("/me", headers={"X-User-Email": "admin@local.test"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "admin@local.test"
    assert body["is_admin"] is True


def test_me_evaluations_requires_auth(db_session):
    """Test that /me/evaluations requires authentication"""
    client = TestClient(app)
    r = client.get("/me/evaluations")
    assert r.status_code == 401


def test_me_evaluations_no_employee(db_session):
    """Test that users without employee record get empty list"""
    user = create_user(db_session, "user@test.com")
    client = TestClient(app)
    r = client.get("/me/evaluations", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    assert r.json() == []


def test_me_evaluations_basic(db_session):
    """Test getting evaluations where user is involved"""
    from app.models.evaluation import Evaluation
    
    user = create_user(db_session, "user@test.com")
    employee = create_employee(db_session, "E100", "Test User", user=user)
    
    admin = create_user(db_session, "admin@test.com")
    admin_emp = create_employee(db_session, "E200", "Admin", user=admin)
    subject_emp = create_employee(db_session, "E300", "Subject", user=None)
    approver_emp = create_employee(db_session, "E400", "Approver", user=None)
    
    # Create active cycle with form
    cycle = create_cycle(db_session, admin, status="ACTIVE")
    form = create_form_template(db_session, name="Test Form", version=1)
    set_cycle_form_template(db_session, cycle=cycle, form=form)
    
    # Create assignment where user is reviewer
    assignment = create_assignment(
        db_session,
        cycle=cycle,
        reviewer=employee,
        subject=subject_emp,
        approver=approver_emp,
    )
    
    # Create evaluation
    evaluation = Evaluation(
        cycle_id=cycle.id,
        assignment_id=assignment.id,
        status="DRAFT",
    )
    db_session.add(evaluation)
    db_session.commit()
    db_session.refresh(evaluation)
    
    client = TestClient(app)
    r = client.get("/me/evaluations", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    evaluations = r.json()
    assert len(evaluations) == 1
    assert evaluations[0]["id"] == str(evaluation.id)
    assert evaluations[0]["status"] == "DRAFT"


def test_me_evaluations_filter_by_role(db_session):
    """Test filtering evaluations by role (reviewer, approver, subject)"""
    from app.models.evaluation import Evaluation
    
    user = create_user(db_session, "user@test.com")
    employee = create_employee(db_session, "E100", "Test User", user=user)
    
    admin = create_user(db_session, "admin@test.com")
    subject_emp = create_employee(db_session, "E300", "Subject", user=None)
    approver_emp = create_employee(db_session, "E400", "Approver", user=None)
    
    cycle = create_cycle(db_session, admin, status="ACTIVE")
    form = create_form_template(db_session, name="Test Form", version=1)
    set_cycle_form_template(db_session, cycle=cycle, form=form)
    
    # Assignment where user is reviewer
    assignment1 = create_assignment(
        db_session,
        cycle=cycle,
        reviewer=employee,
        subject=subject_emp,
        approver=approver_emp,
    )
    eval1 = Evaluation(cycle_id=cycle.id, assignment_id=assignment1.id, status="DRAFT")
    db_session.add(eval1)
    
    # Assignment where user is approver
    assignment2 = create_assignment(
        db_session,
        cycle=cycle,
        reviewer=subject_emp,
        subject=subject_emp,
        approver=employee,
    )
    # SUBMITTED status requires submitted_at to be set (database constraint)
    from datetime import datetime
    eval2 = Evaluation(
        cycle_id=cycle.id,
        assignment_id=assignment2.id,
        status="SUBMITTED",
        submitted_at=datetime.utcnow(),
    )
    db_session.add(eval2)
    db_session.commit()
    
    client = TestClient(app)
    
    # Filter by reviewer role
    r = client.get("/me/evaluations?role=reviewer", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    evaluations = r.json()
    assert len(evaluations) == 1
    assert evaluations[0]["id"] == str(eval1.id)
    
    # Filter by approver role
    r = client.get("/me/evaluations?role=approver", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    evaluations = r.json()
    assert len(evaluations) == 1
    assert evaluations[0]["id"] == str(eval2.id)


def test_me_evaluations_filter_by_status(db_session):
    """Test filtering evaluations by status"""
    from app.models.evaluation import Evaluation
    
    user = create_user(db_session, "user@test.com")
    employee = create_employee(db_session, "E100", "Test User", user=user)
    
    admin = create_user(db_session, "admin@test.com")
    subject_emp = create_employee(db_session, "E300", "Subject", user=None)
    approver_emp = create_employee(db_session, "E400", "Approver", user=None)
    
    cycle = create_cycle(db_session, admin, status="ACTIVE")
    form = create_form_template(db_session, name="Test Form", version=1)
    set_cycle_form_template(db_session, cycle=cycle, form=form)
    
    # Create two assignments (one evaluation per assignment due to unique constraint)
    assignment1 = create_assignment(
        db_session,
        cycle=cycle,
        reviewer=employee,
        subject=subject_emp,
        approver=approver_emp,
    )
    assignment2 = create_assignment(
        db_session,
        cycle=cycle,
        reviewer=employee,
        subject=approver_emp,  # Different subject
        approver=approver_emp,
    )
    
    # SUBMITTED status requires submitted_at to be set (database constraint)
    from datetime import datetime
    eval1 = Evaluation(cycle_id=cycle.id, assignment_id=assignment1.id, status="DRAFT")
    eval2 = Evaluation(
        cycle_id=cycle.id,
        assignment_id=assignment2.id,
        status="SUBMITTED",
        submitted_at=datetime.utcnow(),
    )
    db_session.add(eval1)
    db_session.add(eval2)
    db_session.commit()
    
    client = TestClient(app)
    r = client.get("/me/evaluations?status=DRAFT", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    evaluations = r.json()
    assert len(evaluations) == 1
    assert evaluations[0]["status"] == "DRAFT"


def test_me_assignments_requires_auth(db_session):
    """Test that /me/assignments requires authentication"""
    client = TestClient(app)
    r = client.get("/me/assignments")
    assert r.status_code == 401


def test_me_assignments_no_employee(db_session):
    """Test that users without employee record get empty list"""
    user = create_user(db_session, "user@test.com")
    client = TestClient(app)
    r = client.get("/me/assignments", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    assert r.json() == []


def test_me_assignments_basic(db_session):
    """Test getting assignments where user is involved"""
    user = create_user(db_session, "user@test.com")
    employee = create_employee(db_session, "E100", "Test User", user=user)
    
    admin = create_user(db_session, "admin@test.com")
    subject_emp = create_employee(db_session, "E300", "Subject", user=None)
    approver_emp = create_employee(db_session, "E400", "Approver", user=None)
    
    cycle = create_cycle(db_session, admin, status="DRAFT")
    
    # Create assignment where user is reviewer
    assignment = create_assignment(
        db_session,
        cycle=cycle,
        reviewer=employee,
        subject=subject_emp,
        approver=approver_emp,
    )
    
    client = TestClient(app)
    r = client.get("/me/assignments", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    assignments = r.json()
    assert len(assignments) == 1
    assert assignments[0]["id"] == str(assignment.id)
    assert assignments[0]["reviewer_employee_id"] == str(employee.id)


def test_me_assignments_filter_by_role(db_session):
    """Test filtering assignments by role"""
    user = create_user(db_session, "user@test.com")
    employee = create_employee(db_session, "E100", "Test User", user=user)
    
    admin = create_user(db_session, "admin@test.com")
    subject_emp = create_employee(db_session, "E300", "Subject", user=None)
    approver_emp = create_employee(db_session, "E400", "Approver", user=None)
    
    cycle = create_cycle(db_session, admin, status="DRAFT")
    
    # Assignment where user is reviewer
    assignment1 = create_assignment(
        db_session,
        cycle=cycle,
        reviewer=employee,
        subject=subject_emp,
        approver=approver_emp,
    )
    
    # Assignment where user is approver
    assignment2 = create_assignment(
        db_session,
        cycle=cycle,
        reviewer=subject_emp,
        subject=subject_emp,
        approver=employee,
    )
    
    client = TestClient(app)
    
    # Filter by reviewer role
    r = client.get("/me/assignments?role=reviewer", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    assignments = r.json()
    assert len(assignments) == 1
    assert assignments[0]["id"] == str(assignment1.id)
    
    # Filter by approver role
    r = client.get("/me/assignments?role=approver", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    assignments = r.json()
    assert len(assignments) == 1
    assert assignments[0]["id"] == str(assignment2.id)
