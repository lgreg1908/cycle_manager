import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FieldDefinition(Base):
    __tablename__ = "field_definitions"
    __table_args__ = (
        CheckConstraint(
            "field_type IN ('text','number','select','employee_reference','date')",
            name="ck_field_definitions_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # stable key used in EvaluationResponse.question_key
    key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)

    label: Mapped[str] = mapped_column(String(200), nullable=False)
    field_type: Mapped[str] = mapped_column(String(40), nullable=False)

    # base-level required default (form can override)
    required: Mapped[bool] = mapped_column(nullable=False, default=False)

    # validation rules, examples:
    # number: {"min":1,"max":5,"integer":true}
    # select: {"choices":["Meets","Exceeds"]}
    # text: {"max_length":2000}
    rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
