from pydantic import BaseModel


class CycleReadinessCheck(BaseModel):
    """Result of cycle readiness check"""
    ready: bool
    can_activate: bool
    checks: dict[str, bool]  # Individual check results
    warnings: list[str]  # Non-blocking warnings
    errors: list[str]  # Blocking errors


