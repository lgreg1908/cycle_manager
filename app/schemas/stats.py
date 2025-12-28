from pydantic import BaseModel


class UserStats(BaseModel):
    """Statistics for the current user"""
    total_evaluations: int = 0
    evaluations_by_status: dict[str, int] = {}  # DRAFT, SUBMITTED, APPROVED, RETURNED
    total_assignments: int = 0
    assignments_by_role: dict[str, int] = {}  # reviewer, approver, subject
    assignments_by_status: dict[str, int] = {}  # ACTIVE, INACTIVE


class CycleStats(BaseModel):
    """Statistics for a review cycle"""
    cycle_id: str
    cycle_name: str
    cycle_status: str
    total_assignments: int = 0
    active_assignments: int = 0
    inactive_assignments: int = 0
    total_evaluations: int = 0
    evaluations_by_status: dict[str, int] = {}  # DRAFT, SUBMITTED, APPROVED, RETURNED
    completion_rate: float = 0.0  # Percentage of assignments with evaluations
    submitted_rate: float = 0.0  # Percentage of evaluations submitted
    approved_rate: float = 0.0  # Percentage of evaluations approved


