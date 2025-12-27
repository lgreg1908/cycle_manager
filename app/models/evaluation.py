import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, CheckConstraint, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
import sqlalchemy as sa

from app.db.base import Base


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint("assignment_id", name="uq_evaluations_assignment"),
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','APPROVED','RETURNED')",
            name="ck_evaluations_status",
        ),

        # Timestamp sanity (DB invariant)
        # DRAFT => no submitted/approved timestamps
        CheckConstraint(
            "(status <> 'DRAFT') OR (submitted_at IS NULL AND approved_at IS NULL)",
            name="ck_eval_ts_draft",
        ),
        # SUBMITTED => must have submitted_at; must not have approved_at
        CheckConstraint(
            "(status <> 'SUBMITTED') OR (submitted_at IS NOT NULL AND approved_at IS NULL)",
            name="ck_eval_ts_submitted",
        ),
        # APPROVED => must have both submitted_at + approved_at
        CheckConstraint(
            "(status <> 'APPROVED') OR (submitted_at IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_eval_ts_approved",
        ),
        # RETURNED => must have submitted_at; must not have approved_at
        CheckConstraint(
            "(status <> 'RETURNED') OR (submitted_at IS NOT NULL AND approved_at IS NULL)",
            name="ck_eval_ts_returned",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    cycle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("review_cycles.id", ondelete="CASCADE"),
        nullable=False,
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("review_assignments.id", ondelete="CASCADE"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
        onupdate=datetime.utcnow,
    )
    # Optimistic locking
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
