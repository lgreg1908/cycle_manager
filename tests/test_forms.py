from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import (
    create_user,
    grant_role,
    create_field_definition,
    create_form_template,
    attach_field_to_form,
)
from app.models.form_template import FormTemplate


def test_list_forms_requires_admin(db_session):
    """Test that listing forms requires admin role"""
    user = create_user(db_session, "user@test.com")
    client = TestClient(app)
    r = client.get("/forms", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 403


def test_list_forms_empty(db_session):
    """Test listing forms when none exist"""
    user = create_user(db_session, "admin@test.com")
    grant_role(db_session, user, "ADMIN")

    client = TestClient(app)
    r = client.get("/forms", headers={"X-User-Email": "admin@test.com"})
    assert r.status_code == 200
    assert r.json() == []


def test_list_forms_basic(db_session):
    """Test listing all forms"""
    user = create_user(db_session, "admin@test.com")
    grant_role(db_session, user, "ADMIN")

    form1 = create_form_template(db_session, name="Form A", version=1)
    form2 = create_form_template(db_session, name="Form B", version=1)

    client = TestClient(app)
    r = client.get("/forms", headers={"X-User-Email": "admin@test.com"})
    assert r.status_code == 200
    forms = r.json()
    assert len(forms) == 2
    form_names = [f["name"] for f in forms]
    assert "Form A" in form_names
    assert "Form B" in form_names


def test_list_forms_with_search(db_session):
    """Test searching forms by name or description"""
    user = create_user(db_session, "admin@test.com")
    grant_role(db_session, user, "ADMIN")

    create_form_template(db_session, name="Performance Review", version=1, description="Annual review")
    create_form_template(db_session, name="360 Review", version=1, description="Peer feedback")
    create_form_template(db_session, name="Goal Setting", version=1)

    client = TestClient(app)
    # Search by name
    r = client.get("/forms?search=Review", headers={"X-User-Email": "admin@test.com"})
    assert r.status_code == 200
    forms = r.json()
    assert len(forms) == 2
    assert all("Review" in f["name"] for f in forms)


def test_list_forms_filter_active(db_session):
    """Test filtering forms by active status"""
    user = create_user(db_session, "admin@test.com")
    grant_role(db_session, user, "ADMIN")

    active_form = create_form_template(db_session, name="Active Form", version=1)
    inactive_form = create_form_template(db_session, name="Inactive Form", version=1)
    inactive_form.is_active = False
    db_session.add(inactive_form)
    db_session.commit()

    client = TestClient(app)
    # Only active
    r = client.get("/forms?is_active=true", headers={"X-User-Email": "admin@test.com"})
    assert r.status_code == 200
    forms = r.json()
    assert len(forms) == 1
    assert forms[0]["name"] == "Active Form"

    # Only inactive
    r = client.get("/forms?is_active=false", headers={"X-User-Email": "admin@test.com"})
    assert r.status_code == 200
    forms = r.json()
    assert len(forms) == 1
    assert forms[0]["name"] == "Inactive Form"


def test_get_form_by_id(db_session):
    """Test getting a single form by ID"""
    user = create_user(db_session, "admin@test.com")
    grant_role(db_session, user, "ADMIN")

    form = create_form_template(db_session, name="Test Form", version=1, description="Test description")

    client = TestClient(app)
    r = client.get(f"/forms/{form.id}", headers={"X-User-Email": "admin@test.com"})
    assert r.status_code == 200
    form_data = r.json()
    assert form_data["id"] == str(form.id)
    assert form_data["name"] == "Test Form"
    assert form_data["version"] == 1
    assert form_data["description"] == "Test description"
    assert form_data["is_active"] is True


def test_get_form_with_fields(db_session):
    """Test getting form with its fields"""
    user = create_user(db_session, "admin@test.com")
    grant_role(db_session, user, "ADMIN")

    form = create_form_template(db_session, name="Test Form", version=1)
    field1 = create_field_definition(db_session, key="rating", label="Rating", field_type="number", required=True)
    field2 = create_field_definition(db_session, key="comment", label="Comment", field_type="text", required=False)
    attach_field_to_form(db_session, form=form, field=field1, position=1)
    attach_field_to_form(db_session, form=form, field=field2, position=2)

    client = TestClient(app)
    r = client.get(f"/forms/{form.id}?include_fields=true", headers={"X-User-Email": "admin@test.com"})
    assert r.status_code == 200
    form_data = r.json()
    assert "fields" in form_data
    assert len(form_data["fields"]) == 2
    field_keys = [f["key"] for f in form_data["fields"]]
    assert "rating" in field_keys
    assert "comment" in field_keys


def test_create_form_requires_admin(db_session):
    """Test that creating forms requires admin role"""
    user = create_user(db_session, "user@test.com")
    client = TestClient(app)
    r = client.post(
        "/forms",
        headers={"X-User-Email": "user@test.com"},
        json={"name": "New Form", "version": 1},
    )
    assert r.status_code == 403


def test_create_form_basic(db_session):
    """Test creating a new form template"""
    user = create_user(db_session, "admin@test.com")
    grant_role(db_session, user, "ADMIN")

    client = TestClient(app)
    r = client.post(
        "/forms",
        headers={"X-User-Email": "admin@test.com"},
        json={"name": "New Form", "version": 1, "description": "A new form"},
    )
    assert r.status_code == 201
    form_data = r.json()
    assert form_data["name"] == "New Form"
    assert form_data["version"] == 1
    assert form_data["description"] == "A new form"
    assert form_data["is_active"] is True


def test_create_field_definition_requires_admin(db_session):
    """Test that creating field definitions requires admin role"""
    user = create_user(db_session, "user@test.com")
    client = TestClient(app)
    r = client.post(
        "/forms/fields",
        headers={"X-User-Email": "user@test.com"},
        json={"key": "rating", "label": "Rating", "field_type": "number", "required": True},
    )
    assert r.status_code == 403


def test_create_field_definition_basic(db_session):
    """Test creating a new field definition"""
    user = create_user(db_session, "admin@test.com")
    grant_role(db_session, user, "ADMIN")

    client = TestClient(app)
    r = client.post(
        "/forms/fields",
        headers={"X-User-Email": "admin@test.com"},
        json={
            "key": "rating",
            "label": "Overall Rating",
            "field_type": "number",
            "required": True,
            "rules": {"min": 1, "max": 5, "integer": True},
        },
    )
    assert r.status_code == 201
    field_data = r.json()
    assert field_data["key"] == "rating"
    assert field_data["label"] == "Overall Rating"
    assert field_data["field_type"] == "number"
    assert field_data["required"] is True
    assert field_data["rules"] == {"min": 1, "max": 5, "integer": True}


def test_create_field_definition_duplicate_key(db_session):
    """Test that duplicate field keys are rejected"""
    user = create_user(db_session, "admin@test.com")
    grant_role(db_session, user, "ADMIN")

    # Create first field
    create_field_definition(db_session, key="rating", label="Rating")

    client = TestClient(app)
    # Try to create duplicate
    r = client.post(
        "/forms/fields",
        headers={"X-User-Email": "admin@test.com"},
        json={"key": "rating", "label": "Another Rating", "field_type": "number"},
    )
    assert r.status_code == 409


def test_attach_field_to_form(db_session):
    """Test attaching a field to a form"""
    user = create_user(db_session, "admin@test.com")
    grant_role(db_session, user, "ADMIN")

    form = create_form_template(db_session, name="Test Form", version=1)
    field = create_field_definition(db_session, key="rating", label="Rating", field_type="number")

    client = TestClient(app)
    # The endpoint expects a list of fields
    r = client.post(
        f"/forms/{form.id}/fields",
        headers={"X-User-Email": "admin@test.com"},
        json=[
            {
                "field_definition_id": str(field.id),
                "position": 1,
                "override_label": "Custom Rating",
            }
        ],
    )
    assert r.status_code == 200

    # Verify by getting form with fields
    r = client.get(f"/forms/{form.id}?include_fields=true", headers={"X-User-Email": "admin@test.com"})
    assert r.status_code == 200
    form_data = r.json()
    assert len(form_data["fields"]) == 1
    assert form_data["fields"][0]["key"] == "rating"
    assert form_data["fields"][0]["label"] == "Custom Rating"  # Override label

