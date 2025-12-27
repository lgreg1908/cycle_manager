from pydantic import BaseModel


class ValidationError(BaseModel):
    """Individual validation error"""
    field: str
    code: str  # required, type, min, max, choice, not_found, etc.
    message: str


class ValidationPreviewResponse(BaseModel):
    """Response from validation preview endpoint"""
    valid: bool
    errors: list[ValidationError]
    warnings: list[str]  # Non-blocking warnings

