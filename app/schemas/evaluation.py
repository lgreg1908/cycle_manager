from datetime import datetime
from pydantic import BaseModel, Field


class EvaluationOut(BaseModel):
    id: str
    cycle_id: str
    assignment_id: str
    status: str
    submitted_at: datetime | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ResponseUpsert(BaseModel):
    question_key: str = Field(min_length=1, max_length=100)
    value_text: str | None = None


class SaveDraftPayload(BaseModel):
    responses: list[ResponseUpsert] = Field(default_factory=list)


class EvaluationWithResponsesOut(EvaluationOut):
    responses: dict[str, str | None]
