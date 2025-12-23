from datetime import datetime
from pydantic import BaseModel, Field


class AssignmentCreate(BaseModel):
    reviewer_employee_id: str
    subject_employee_id: str
    approver_employee_id: str


class AssignmentBulkCreate(BaseModel):
    items: list[AssignmentCreate] = Field(min_length=1)


class AssignmentOut(BaseModel):
    id: str
    cycle_id: str
    reviewer_employee_id: str
    subject_employee_id: str
    approver_employee_id: str
    status: str
    created_at: datetime
