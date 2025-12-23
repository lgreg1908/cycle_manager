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
    v = ev["version"]

    # audit exists exactly once
    assert _count_audit(db_session, "EVALUATION_CREATED", "evaluation", evaluation_id) == 1

    # (Reviewer) save draft
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/draft",
        headers={"X-User-Email": "reviewer@local.test", "If-Match": str(v)},
        json={"responses": [{"question_key": "q1", "value_text": "hello"}]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["responses"]["q1"] == "hello"
    assert _count_audit(db_session, "EVALUATION_DRAFT_SAVED", "evaluation", evaluation_id) == 1
    v = body["version"]

    # (Approver) cannot save draft (still include If-Match so we don't get 428)
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/draft",
        headers={"X-User-Email": "approver@local.test", "If-Match": str(v)},
        json={"responses": [{"question_key": "q1", "value_text": "nope"}]},
    )
    assert r.status_code == 403

    # (Reviewer) submit
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/submit",
        headers={"X-User-Email": "reviewer@local.test", "If-Match": str(v)},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "SUBMITTED"
    assert _count_audit(db_session, "EVALUATION_SUBMITTED", "evaluation", evaluation_id) == 1
    v = r.json()["version"]

    # (Reviewer) cannot approve (include If-Match to avoid 428)
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/approve",
        headers={"X-User-Email": "reviewer@local.test", "If-Match": str(v)},
    )
    assert r.status_code == 403

    # (Approver) return
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/return",
        headers={"X-User-Email": "approver@local.test", "If-Match": str(v)},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "RETURNED"
    assert _count_audit(db_session, "EVALUATION_RETURNED", "evaluation", evaluation_id) == 1
    v = r.json()["version"]

    # (Approver) cannot approve from RETURNED (include If-Match)
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/approve",
        headers={"X-User-Email": "approver@local.test", "If-Match": str(v)},
    )
    assert r.status_code == 409

    # (Reviewer) submit again should fail (status RETURNED) (include If-Match)
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/submit",
        headers={"X-User-Email": "reviewer@local.test", "If-Match": str(v)},
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


def test_save_draft_requires_if_match(db_session, client: TestClient):
    admin = create_user(db_session, "admin@local.test", "Admin")
    grant_role(db_session, admin, "ADMIN")

    reviewer_user = create_user(db_session, "reviewer@local.test", "Reviewer")
    approver_user = create_user(db_session, "approver@local.test", "Approver")

    reviewer_emp = create_employee(db_session, "E200", "Reviewer", user=reviewer_user)
    approver_emp = create_employee(db_session, "E300", "Approver", user=approver_user)
    subject_emp = create_employee(db_session, "E400", "Subject", user=None)

    cycle = create_cycle(db_session, created_by=admin, status="ACTIVE")
    assignment = create_assignment(db_session, cycle, reviewer_emp, subject_emp, approver_emp)

    r = client.post(
        f"/cycles/{cycle.id}/assignments/{assignment.id}/evaluation",
        headers={"X-User-Email": "reviewer@local.test"},
    )
    evaluation_id = r.json()["id"]

    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/draft",
        headers={"X-User-Email": "reviewer@local.test"},
        json={"responses": [{"question_key": "q1", "value_text": "hello"}]},
    )
    assert r.status_code == 428


def test_save_draft_rejects_invalid_if_match(db_session, client: TestClient):
    admin = create_user(db_session, "admin@local.test", "Admin")
    grant_role(db_session, admin, "ADMIN")

    reviewer_user = create_user(db_session, "reviewer@local.test", "Reviewer")
    approver_user = create_user(db_session, "approver@local.test", "Approver")

    reviewer_emp = create_employee(db_session, "E200", "Reviewer", user=reviewer_user)
    approver_emp = create_employee(db_session, "E300", "Approver", user=approver_user)
    subject_emp = create_employee(db_session, "E400", "Subject", user=None)

    cycle = create_cycle(db_session, created_by=admin, status="ACTIVE")
    assignment = create_assignment(db_session, cycle, reviewer_emp, subject_emp, approver_emp)

    r = client.post(
        f"/cycles/{cycle.id}/assignments/{assignment.id}/evaluation",
        headers={"X-User-Email": "reviewer@local.test"},
    )
    evaluation_id = r.json()["id"]

    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/draft",
        headers={"X-User-Email": "reviewer@local.test", "If-Match": "abc"},
        json={"responses": [{"question_key": "q1", "value_text": "hello"}]},
    )
    assert r.status_code == 400
