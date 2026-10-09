"""add genre to movies

Revision ID: d2a6e735ce95
Revises: e39bb706e9f8
Create Date: 2026-09-18 15:38:22.809820

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2a6e735ce95'
down_revision: Union[str, None] = 'e39bb706e9f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "movies",
        sa.Column("genre", sa.String(120), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("movies", "genre")