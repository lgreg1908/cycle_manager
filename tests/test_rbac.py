from fastapi.testclient import TestClient

from app.main import app
from app.models.user import User
from app.models.rbac import Role, UserRole


def test_admin_ping_forbidden_without_admin_role(db_session):
    # seed user (no roles)
    u = User(email="user@local.test", full_name="User Local", is_admin=False)
    db_session.add(u)
    db_session.commit()

    client = TestClient(app)
    r = client.get("/admin/ping", headers={"X-User-Email": "user@local.test"})
    assert r.status_code == 403


def test_admin_ping_ok_with_admin_role(db_session):
    # seed role + user + mapping
    admin_role = Role(name="ADMIN")
    db_session.add(admin_role)
    db_session.commit()
    db_session.refresh(admin_role)

    u = User(email="admin2@local.test", full_name="Admin Two", is_admin=False)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)

    db_session.add(UserRole(user_id=u.id, role_id=admin_role.id))
    db_session.commit()

    client = TestClient(app)
    r = client.get("/admin/ping", headers={"X-User-Email": "admin2@local.test"})
    assert r.status_code == 200
    assert r.json()["admin"] == "admin2@local.test"
