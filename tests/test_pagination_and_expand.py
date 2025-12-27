"""
Tests for pagination and expand functionality across endpoints.
"""
import pytest
from fastapi.testclient import TestClient

from tests.helpers import (
    create_user,
    create_employee,
    create_cycle,
    create_assignment,
    grant_role,
)


def test_me_endpoint_includes_employee_id(client: TestClient, db_session):
    """Test that /me endpoint includes employee_id"""
    user = create_user(db_session, email="test@example.com")
    employee = create_employee(db_session, employee_number="E001", display_name="Test Employee", user=user)
    
    response = client.get("/me", headers={"X-User-Email": "test@example.com"})
    assert response.status_code == 200
    data = response.json()
    assert "employee_id" in data
    assert data["employee_id"] == str(employee.id)
    assert data["email"] == "test@example.com"


def test_me_endpoint_no_employee(client: TestClient, db_session):
    """Test /me endpoint when user has no linked employee"""
    user = create_user(db_session, email="test@example.com")
    
    response = client.get("/me", headers={"X-User-Email": "test@example.com"})
    assert response.status_code == 200
    data = response.json()
    assert data["employee_id"] is None


def test_assignments_list_with_pagination(client: TestClient, db_session):
    """Test assignments list endpoint with pagination"""
    admin = create_user(db_session, email="admin@example.com", is_admin=True)
    grant_role(db_session, admin, "ADMIN")
    
    cycle = create_cycle(db_session, created_by=admin, status="DRAFT")
    
    # Create 5 assignments with different employees (unique constraint requires unique cycle+reviewer+subject)
    approver = create_employee(db_session, employee_number="A001", display_name="Approver")
    
    for i in range(5):
        reviewer = create_employee(db_session, employee_number=f"R{i:03d}", display_name=f"Reviewer {i}")
        subject = create_employee(db_session, employee_number=f"S{i:03d}", display_name=f"Subject {i}")
        create_assignment(
            db_session,
            cycle=cycle,
            reviewer=reviewer,
            subject=subject,
            approver=approver,
        )
    
    # Test without pagination (default)
    response = client.get(
        f"/cycles/{cycle.id}/assignments",
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 5
    
    # Test with pagination
    response = client.get(
        f"/cycles/{cycle.id}/assignments",
        params={"include_pagination": True, "limit": 2, "offset": 0},
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "pagination" in data
    assert len(data["items"]) == 2
    assert data["pagination"]["total"] == 5
    assert data["pagination"]["limit"] == 2
    assert data["pagination"]["offset"] == 0
    assert data["pagination"]["has_more"] is True
    
    # Test second page
    response = client.get(
        f"/cycles/{cycle.id}/assignments",
        params={"include_pagination": True, "limit": 2, "offset": 2},
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["pagination"]["offset"] == 2
    assert data["pagination"]["has_more"] is True
    
    # Test last page
    response = client.get(
        f"/cycles/{cycle.id}/assignments",
        params={"include_pagination": True, "limit": 2, "offset": 4},
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["pagination"]["has_more"] is False


def test_assignments_list_with_expand(client: TestClient, db_session):
    """Test assignments list endpoint with expand=employees"""
    admin = create_user(db_session, email="admin@example.com", is_admin=True)
    grant_role(db_session, admin, "ADMIN")
    
    cycle = create_cycle(db_session, created_by=admin, status="DRAFT")
    
    reviewer = create_employee(db_session, employee_number="R001", display_name="Reviewer One")
    subject = create_employee(db_session, employee_number="S001", display_name="Subject One")
    approver = create_employee(db_session, employee_number="A001", display_name="Approver One")
    
    assignment = create_assignment(
        db_session,
        cycle=cycle,
        reviewer=reviewer,
        subject=subject,
        approver=approver,
    )
    
    # Test without expand
    response = client.get(
        f"/cycles/{cycle.id}/assignments",
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert "reviewer_name" not in data[0]
    assert "subject_name" not in data[0]
    assert "approver_name" not in data[0]
    
    # Test with expand
    response = client.get(
        f"/cycles/{cycle.id}/assignments",
        params={"expand": "employees"},
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    item = data[0]
    assert "reviewer_name" in item
    assert item["reviewer_name"] == "Reviewer One"
    assert item["reviewer_employee_number"] == "R001"
    assert "subject_name" in item
    assert item["subject_name"] == "Subject One"
    assert item["subject_employee_number"] == "S001"
    assert "approver_name" in item
    assert item["approver_name"] == "Approver One"
    assert item["approver_employee_number"] == "A001"


def test_assignments_list_expand_with_pagination(client: TestClient, db_session):
    """Test assignments with both expand and pagination"""
    admin = create_user(db_session, email="admin@example.com", is_admin=True)
    grant_role(db_session, admin, "ADMIN")
    
    cycle = create_cycle(db_session, created_by=admin, status="DRAFT")
    
    approver = create_employee(db_session, employee_number="A001", display_name="Approver")
    
    for i in range(3):
        reviewer = create_employee(db_session, employee_number=f"R{i:03d}", display_name=f"Reviewer {i}")
        subject = create_employee(db_session, employee_number=f"S{i:03d}", display_name=f"Subject {i}")
        create_assignment(
            db_session,
            cycle=cycle,
            reviewer=reviewer,
            subject=subject,
            approver=approver,
        )
    
    response = client.get(
        f"/cycles/{cycle.id}/assignments",
        params={"expand": "employees", "include_pagination": True, "limit": 2},
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "pagination" in data
    assert len(data["items"]) == 2
    assert "reviewer_name" in data["items"][0]
    assert data["pagination"]["total"] == 3


def test_me_assignments_with_expand(client: TestClient, db_session):
    """Test /me/assignments with expand parameter"""
    user = create_user(db_session, email="user@example.com")
    employee = create_employee(db_session, employee_number="E001", display_name="Test Employee", user=user)
    
    reviewer = create_employee(db_session, employee_number="R001", display_name="Reviewer")
    subject = create_employee(db_session, employee_number="S001", display_name="Subject")
    approver = create_employee(db_session, employee_number="A001", display_name="Approver")
    
    admin = create_user(db_session, email="admin@example.com", is_admin=True)
    grant_role(db_session, admin, "ADMIN")
    cycle = create_cycle(db_session, created_by=admin, status="DRAFT")
    
    # Create assignment where user is reviewer
    assignment = create_assignment(
        db_session,
        cycle=cycle,
        reviewer=employee,
        subject=subject,
        approver=approver,
    )
    
    # Test without expand
    response = client.get(
        "/me/assignments",
        headers={"X-User-Email": "user@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert "reviewer_name" not in data[0]
    
    # Test with expand
    response = client.get(
        "/me/assignments",
        params={"expand": "employees"},
        headers={"X-User-Email": "user@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert "reviewer_name" in data[0]
    assert data[0]["reviewer_name"] == "Test Employee"
    assert data[0]["subject_name"] == "Subject"
    assert data[0]["approver_name"] == "Approver"


def test_cycles_list_with_pagination(client: TestClient, db_session):
    """Test cycles list endpoint with pagination"""
    user = create_user(db_session, email="user@example.com")
    
    # Create 5 cycles
    from app.models.review_cycle import ReviewCycle
    for i in range(5):
        cycle = ReviewCycle(name=f"Cycle {i}", status="DRAFT", created_by_user_id=user.id)
        db_session.add(cycle)
    db_session.commit()
    
    # Test without pagination
    response = client.get("/cycles", headers={"X-User-Email": "user@example.com"})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 5
    
    # Test with pagination
    response = client.get(
        "/cycles",
        params={"include_pagination": True, "limit": 2},
        headers={"X-User-Email": "user@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "pagination" in data
    assert len(data["items"]) == 2
    assert data["pagination"]["total"] == 5
    assert data["pagination"]["has_more"] is True


def test_employees_list_with_pagination(client: TestClient, db_session):
    """Test employees list endpoint with pagination"""
    user = create_user(db_session, email="user@example.com")
    
    # Create 5 employees
    for i in range(5):
        create_employee(db_session, employee_number=f"E{i:03d}", display_name=f"Employee {i}")
    
    # Test with pagination
    response = client.get(
        "/employees",
        params={"include_pagination": True, "limit": 2},
        headers={"X-User-Email": "user@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "pagination" in data
    assert len(data["items"]) == 2
    assert data["pagination"]["total"] == 5


def test_forms_list_with_pagination(client: TestClient, db_session):
    """Test forms list endpoint with pagination"""
    admin = create_user(db_session, email="admin@example.com", is_admin=True)
    grant_role(db_session, admin, "ADMIN")
    
    from tests.helpers import create_form_template
    
    # Create 5 forms
    for i in range(5):
        create_form_template(db_session, name=f"Form {i}")
    
    # Test with pagination
    response = client.get(
        "/forms",
        params={"include_pagination": True, "limit": 2},
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "pagination" in data
    assert len(data["items"]) == 2
    assert data["pagination"]["total"] == 5


def test_evaluations_list_with_expand(client: TestClient, db_session):
    """Test evaluations list with expand=employees"""
    from datetime import datetime
    from tests.helpers import create_form_for_cycle_with_fields
    
    admin = create_user(db_session, email="admin@example.com", is_admin=True)
    grant_role(db_session, admin, "ADMIN")
    
    reviewer = create_employee(db_session, employee_number="R001", display_name="Reviewer")
    subject = create_employee(db_session, employee_number="S001", display_name="Subject")
    approver = create_employee(db_session, employee_number="A001", display_name="Approver")
    
    cycle = create_cycle(db_session, created_by=admin, status="DRAFT")
    create_form_for_cycle_with_fields(db_session, cycle=cycle, fields=[{"key": "q1", "field_type": "text"}])
    
    # Activate cycle (evaluations can only exist in ACTIVE cycles)
    cycle.status = "ACTIVE"
    db_session.commit()
    
    assignment = create_assignment(
        db_session,
        cycle=cycle,
        reviewer=reviewer,
        subject=subject,
        approver=approver,
    )
    
    # Create evaluation
    from app.models.evaluation import Evaluation
    evaluation = Evaluation(
        cycle_id=cycle.id,
        assignment_id=assignment.id,
        status="DRAFT",
    )
    db_session.add(evaluation)
    db_session.commit()
    
    # Test with expand
    response = client.get(
        f"/cycles/{cycle.id}/evaluations",
        params={"expand": "employees"},
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    item = data[0]
    assert "reviewer_name" in item
    assert item["reviewer_name"] == "Reviewer"
    assert item["subject_name"] == "Subject"
    assert item["approver_name"] == "Approver"


def test_pagination_metadata_calculations(client: TestClient, db_session):
    """Test that pagination metadata calculations are correct"""
    admin = create_user(db_session, email="admin@example.com", is_admin=True)
    grant_role(db_session, admin, "ADMIN")
    
    cycle = create_cycle(db_session, created_by=admin, status="DRAFT")
    
    approver = create_employee(db_session, employee_number="A001", display_name="Approver")
    
    # Create exactly 10 assignments with different employees
    for i in range(10):
        reviewer = create_employee(db_session, employee_number=f"R{i:03d}", display_name=f"Reviewer {i}")
        subject = create_employee(db_session, employee_number=f"S{i:03d}", display_name=f"Subject {i}")
        create_assignment(
            db_session,
            cycle=cycle,
            reviewer=reviewer,
            subject=subject,
            approver=approver,
        )
    
    # Test pagination metadata
    response = client.get(
        f"/cycles/{cycle.id}/assignments",
        params={"include_pagination": True, "limit": 3, "offset": 0},
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    pagination = data["pagination"]
    assert pagination["total"] == 10
    assert pagination["limit"] == 3
    assert pagination["offset"] == 0
    assert pagination["has_more"] is True
    # Note: page and total_pages are computed properties, not serialized fields
    
    # Test last page
    response = client.get(
        f"/cycles/{cycle.id}/assignments",
        params={"include_pagination": True, "limit": 3, "offset": 9},
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    pagination = data["pagination"]
    assert pagination["has_more"] is False
    assert pagination["offset"] == 9

