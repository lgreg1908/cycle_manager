# tests/test_evaluations.py

from fastapi.testclient import TestClient

from app.models.audit_event import AuditEvent
from app.models.idempotency import IdempotencyKey

from tests.helpers import (
    create_user,
    grant_role,
    create_employee,
    create_cycle,
    create_assignment,
    create_field_definition,
    create_form_template,
    attach_field_to_form,
    set_cycle_form_template,
    create_form_for_cycle_with_fields
)


def _count_audit(db, action: str, entity_type: str, entity_id: str) -> int:
    return (
        db.query(AuditEvent)
        .filter(
            AuditEvent.action == action,
            AuditEvent.entity_type == entity_type,
            AuditEvent.entity_id == entity_id,
        )
        .count()
    )


def test_evaluation_cannot_be_created_when_cycle_not_active(db_session, client: TestClient):
    reviewer_user = create_user(db_session, "reviewer@local.test", "Reviewer")
    reviewer_emp = create_employee(db_session, "E200", "Reviewer", user=reviewer_user)

    approver_user = create_user(db_session, "approver@local.test", "Approver")
    approver_emp = create_employee(db_session, "E300", "Approver", user=approver_user)

    admin = create_user(db_session, "admin@local.test", "Admin")
    grant_role(db_session, admin, "ADMIN")

    subject_emp = create_employee(db_session, "E400", "Subject", user=None)

    cycle = create_cycle(db_session, created_by=admin, status="DRAFT")  # NOT ACTIVE
    assignment = create_assignment(db_session, cycle, reviewer_emp, subject_emp, approver_emp)

    r = client.post(
        f"/cycles/{cycle.id}/assignments/{assignment.id}/evaluation",
        headers={"X-User-Email": "reviewer@local.test"},
    )
    assert r.status_code == 409

def test_evaluation_happy_path_workflow(db_session, client: TestClient):
    admin = create_user(db_session, "admin@local.test", "Admin")
    grant_role(db_session, admin, "ADMIN")

    reviewer_user = create_user(db_session, "reviewer@local.test", "Reviewer")
    approver_user = create_user(db_session, "approver@local.test", "Approver")

    reviewer_emp = create_employee(db_session, "E200", "Reviewer", user=reviewer_user)
    approver_emp = create_employee(db_session, "E300", "Approver", user=approver_user)
    subject_emp = create_employee(db_session, "E400", "Subject", user=None)

    cycle = create_cycle(db_session, created_by=admin, status="ACTIVE")

    # ✅ attach a form to the cycle so q1 is valid (draft validation needs known keys)
    create_form_for_cycle_with_fields(
        db_session,
        cycle=cycle,
        fields=[
            {"key": "q1", "field_type": "text", "required": False},
        ],
    )

    assignment = create_assignment(db_session, cycle, reviewer_emp, subject_emp, approver_emp)

    # (Reviewer) create/get evaluation
    r = client.post(
        f"/cycles/{cycle.id}/assignments/{assignment.id}/evaluation",
        headers={"X-User-Email": "reviewer@local.test"},
    )
    assert r.status_code == 201
    ev = r.json()
    assert ev["status"] == "DRAFT"
    evaluation_id = ev["id"]
    v1 = ev["version"]

    # audit exists exactly once
    assert _count_audit(db_session, "EVALUATION_CREATED", "evaluation", evaluation_id) == 1

    # (Reviewer) save draft (requires If-Match)
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/draft",
        headers={"X-User-Email": "reviewer@local.test", "If-Match": str(v1)},
        json={"responses": [{"question_key": "q1", "value_text": "hello"}]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["responses"]["q1"] == "hello"
    assert _count_audit(db_session, "EVALUATION_DRAFT_SAVED", "evaluation", evaluation_id) == 1
    v2 = body["version"]

    # (Approver) cannot save draft
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/draft",
        headers={"X-User-Email": "approver@local.test", "If-Match": str(v2)},
        json={"responses": [{"question_key": "q1", "value_text": "nope"}]},
    )
    assert r.status_code == 403

    # (Reviewer) submit (requires If-Match)
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/submit",
        headers={"X-User-Email": "reviewer@local.test", "If-Match": str(v2)},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "SUBMITTED"
    assert _count_audit(db_session, "EVALUATION_SUBMITTED", "evaluation", evaluation_id) == 1
    v3 = r.json()["version"]

    # (Reviewer) cannot approve
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/approve",
        headers={"X-User-Email": "reviewer@local.test", "If-Match": str(v3)},
    )
    assert r.status_code == 403

    # (Approver) return (requires If-Match)
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/return",
        headers={"X-User-Email": "approver@local.test", "If-Match": str(v3)},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "RETURNED"
    assert _count_audit(db_session, "EVALUATION_RETURNED", "evaluation", evaluation_id) == 1
    v4 = r.json()["version"]

    # (Approver) cannot approve from RETURNED
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/approve",
        headers={"X-User-Email": "approver@local.test", "If-Match": str(v4)},
    )
    assert r.status_code == 409

    # (Reviewer) submit again should fail (status RETURNED)
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/submit",
        headers={"X-User-Email": "reviewer@local.test", "If-Match": str(v4)},
    )
    assert r.status_code == 409


def test_get_evaluation_access_controls(db_session, client: TestClient):
    admin = create_user(db_session, "admin@local.test", "Admin")
    grant_role(db_session, admin, "ADMIN")

    reviewer_user = create_user(db_session, "reviewer@local.test", "Reviewer")
    approver_user = create_user(db_session, "approver@local.test", "Approver")
    random_user = create_user(db_session, "random@local.test", "Random")

    reviewer_emp = create_employee(db_session, "E200", "Reviewer", user=reviewer_user)
    approver_emp = create_employee(db_session, "E300", "Approver", user=approver_user)
    subject_emp = create_employee(db_session, "E400", "Subject", user=None)

    cycle = create_cycle(db_session, created_by=admin, status="ACTIVE")

    f_q1 = create_field_definition(
        db_session,
        key="q1",
        label="Q1",
        field_type="text",
        required=False,
    )
    form = create_form_template(db_session, name="Eval Form", version=1)
    attach_field_to_form(db_session, form=form, field=f_q1, position=1)
    set_cycle_form_template(db_session, cycle=cycle, form=form)

    assignment = create_assignment(db_session, cycle, reviewer_emp, subject_emp, approver_emp)

    r = client.post(
        f"/cycles/{cycle.id}/assignments/{assignment.id}/evaluation",
        headers={"X-User-Email": "reviewer@local.test"},
    )
    evaluation_id = r.json()["id"]

    # Reviewer can view
    r = client.get(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}",
        headers={"X-User-Email": "reviewer@local.test"},
    )
    assert r.status_code == 200

    # Approver can view
    r = client.get(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}",
        headers={"X-User-Email": "approver@local.test"},
    )
    assert r.status_code == 200

    # Random cannot
    r = client.get(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}",
        headers={"X-User-Email": "random@local.test"},
    )
    assert r.status_code == 403


def test_create_evaluation_idempotency_key_dedupes_audit(db_session, client: TestClient):
    admin = create_user(db_session, "admin@local.test", "Admin")
    grant_role(db_session, admin, "ADMIN")

    reviewer_user = create_user(db_session, "reviewer@local.test", "Reviewer")
    approver_user = create_user(db_session, "approver@local.test", "Approver")

    reviewer_emp = create_employee(db_session, "E200", "Reviewer", user=reviewer_user)
    approver_emp = create_employee(db_session, "E300", "Approver", user=approver_user)
    subject_emp = create_employee(db_session, "E400", "Subject", user=None)

    cycle = create_cycle(db_session, created_by=admin, status="ACTIVE")

    f_q1 = create_field_definition(
        db_session,
        key="q1",
        label="Q1",
        field_type="text",
        required=False,
    )
    form = create_form_template(db_session, name="Eval Form", version=1)
    attach_field_to_form(db_session, form=form, field=f_q1, position=1)
    set_cycle_form_template(db_session, cycle=cycle, form=form)

    assignment = create_assignment(db_session, cycle, reviewer_emp, subject_emp, approver_emp)

    idem_key = "idem-create-eval-1"

    r1 = client.post(
        f"/cycles/{cycle.id}/assignments/{assignment.id}/evaluation",
        headers={"X-User-Email": "reviewer@local.test", "Idempotency-Key": idem_key},
    )
    assert r1.status_code == 201
    ev1 = r1.json()
    evaluation_id = ev1["id"]

    # repeat exact same request with same key -> should return same evaluation and NOT add audit again
    r2 = client.post(
        f"/cycles/{cycle.id}/assignments/{assignment.id}/evaluation",
        headers={"X-User-Email": "reviewer@local.test", "Idempotency-Key": idem_key},
    )
    assert r2.status_code == 201
    ev2 = r2.json()
    assert ev2["id"] == evaluation_id

    # audit only once
    assert _count_audit(db_session, "EVALUATION_CREATED", "evaluation", evaluation_id) == 1

    # idempotency row stored
    row = (
        db_session.query(IdempotencyKey)
        .filter(IdempotencyKey.key == idem_key)
        .one_or_none()
    )
    assert row is not None
    assert row.status == "COMPLETED"


def test_evaluation_optimistic_locking_rejects_stale(db_session, client: TestClient):
    admin = create_user(db_session, "admin@local.test", "Admin")
    grant_role(db_session, admin, "ADMIN")

    reviewer_user = create_user(db_session, "reviewer@local.test", "Reviewer")
    approver_user = create_user(db_session, "approver@local.test", "Approver")

    reviewer_emp = create_employee(db_session, "E200", "Reviewer", user=reviewer_user)
    approver_emp = create_employee(db_session, "E300", "Approver", user=approver_user)
    subject_emp = create_employee(db_session, "E400", "Subject", user=None)

    cycle = create_cycle(db_session, created_by=admin, status="ACTIVE")

    # ✅ attach a form to the cycle so q1 is valid
    create_form_for_cycle_with_fields(
        db_session,
        cycle=cycle,
        fields=[
            {"key": "q1", "field_type": "text", "required": False},
        ],
    )

    assignment = create_assignment(db_session, cycle, reviewer_emp, subject_emp, approver_emp)

    r = client.post(
        f"/cycles/{cycle.id}/assignments/{assignment.id}/evaluation",
        headers={"X-User-Email": "reviewer@local.test"},
    )
    assert r.status_code == 201
    ev = r.json()
    evaluation_id = ev["id"]
    v1 = ev["version"]

    # First mutation with v1
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/draft",
        headers={"X-User-Email": "reviewer@local.test", "If-Match": str(v1)},
        json={"responses": [{"question_key": "q1", "value_text": "hello"}]},
    )
    assert r.status_code == 200
    v2 = r.json()["version"]
    assert v2 != v1

    # Now try again with stale v1 -> 409
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/draft",
        headers={"X-User-Email": "reviewer@local.test", "If-Match": str(v1)},
        json={"responses": [{"question_key": "q1", "value_text": "world"}]},
    )
    assert r.status_code == 409

def test_draft_rejects_unknown_key(db_session, client: TestClient):
    admin = create_user(db_session, "admin@local.test", "Admin")
    grant_role(db_session, admin, "ADMIN")

    reviewer_user = create_user(db_session, "reviewer@local.test", "Reviewer")
    approver_user = create_user(db_session, "approver@local.test", "Approver")

    reviewer_emp = create_employee(db_session, "E200", "Reviewer", user=reviewer_user)
    approver_emp = create_employee(db_session, "E300", "Approver", user=approver_user)
    subject_emp = create_employee(db_session, "E400", "Subject", user=None)

    cycle = create_cycle(db_session, created_by=admin, status="ACTIVE")
    create_form_for_cycle_with_fields(
        db_session,
        cycle=cycle,
        fields=[{"key": "q1", "field_type": "text", "required": False}],
    )

    assignment = create_assignment(db_session, cycle, reviewer_emp, subject_emp, approver_emp)

    r = client.post(
        f"/cycles/{cycle.id}/assignments/{assignment.id}/evaluation",
        headers={"X-User-Email": "reviewer@local.test"},
    )
    assert r.status_code == 201
    ev = r.json()
    evaluation_id = ev["id"]
    v1 = ev["version"]

    # unknown key -> should fail
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/draft",
        headers={"X-User-Email": "reviewer@local.test", "If-Match": str(v1)},
        json={"responses": [{"question_key": "unknown_key", "value_text": "x"}]},
    )
    assert r.status_code in (400, 409)

def test_submit_requires_required_fields(db_session, client: TestClient):
    admin = create_user(db_session, "admin@local.test", "Admin")
    grant_role(db_session, admin, "ADMIN")

    reviewer_user = create_user(db_session, "reviewer@local.test", "Reviewer")
    approver_user = create_user(db_session, "approver@local.test", "Approver")

    reviewer_emp = create_employee(db_session, "E200", "Reviewer", user=reviewer_user)
    approver_emp = create_employee(db_session, "E300", "Approver", user=approver_user)
    subject_emp = create_employee(db_session, "E400", "Subject", user=None)

    cycle = create_cycle(db_session, created_by=admin, status="ACTIVE")

    # ✅ rating is required
    create_form_for_cycle_with_fields(
        db_session,
        cycle=cycle,
        fields=[
            {"key": "q1", "field_type": "text", "required": False},
            {"key": "rating", "field_type": "number", "required": True, "rules": {"min": 1, "max": 5, "integer": True}},
        ],
    )

    assignment = create_assignment(db_session, cycle, reviewer_emp, subject_emp, approver_emp)

    r = client.post(
        f"/cycles/{cycle.id}/assignments/{assignment.id}/evaluation",
        headers={"X-User-Email": "reviewer@local.test"},
    )
    assert r.status_code == 201
    evaluation_id = r.json()["id"]
    v1 = r.json()["version"]

    # Save draft with only q1 (missing required rating is OK for draft)
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/draft",
        headers={"X-User-Email": "reviewer@local.test", "If-Match": str(v1)},
        json={"responses": [{"question_key": "q1", "value_text": "hello"}]},
    )
    assert r.status_code == 200
    v2 = r.json()["version"]

    # Submit should fail because required rating is missing
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/submit",
        headers={"X-User-Email": "reviewer@local.test", "If-Match": str(v2)},
    )
    assert r.status_code in (400, 409)

def test_submit_succeeds_when_required_fields_present(db_session, client: TestClient):
    admin = create_user(db_session, "admin@local.test", "Admin")
    grant_role(db_session, admin, "ADMIN")

    reviewer_user = create_user(db_session, "reviewer@local.test", "Reviewer")
    approver_user = create_user(db_session, "approver@local.test", "Approver")

    reviewer_emp = create_employee(db_session, "E200", "Reviewer", user=reviewer_user)
    approver_emp = create_employee(db_session, "E300", "Approver", user=approver_user)
    subject_emp = create_employee(db_session, "E400", "Subject", user=None)

    cycle = create_cycle(db_session, created_by=admin, status="ACTIVE")

    create_form_for_cycle_with_fields(
        db_session,
        cycle=cycle,
        fields=[
            {"key": "rating", "field_type": "number", "required": True, "rules": {"min": 1, "max": 5, "integer": True}},
        ],
    )

    assignment = create_assignment(db_session, cycle, reviewer_emp, subject_emp, approver_emp)

    r = client.post(
        f"/cycles/{cycle.id}/assignments/{assignment.id}/evaluation",
        headers={"X-User-Email": "reviewer@local.test"},
    )
    assert r.status_code == 201
    evaluation_id = r.json()["id"]
    v1 = r.json()["version"]

    # draft with rating
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/draft",
        headers={"X-User-Email": "reviewer@local.test", "If-Match": str(v1)},
        json={"responses": [{"question_key": "rating", "value_text": "5"}]},
    )
    assert r.status_code == 200
    v2 = r.json()["version"]

    # submit ok
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/submit",
        headers={"X-User-Email": "reviewer@local.test", "If-Match": str(v2)},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "SUBMITTED"


# ===== Validation Preview Tests =====

def test_validate_evaluation_not_found(db_session, client: TestClient):
    """Test validation preview for non-existent evaluation"""
    import uuid
    from tests.helpers import create_user, grant_role, create_cycle
    
    admin = create_user(db_session, "admin@example.com", is_admin=True)
    grant_role(db_session, admin, "ADMIN")
    
    cycle = create_cycle(db_session, created_by=admin, status="ACTIVE")
    
    fake_id = str(uuid.uuid4())
    response = client.post(
        f"/cycles/{cycle.id}/evaluations/{fake_id}/validate",
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 404


def test_validate_evaluation_no_form(db_session, client: TestClient):
    """Test validation preview when cycle has no form template"""
    from datetime import datetime
    from app.models.evaluation import Evaluation
    from tests.helpers import create_user, grant_role, create_cycle, create_employee, create_assignment
    
    admin = create_user(db_session, "admin@example.com", is_admin=True)
    grant_role(db_session, admin, "ADMIN")
    
    # Create admin employee and link to admin user
    admin_emp = create_employee(db_session, "A001", "Admin Employee", user=admin)
    
    reviewer = admin_emp  # Admin is the reviewer
    subject = create_employee(db_session, "S001", "Subject")
    approver = create_employee(db_session, "AP001", "Approver")
    
    cycle = create_cycle(db_session, created_by=admin, status="ACTIVE")
    assignment = create_assignment(
        db_session,
        cycle=cycle,
        reviewer=reviewer,
        subject=subject,
        approver=approver,
    )
    
    evaluation = Evaluation(
        cycle_id=cycle.id,
        assignment_id=assignment.id,
        status="DRAFT",
    )
    db_session.add(evaluation)
    db_session.commit()
    
    response = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation.id}/validate",
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert len(data["errors"]) > 0
    assert any("form" in err["message"].lower() for err in data["errors"])


def test_validate_evaluation_with_errors(db_session, client: TestClient):
    """Test validation preview with validation errors"""
    from datetime import datetime
    from app.models.evaluation import Evaluation
    from app.models.evaluation_response import EvaluationResponse
    from tests.helpers import (
        create_user, grant_role, create_cycle, create_employee, create_assignment,
        create_form_for_cycle_with_fields,
    )
    
    admin = create_user(db_session, "admin@example.com", is_admin=True)
    grant_role(db_session, admin, "ADMIN")
    
    # Create admin employee and link to admin user
    admin_emp = create_employee(db_session, "A001", "Admin Employee", user=admin)
    
    reviewer = admin_emp  # Admin is the reviewer
    subject = create_employee(db_session, "S001", "Subject")
    approver = create_employee(db_session, "AP001", "Approver")
    
    cycle = create_cycle(db_session, created_by=admin, status="ACTIVE")
    create_form_for_cycle_with_fields(
        db_session,
        cycle=cycle,
        fields=[
            {"key": "required_field", "field_type": "text", "required": True},
            {"key": "number_field", "field_type": "number", "required": True, "rules": {"min": 1, "max": 10}},
        ],
    )
    
    assignment = create_assignment(
        db_session,
        cycle=cycle,
        reviewer=reviewer,
        subject=subject,
        approver=approver,
    )
    
    evaluation = Evaluation(
        cycle_id=cycle.id,
        assignment_id=assignment.id,
        status="DRAFT",
    )
    db_session.add(evaluation)
    db_session.flush()
    
    # Add invalid response (missing required field, invalid number)
    response_obj = EvaluationResponse(
        evaluation_id=evaluation.id,
        question_key="number_field",
        value_text="999",  # Exceeds max
    )
    db_session.add(response_obj)
    db_session.commit()
    
    response = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation.id}/validate",
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert len(data["errors"]) > 0
    # Should have error for missing required field
    assert any(err["field"] == "required_field" for err in data["errors"])
    # Should have error for number exceeding max
    assert any(err["field"] == "number_field" and "max" in err["code"] for err in data["errors"])


def test_validate_evaluation_valid(db_session, client: TestClient):
    """Test validation preview with valid evaluation"""
    from datetime import datetime
    from app.models.evaluation import Evaluation
    from app.models.evaluation_response import EvaluationResponse
    from tests.helpers import (
        create_user, grant_role, create_cycle, create_employee, create_assignment,
        create_form_for_cycle_with_fields,
    )
    
    admin = create_user(db_session, "admin@example.com", is_admin=True)
    grant_role(db_session, admin, "ADMIN")
    
    # Create admin employee and link to admin user
    admin_emp = create_employee(db_session, "A001", "Admin Employee", user=admin)
    
    reviewer = admin_emp  # Admin is the reviewer
    subject = create_employee(db_session, "S001", "Subject")
    approver = create_employee(db_session, "AP001", "Approver")
    
    cycle = create_cycle(db_session, created_by=admin, status="ACTIVE")
    create_form_for_cycle_with_fields(
        db_session,
        cycle=cycle,
        fields=[
            {"key": "text_field", "field_type": "text", "required": True},
            {"key": "number_field", "field_type": "number", "required": True, "rules": {"min": 1, "max": 10, "integer": True}},
        ],
    )
    
    assignment = create_assignment(
        db_session,
        cycle=cycle,
        reviewer=reviewer,
        subject=subject,
        approver=approver,
    )
    
    evaluation = Evaluation(
        cycle_id=cycle.id,
        assignment_id=assignment.id,
        status="DRAFT",
    )
    db_session.add(evaluation)
    db_session.flush()
    
    # Add valid responses
    responses = [
        EvaluationResponse(
            evaluation_id=evaluation.id,
            question_key="text_field",
            value_text="Valid text",
        ),
        EvaluationResponse(
            evaluation_id=evaluation.id,
            question_key="number_field",
            value_text="5",
        ),
    ]
    db_session.add_all(responses)
    db_session.commit()
    
    response = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation.id}/validate",
        headers={"X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert len(data["errors"]) == 0
    assert len(data["warnings"]) > 0
    assert any("ready" in w.lower() for w in data["warnings"])


def test_validate_evaluation_access_control(db_session, client: TestClient):
    """Test validation preview access control"""
    from datetime import datetime
    from app.models.evaluation import Evaluation
    from tests.helpers import (
        create_user, grant_role, create_cycle, create_employee, create_assignment,
        create_form_for_cycle_with_fields,
    )
    
    admin = create_user(db_session, "admin@example.com", is_admin=True)
    grant_role(db_session, admin, "ADMIN")
    
    user = create_user(db_session, "user@example.com")
    employee = create_employee(db_session, "E001", "User Employee", user=user)
    
    reviewer = create_employee(db_session, "R001", "Reviewer")
    subject = create_employee(db_session, "S001", "Subject")
    approver = create_employee(db_session, "A001", "Approver")
    
    cycle = create_cycle(db_session, created_by=admin, status="ACTIVE")
    create_form_for_cycle_with_fields(
        db_session,
        cycle=cycle,
        fields=[{"key": "q1", "field_type": "text"}],
    )
    
    # Create assignment where user is NOT involved
    assignment = create_assignment(
        db_session,
        cycle=cycle,
        reviewer=reviewer,
        subject=subject,
        approver=approver,
    )
    
    evaluation = Evaluation(
        cycle_id=cycle.id,
        assignment_id=assignment.id,
        status="DRAFT",
    )
    db_session.add(evaluation)
    db_session.commit()
    
    # User should not be able to validate this evaluation
    response = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation.id}/validate",
        headers={"X-User-Email": "user@example.com"},
    )
    assert response.status_code == 403
