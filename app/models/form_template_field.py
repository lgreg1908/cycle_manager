import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
import sqlalchemy as sa

from app.db.base import Base


class FormTemplateField(Base):
    __tablename__ = "form_template_fields"
    __table_args__ = (
        UniqueConstraint("form_template_id", "field_definition_id", name="uq_form_field_unique"),
        UniqueConstraint("form_template_id", "position", name="uq_form_field_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    form_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("form_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("field_definitions.id", ondelete="RESTRICT"),
        nullable=False,
    )

    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # Optional overrides (if None, use field_definitions.*)
    override_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    override_required: Mapped[bool | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
    form = relationship("FormTemplate", back_populates="fields", lazy="selectin")
    field = relationship("FieldDefinition", lazy="selectin")
