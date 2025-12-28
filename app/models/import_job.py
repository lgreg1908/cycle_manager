import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String, CheckConstraint, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ImportJob(Base):
    __tablename__ = "import_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','PROCESSING','COMPLETED','FAILED')",
            name="ck_import_job_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=sa.text("'PENDING'"))
    phase: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Current import phase

    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0-100
    total_records: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Summary statistics
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()"), onupdate=datetime.utcnow
    )

