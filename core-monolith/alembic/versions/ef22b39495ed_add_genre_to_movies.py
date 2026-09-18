"""add genre to movies

Revision ID: ef22b39495ed
Revises: 2af149aa5a86
Create Date: 2026-09-18 17:54:32.063465

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ef22b39495ed'
down_revision: Union[str, None] = '2af149aa5a86'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("movies", sa.Column("genre", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("movies", "genre")