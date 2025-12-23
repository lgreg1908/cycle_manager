from app.models.audit_event import AuditEvent

from tests.helpers import (
    create_user, grant_role, create_employee, create_cycle, create_assignment, ensure_role
)

def test_evaluation_cannot_be_created_when_cycle_not_active(db_session, client):
    reviewer_user = create_user(db_session, "reviewer@local.test", "Reviewer")
    # reviewer must be linked to employee
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


def test_evaluation_happy_path_workflow(db_session, client):
    # Users
    admin = create_user(db_session, "admin@local.test", "Admin")
    grant_role(db_session, admin, "ADMIN")

    reviewer_user = create_user(db_session, "reviewer@local.test", "Reviewer")
    approver_user = create_user(db_session, "approver@local.test", "Approver")

    # Employees (link reviewer/approver to their users)
    reviewer_emp = create_employee(db_session, "E200", "Reviewer", user=reviewer_user)
    approver_emp = create_employee(db_session, "E300", "Approver", user=approver_user)
    subject_emp = create_employee(db_session, "E400", "Subject", user=None)

    # ACTIVE cycle + assignment
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

    # (Reviewer) save draft
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/draft",
        headers={"X-User-Email": "reviewer@local.test"},
        json={"responses": [{"question_key": "q1", "value_text": "hello"}]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["responses"]["q1"] == "hello"

    # (Approver) cannot save draft
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/draft",
        headers={"X-User-Email": "approver@local.test"},
        json={"responses": [{"question_key": "q1", "value_text": "nope"}]},
    )
    assert r.status_code == 403

    # (Reviewer) submit
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/submit",
        headers={"X-User-Email": "reviewer@local.test"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "SUBMITTED"

    # (Reviewer) cannot approve
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/approve",
        headers={"X-User-Email": "reviewer@local.test"},
    )
    assert r.status_code == 403

    # (Approver) return
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/return",
        headers={"X-User-Email": "approver@local.test"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "RETURNED"

    # (Approver) cannot approve from RETURNED
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/approve",
        headers={"X-User-Email": "approver@local.test"},
    )
    assert r.status_code == 409

    # (Reviewer) can submit again? should fail because status is RETURNED (your logic: only DRAFT submit)
    r = client.post(
        f"/cycles/{cycle.id}/evaluations/{evaluation_id}/submit",
        headers={"X-User-Email": "reviewer@local.test"},
    )
    assert r.status_code == 409


def test_get_evaluation_access_controls(db_session, client):
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
