from fastapi.testclient import TestClient
from app.main import app
from app.models.user import User

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
