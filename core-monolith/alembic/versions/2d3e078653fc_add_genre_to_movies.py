"""add genre to movies

Revision ID: 2d3e078653fc
Revises: f86481dc3be8
Create Date: 2026-09-18 15:43:44.509270

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2d3e078653fc'
down_revision: Union[str, None] = 'f86481dc3be8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("movies", sa.Column("genre", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("movies", "genre")