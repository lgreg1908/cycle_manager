"""add idempotency keys

Revision ID: 8d171f5d675f
Revises: 07aa1f4a2b50
Create Date: 2025-12-22 23:56:11.795646

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8d171f5d675f'
down_revision: Union[str, None] = '07aa1f4a2b50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
