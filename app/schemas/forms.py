from datetime import datetime
from pydantic import BaseModel, Field


class FieldDefinitionCreate(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=200)
    field_type: str  # text|number|select|employee_reference|date
    required: bool = False
    rules: dict | None = None


class FieldDefinitionOut(BaseModel):
    id: str
    key: str
    label: str
    field_type: str
    required: bool
    rules: dict | None
    created_at: datetime
    updated_at: datetime


class FormTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    version: int = Field(default=1, ge=1)
    description: str | None = Field(default=None, max_length=500)


class FormTemplateOut(BaseModel):
    id: str
    name: str
    version: int
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class FormTemplateFieldAttach(BaseModel):
    field_definition_id: str
    position: int = Field(ge=1)
    override_label: str | None = Field(default=None, max_length=200)
    override_required: bool | None = None


class FormTemplateWithFieldsOut(BaseModel):
    id: str
    name: str
    version: int
    description: str | None
    is_active: bool
    fields: list[dict]  # keep loose for now (simple output)
