"""tighten evaluation constraints

Revision ID: 83a9ccb0b0a0
Revises: 8dcc6b1c7003
Create Date: 2025-12-26 16:39:51.339614
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "83a9ccb0b0a0"
down_revision: Union[str, None] = "8dcc6b1c7003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns as nullable with server_default so existing rows can be populated.
    op.add_column(
        "evaluation_responses",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
    )

    op.add_column(
        "review_assignments",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
    )

    # Backfill explicitly (safe even if server_default already populated on add)
    op.execute(
        "UPDATE evaluation_responses SET created_at = now() WHERE created_at IS NULL"
    )
    op.execute(
        "UPDATE review_assignments SET updated_at = now() WHERE updated_at IS NULL"
    )

    # Tighten to NOT NULL
    op.alter_column("evaluation_responses", "created_at", nullable=False)
    op.alter_column("review_assignments", "updated_at", nullable=False)

    # Keep server_default=now() to prevent NULLs on raw inserts.
    # If you want to remove defaults later, do it in a separate migration.


def downgrade() -> None:
    op.drop_column("review_assignments", "updated_at")
    op.drop_column("evaluation_responses", "created_at")
