"""
Tests for audit endpoints and admin functionality.
"""

from fastapi.testclient import TestClient
from app.main import app

from tests.helpers import create_user, grant_role, create_cycle


def test_admin_ping(db_session):
    """Test admin ping endpoint"""
    admin = create_user(db_session, "admin@local.test", "Admin")
    grant_role(db_session, admin, "ADMIN")

    client = TestClient(app)
    response = client.get(
        "/admin/ping",
        headers={"X-User-Email": "admin@local.test"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["admin"] == "admin@local.test"


def test_list_audit_events(db_session):
    """Test listing audit events"""
    admin = create_user(db_session, "admin@local.test", "Admin")
    grant_role(db_session, admin, "ADMIN")

    # Setup a cycle to generate audit events
    cycle = create_cycle(db_session, created_by=admin, status="ACTIVE")

    client = TestClient(app)
    response = client.get(
        "/audit",
        headers={"X-User-Email": "admin@local.test"},
    )
    assert response.status_code == 200
    events = response.json()
    assert isinstance(events, list)


def test_list_audit_events_for_cycle(db_session):
    """Test listing audit events filtered by cycle"""
    admin = create_user(db_session, "admin@local.test", "Admin")
    grant_role(db_session, admin, "ADMIN")

    cycle = create_cycle(db_session, created_by=admin, status="ACTIVE")

    client = TestClient(app)
    response = client.get(
        "/audit",
        headers={"X-User-Email": "admin@local.test"},
        params={"entity_type": "review_cycle", "entity_id": str(cycle.id)},
    )
    assert response.status_code == 200
    cycle_events = response.json()
    assert isinstance(cycle_events, list)


def test_list_audit_events_requires_admin(db_session):
    """Test that listing audit events requires admin role"""
    user = create_user(db_session, "user@local.test", "User")
    client = TestClient(app)
    
    response = client.get(
        "/audit",
        headers={"X-User-Email": "user@local.test"},
    )
    assert response.status_code == 403

