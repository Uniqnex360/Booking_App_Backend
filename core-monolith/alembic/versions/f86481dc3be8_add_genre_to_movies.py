"""add genre to movies

Revision ID: f86481dc3be8
Revises: d2a6e735ce95
Create Date: 2026-09-18 15:43:04.027330

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f86481dc3be8'
down_revision: Union[str, None] = 'd2a6e735ce95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("movies", sa.Column("genre", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("movies", "genre")