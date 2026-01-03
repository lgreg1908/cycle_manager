"""
Comprehensive end-to-end workflow tests covering complete Postman collection scenarios.

This test suite focuses on full workflow integration tests. Individual unit tests
for specific endpoints are in their respective domain test files:
- test_health.py - Health and root endpoint tests
- test_me.py - User info and stats tests
- test_cycles.py - Cycle management and readiness tests
- test_forms.py - Form and field definition tests
- test_assignments.py - Assignment management tests
- test_evaluations.py - Evaluation workflow and error tests
- test_employees.py - Employee management tests
- test_audit.py - Audit and admin tests
"""

import uuid
from fastapi.testclient import TestClient

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
    create_form_for_cycle_with_fields,
)
from app.models.review_cycle import ReviewCycle


class TestCompleteAdminWorkflow:
    """Complete Admin Workflow: Cycle Setup from Start to Finish"""

    def test_complete_cycle_setup_workflow(self, db_session, client: TestClient):
        """Complete admin workflow: create cycle, fields, form, assignments, activate"""
        # Setup users and employees
        admin = create_user(db_session, "admin@local.test", "Admin")
        grant_role(db_session, admin, "ADMIN")

        reviewer_user = create_user(db_session, "reviewer@local.test", "Reviewer")
        approver_user = create_user(db_session, "approver@local.test", "Approver")
        subject_user = create_user(db_session, "subject@local.test", "Subject")

        reviewer_emp = create_employee(db_session, "E001", "Reviewer Employee", user=reviewer_user)
        approver_emp = create_employee(db_session, "E002", "Approver Employee", user=approver_user)
        subject_emp = create_employee(db_session, "E003", "Subject Employee", user=subject_user)

        # Create Review Cycle
        response = client.post(
            "/cycles",
            headers={"X-User-Email": "admin@local.test"},
            json={
                "name": "Q4 2024 Performance Reviews",
                "start_date": "2024-10-01",
                "end_date": "2024-12-31",
            },
        )
        assert response.status_code == 201
        cycle_data = response.json()
        cycle_id = cycle_data["id"]
        assert cycle_data["status"] == "DRAFT"

        # Check Cycle Readiness (before setup)
        response = client.get(
            f"/cycles/{cycle_id}/readiness",
            headers={"X-User-Email": "admin@local.test"},
        )
        assert response.status_code == 200
        readiness = response.json()
        assert readiness["ready"] is False
        assert readiness["checks"]["has_form_template"] is False
        assert readiness["checks"]["has_assignments"] is False

        # Create Field Definitions
        response = client.post(
            "/forms/fields",
            headers={"X-User-Email": "admin@local.test"},
            json={
                "key": "overall_rating",
                "label": "Overall Performance Rating",
                "field_type": "number",
                "required": True,
                "rules": {"min": 1, "max": 5, "integer": True},
            },
        )
        assert response.status_code == 201
        field1_data = response.json()
        field_definition_id_1 = field1_data["id"]

        response = client.post(
            "/forms/fields",
            headers={"X-User-Email": "admin@local.test"},
            json={
                "key": "q1",
                "label": "Comments",
                "field_type": "text",
                "required": False,
            },
        )
        assert response.status_code == 201
        field2_data = response.json()
        field_definition_id_2 = field2_data["id"]

        # Create Form Template
        response = client.post(
            "/forms",
            headers={"X-User-Email": "admin@local.test"},
            json={
                "name": "Standard Performance Review Form",
                "version": 1,
                "description": "Standard form for performance reviews",
            },
        )
        assert response.status_code == 201
        form_data = response.json()
        form_template_id = form_data["id"]

        # Attach Fields to Form
        response = client.post(
            f"/forms/{form_template_id}/fields",
            headers={"X-User-Email": "admin@local.test"},
            json=[
                {
                    "field_definition_id": field_definition_id_1,
                    "position": 1,
                    "override_required": True,
                }
            ],
        )
        assert response.status_code == 200

        response = client.post(
            f"/forms/{form_template_id}/fields",
            headers={"X-User-Email": "admin@local.test"},
            json=[
                {
                    "field_definition_id": field_definition_id_2,
                    "position": 2,
                    "override_required": False,
                }
            ],
        )
        assert response.status_code == 200

        # Assign Form to Cycle
        response = client.post(
            f"/cycles/{cycle_id}/set-form/{form_template_id}",
            headers={"X-User-Email": "admin@local.test"},
        )
        assert response.status_code == 200

        # Bulk Create Assignments
        response = client.post(
            f"/cycles/{cycle_id}/assignments/bulk",
            headers={"X-User-Email": "admin@local.test"},
            json={
                "items": [
                    {
                        "reviewer_employee_id": str(reviewer_emp.id),
                        "subject_employee_id": str(subject_emp.id),
                        "approver_employee_id": str(approver_emp.id),
                    }
                ]
            },
        )
        assert response.status_code == 201
        assignments_data = response.json()
        assert len(assignments_data) == 1
        assignment_id = assignments_data[0]["id"]

        # Check Cycle Readiness (after setup)
        response = client.get(
            f"/cycles/{cycle_id}/readiness",
            headers={"X-User-Email": "admin@local.test"},
        )
        assert response.status_code == 200
        readiness = response.json()
        assert readiness["can_activate"] is True
        assert readiness["checks"]["has_form_template"] is True
        assert readiness["checks"]["has_assignments"] is True
        assert readiness["ready"] is True

        # Activate Cycle
        response = client.post(
            f"/cycles/{cycle_id}/activate",
            headers={"X-User-Email": "admin@local.test"},
        )
        assert response.status_code == 200
        cycle_data = response.json()
        assert cycle_data["status"] == "ACTIVE"


class TestCompleteReviewerWorkflow:
    """Complete Reviewer Workflow: Create, Draft, Submit Evaluation"""

    def test_complete_reviewer_workflow(self, db_session, client: TestClient):
        """Complete reviewer workflow: get assignments, create eval, save draft, submit"""
        # Setup: Create complete cycle setup
        admin = create_user(db_session, "admin@local.test", "Admin")
        grant_role(db_session, admin, "ADMIN")

        reviewer_user = create_user(db_session, "reviewer@local.test", "Reviewer")
        approver_user = create_user(db_session, "approver@local.test", "Approver")
        subject_user = create_user(db_session, "subject@local.test", "Subject")

        reviewer_emp = create_employee(db_session, "E001", "Reviewer Employee", user=reviewer_user)
        approver_emp = create_employee(db_session, "E002", "Approver Employee", user=approver_user)
        subject_emp = create_employee(db_session, "E003", "Subject Employee", user=subject_user)

        # Create cycle
        cycle = create_cycle(db_session, created_by=admin, status="ACTIVE")
        cycle_id = str(cycle.id)

        # Create form with fields
        create_form_for_cycle_with_fields(
            db_session,
            cycle=cycle,
            fields=[
                {"key": "overall_rating", "field_type": "number", "required": True, "rules": {"min": 1, "max": 5}},
                {"key": "q1", "field_type": "text", "required": False},
            ],
        )

        # Create assignment
        assignment = create_assignment(db_session, cycle, reviewer_emp, subject_emp, approver_emp)
        assignment_id = str(assignment.id)

        # Get My Assignments (as Reviewer)
        response = client.get(
            "/me/assignments",
            headers={"X-User-Email": "reviewer@local.test"},
            params={"role": "reviewer"},
        )
        assert response.status_code == 200
        assignments = response.json()
        assert len(assignments) >= 1
        my_assignment = next(a for a in assignments if a["id"] == assignment_id)
        assert my_assignment["status"] == "ACTIVE"

        # Create or Get Evaluation
        idempotency_key = str(uuid.uuid4())
        response = client.post(
            f"/cycles/{cycle_id}/assignments/{assignment_id}/evaluation",
            headers={
                "X-User-Email": "reviewer@local.test",
                "Idempotency-Key": idempotency_key,
            },
        )
        assert response.status_code == 201
        eval_data = response.json()
        evaluation_id = eval_data["id"]
        evaluation_version = eval_data["version"]
        assert eval_data["status"] == "DRAFT"

        # Verify idempotency
        response2 = client.post(
            f"/cycles/{cycle_id}/assignments/{assignment_id}/evaluation",
            headers={
                "X-User-Email": "reviewer@local.test",
                "Idempotency-Key": idempotency_key,
            },
        )
        assert response2.status_code == 201
        assert response2.json()["id"] == evaluation_id

        # Get Evaluation Details
        response = client.get(
            f"/cycles/{cycle_id}/evaluations/{evaluation_id}",
            headers={"X-User-Email": "reviewer@local.test"},
        )
        assert response.status_code == 200
        eval_details = response.json()
        assert eval_details["id"] == evaluation_id
        assert eval_details["status"] == "DRAFT"

        # Save Draft
        response = client.post(
            f"/cycles/{cycle_id}/evaluations/{evaluation_id}/draft",
            headers={
                "X-User-Email": "reviewer@local.test",
                "If-Match": str(evaluation_version),
            },
            json={
                "responses": [
                    {"question_key": "overall_rating", "value_text": "4"},
                    {"question_key": "q1", "value_text": "Great work this quarter!"},
                ]
            },
        )
        assert response.status_code == 200
        evaluation_version = response.json()["version"]

        # Validate Draft
        response = client.post(
            f"/cycles/{cycle_id}/evaluations/{evaluation_id}/validate",
            headers={"X-User-Email": "reviewer@local.test"},
        )
        assert response.status_code == 200
        validation = response.json()
        assert validation["valid"] is True
        assert len(validation["errors"]) == 0

        # Submit Evaluation
        response = client.post(
            f"/cycles/{cycle_id}/evaluations/{evaluation_id}/submit",
            headers={
                "X-User-Email": "reviewer@local.test",
                "If-Match": str(evaluation_version),
            },
        )
        assert response.status_code == 200
        submitted_data = response.json()
        assert submitted_data["status"] == "SUBMITTED"
        assert submitted_data["submitted_at"] is not None


class TestCompleteApproverWorkflow:
    """Complete Approver Workflow: Review, Approve, and Return Evaluations"""

    def test_complete_approver_workflow(self, db_session, client: TestClient):
        """Complete approver workflow: get assignments, list evaluations, approve"""
        # Setup: Create complete cycle setup with submitted evaluation
        admin = create_user(db_session, "admin@local.test", "Admin")
        grant_role(db_session, admin, "ADMIN")

        reviewer_user = create_user(db_session, "reviewer@local.test", "Reviewer")
        approver_user = create_user(db_session, "approver@local.test", "Approver")
        subject_user = create_user(db_session, "subject@local.test", "Subject")

        reviewer_emp = create_employee(db_session, "E001", "Reviewer Employee", user=reviewer_user)
        approver_emp = create_employee(db_session, "E002", "Approver Employee", user=approver_user)
        subject_emp = create_employee(db_session, "E003", "Subject Employee", user=subject_user)

        # Create cycle
        cycle = create_cycle(db_session, created_by=admin, status="ACTIVE")
        cycle_id = str(cycle.id)

        # Create form with fields
        create_form_for_cycle_with_fields(
            db_session,
            cycle=cycle,
            fields=[
                {"key": "overall_rating", "field_type": "number", "required": True, "rules": {"min": 1, "max": 5}},
                {"key": "q1", "field_type": "text", "required": False},
            ],
        )

        # Create assignment
        assignment = create_assignment(db_session, cycle, reviewer_emp, subject_emp, approver_emp)

        # Create and submit evaluation
        response = client.post(
            f"/cycles/{cycle_id}/assignments/{assignment.id}/evaluation",
            headers={"X-User-Email": "reviewer@local.test"},
        )
        assert response.status_code == 201
        eval_data = response.json()
        evaluation_id = eval_data["id"]
        evaluation_version = eval_data["version"]

        # Save draft
        response = client.post(
            f"/cycles/{cycle_id}/evaluations/{evaluation_id}/draft",
            headers={
                "X-User-Email": "reviewer@local.test",
                "If-Match": str(evaluation_version),
            },
            json={
                "responses": [
                    {"question_key": "overall_rating", "value_text": "4"},
                    {"question_key": "q1", "value_text": "Great work!"},
                ]
            },
        )
        assert response.status_code == 200
        evaluation_version = response.json()["version"]

        # Submit evaluation
        response = client.post(
            f"/cycles/{cycle_id}/evaluations/{evaluation_id}/submit",
            headers={
                "X-User-Email": "reviewer@local.test",
                "If-Match": str(evaluation_version),
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "SUBMITTED"

        # Get My Assignments (as Approver)
        response = client.get(
            "/me/assignments",
            headers={"X-User-Email": "approver@local.test"},
            params={"role": "approver"},
        )
        assert response.status_code == 200
        assignments = response.json()
        assert len(assignments) >= 1

        # List Evaluations (Pending Approval)
        response = client.get(
            f"/cycles/{cycle_id}/evaluations",
            headers={"X-User-Email": "approver@local.test"},
            params={"status": "SUBMITTED"},
        )
        assert response.status_code == 200
        evaluations = response.json()
        assert len(evaluations) >= 1
        pending_eval = next(e for e in evaluations if e["id"] == evaluation_id)
        assert pending_eval["status"] == "SUBMITTED"

        # Get Evaluation for Approval
        response = client.get(
            f"/cycles/{cycle_id}/evaluations/{evaluation_id}",
            headers={"X-User-Email": "approver@local.test"},
        )
        assert response.status_code == 200
        eval_for_approval = response.json()
        assert eval_for_approval["status"] == "SUBMITTED"
        evaluation_version = eval_for_approval["version"]

        # Approve Evaluation
        response = client.post(
            f"/cycles/{cycle_id}/evaluations/{evaluation_id}/approve",
            headers={
                "X-User-Email": "approver@local.test",
                "If-Match": str(evaluation_version),
                "Idempotency-Key": f"approve-{uuid.uuid4()}",
            },
        )
        assert response.status_code == 200
        approved_data = response.json()
        assert approved_data["status"] == "APPROVED"
        assert approved_data["approved_at"] is not None

        # Test Return Evaluation (with a new evaluation)
        subject_emp2 = create_employee(db_session, "E004", "Subject Employee 2", user=None)
        assignment2 = create_assignment(db_session, cycle, reviewer_emp, subject_emp2, approver_emp)
        
        response = client.post(
            f"/cycles/{cycle_id}/assignments/{assignment2.id}/evaluation",
            headers={"X-User-Email": "reviewer@local.test"},
        )
        assert response.status_code == 201
        eval_data2 = response.json()
        eval_id_2 = eval_data2["id"]
        eval_version_2 = eval_data2["version"]

        # Save and submit
        response = client.post(
            f"/cycles/{cycle_id}/evaluations/{eval_id_2}/draft",
            headers={
                "X-User-Email": "reviewer@local.test",
                "If-Match": str(eval_version_2),
            },
            json={
                "responses": [
                    {"question_key": "overall_rating", "value_text": "3"},
                    {"question_key": "q1", "value_text": "Good work"},
                ]
            },
        )
        eval_version_2 = response.json()["version"]

        response = client.post(
            f"/cycles/{cycle_id}/evaluations/{eval_id_2}/submit",
            headers={
                "X-User-Email": "reviewer@local.test",
                "If-Match": str(eval_version_2),
            },
        )
        assert response.status_code == 200

        # Return evaluation
        response = client.get(
            f"/cycles/{cycle_id}/evaluations/{eval_id_2}",
            headers={"X-User-Email": "approver@local.test"},
        )
        return_version = response.json()["version"]

        response = client.post(
            f"/cycles/{cycle_id}/evaluations/{eval_id_2}/return",
            headers={
                "X-User-Email": "approver@local.test",
                "If-Match": str(return_version),
                "Idempotency-Key": f"return-{uuid.uuid4()}",
            },
            json={"reason": "Needs more detail on collaboration"},
        )
        assert response.status_code == 200
        returned_data = response.json()
        assert returned_data["status"] == "RETURNED"


class TestCompleteEndToEndWorkflow:
    """Complete End-to-End Workflow: Setup → Review → Approve → Close"""

    def test_complete_workflow_from_start_to_finish(self, db_session, client: TestClient):
        """Run complete workflow: Setup → Review → Approve → Close"""
        # 1. Setup & Health
        response = client.get("/health")
        assert response.status_code == 200

        response = client.get("/")
        assert response.status_code == 200

        # 2. Admin Setup
        admin = create_user(db_session, "admin@local.test", "Admin")
        grant_role(db_session, admin, "ADMIN")

        reviewer_user = create_user(db_session, "reviewer@local.test", "Reviewer")
        approver_user = create_user(db_session, "approver@local.test", "Approver")
        subject_user = create_user(db_session, "subject@local.test", "Subject")

        reviewer_emp = create_employee(db_session, "E001", "Reviewer", user=reviewer_user)
        approver_emp = create_employee(db_session, "E002", "Approver", user=approver_user)
        subject_emp = create_employee(db_session, "E003", "Subject", user=subject_user)

        # Create cycle
        response = client.post(
            "/cycles",
            headers={"X-User-Email": "admin@local.test"},
            json={"name": "E2E Test Cycle", "start_date": "2024-01-01", "end_date": "2024-12-31"},
        )
        assert response.status_code == 201
        cycle_id = response.json()["id"]

        # Create form
        field = create_field_definition(db_session, key="rating", field_type="number", required=True)
        form = create_form_template(db_session, name="Test Form", version=1)
        attach_field_to_form(db_session, form=form, field=field, position=1)
        cycle = db_session.get(ReviewCycle, cycle_id)
        set_cycle_form_template(db_session, cycle=cycle, form=form)

        # Create assignment (cycle is already DRAFT from creation)
        response = client.post(
            f"/cycles/{cycle_id}/assignments/bulk",
            headers={"X-User-Email": "admin@local.test"},
            json={
                "items": [
                    {
                        "reviewer_employee_id": str(reviewer_emp.id),
                        "subject_employee_id": str(subject_emp.id),
                        "approver_employee_id": str(approver_emp.id),
                    }
                ]
            },
        )
        assert response.status_code == 201
        assignment_id = response.json()[0]["id"]

        # Activate cycle
        response = client.post(
            f"/cycles/{cycle_id}/activate",
            headers={"X-User-Email": "admin@local.test"},
        )
        assert response.status_code == 200

        # 3. Reviewer Workflow
        response = client.post(
            f"/cycles/{cycle_id}/assignments/{assignment_id}/evaluation",
            headers={"X-User-Email": "reviewer@local.test"},
        )
        assert response.status_code == 201
        evaluation_id = response.json()["id"]
        eval_version = response.json()["version"]

        response = client.post(
            f"/cycles/{cycle_id}/evaluations/{evaluation_id}/draft",
            headers={
                "X-User-Email": "reviewer@local.test",
                "If-Match": str(eval_version),
            },
            json={"responses": [{"question_key": "rating", "value_text": "4"}]},
        )
        assert response.status_code == 200
        eval_version = response.json()["version"]

        response = client.post(
            f"/cycles/{cycle_id}/evaluations/{evaluation_id}/submit",
            headers={
                "X-User-Email": "reviewer@local.test",
                "If-Match": str(eval_version),
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "SUBMITTED"

        # 4. Approver Workflow
        eval_version = response.json()["version"]
        response = client.post(
            f"/cycles/{cycle_id}/evaluations/{evaluation_id}/approve",
            headers={
                "X-User-Email": "approver@local.test",
                "If-Match": str(eval_version),
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "APPROVED"

        # 5. Statistics
        response = client.get(
            f"/cycles/{cycle_id}/stats",
            headers={"X-User-Email": "admin@local.test"},
        )
        assert response.status_code == 200

        # 6. Close Cycle
        response = client.post(
            f"/cycles/{cycle_id}/close",
            headers={"X-User-Email": "admin@local.test"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "CLOSED"
