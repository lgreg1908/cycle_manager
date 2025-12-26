import uuid
from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
import sqlalchemy as sa

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at = mapped_column(DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)
    updated_at = mapped_column(DateTime(timezone=True), server_default=sa.text("now()"), onupdate=datetime.utcnow, nullable=False)
