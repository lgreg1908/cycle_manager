from pydantic import BaseModel, Field
from datetime import datetime


class EmployeeOut(BaseModel):
    id: str
    employee_number: str
    display_name: str
    user_id: str | None


class EmployeeWithUserOut(EmployeeOut):
    user_email: str | None
    user_full_name: str | None


class BulkEmployeeLookupRequest(BaseModel):
    """Request to lookup multiple employees by ID"""
    employee_ids: list[str] = Field(min_length=1, max_length=100, description="List of employee IDs to lookup")


class BulkEmployeeLookupResponse(BaseModel):
    """Response with found employees and missing IDs"""
    employees: list[EmployeeOut]
    missing_ids: list[str]  # IDs that were not found
