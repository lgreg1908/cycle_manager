import uuid
from datetime import datetime, date

from sqlalchemy import String, Date, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
import sqlalchemy as sa

from app.db.base import Base


class ReviewCycle(Base):
    __tablename__ = "review_cycles"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','ACTIVE','CLOSED','ARCHIVED')",
            name="ck_review_cycles_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    form_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("form_templates.id", ondelete="SET NULL"),
        nullable=True,
)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
        onupdate=datetime.utcnow,
    )