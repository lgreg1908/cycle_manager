from datetime import date, datetime
from pydantic import BaseModel, Field


class ReviewCycleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    start_date: date | None = None
    end_date: date | None = None


class ReviewCycleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    start_date: date | None = None
    end_date: date | None = None


class ReviewCycleOut(BaseModel):
    id: str
    name: str
    start_date: date | None
    end_date: date | None
    status: str
    created_by_user_id: str
    form_template_id: str | None = None
    created_at: datetime
    updated_at: datetime
