from fastapi.testclient import TestClient

from app.main import app
from app.models.user import User
from app.models.rbac import Role, UserRole


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
