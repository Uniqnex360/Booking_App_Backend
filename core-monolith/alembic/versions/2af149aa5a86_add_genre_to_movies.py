"""add genre to movies

Revision ID: 2af149aa5a86
Revises: 2d3e078653fc
Create Date: 2026-09-18 15:54:26.302629

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2af149aa5a86'
down_revision: Union[str, None] = '2d3e078653fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass