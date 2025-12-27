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
