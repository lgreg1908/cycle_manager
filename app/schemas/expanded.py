from pydantic import BaseModel


class EmployeeInfo(BaseModel):
    """Minimal employee information for expanded responses"""
    id: str
    employee_number: str
    display_name: str


class AssignmentOutExpanded(BaseModel):
    """Assignment with employee names included"""
    id: str
    cycle_id: str
    reviewer_employee_id: str
    reviewer_name: str | None = None
    reviewer_employee_number: str | None = None
    subject_employee_id: str
    subject_name: str | None = None
    subject_employee_number: str | None = None
    approver_employee_id: str
    approver_name: str | None = None
    approver_employee_number: str | None = None
    status: str
    created_at: str  # datetime as ISO string


class EvaluationOutExpanded(BaseModel):
    """Evaluation with assignment context (employee names)"""
    id: str
    cycle_id: str
    assignment_id: str
    status: str
    submitted_at: str | None  # datetime as ISO string
    approved_at: str | None  # datetime as ISO string
    created_at: str  # datetime as ISO string
    updated_at: str  # datetime as ISO string
    version: int
    # Assignment context
    reviewer_employee_id: str | None = None
    reviewer_name: str | None = None
    subject_employee_id: str | None = None
    subject_name: str | None = None
    approver_employee_id: str | None = None
    approver_name: str | None = None




