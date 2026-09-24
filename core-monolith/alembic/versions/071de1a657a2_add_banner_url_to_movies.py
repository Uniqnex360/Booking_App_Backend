"""add banner_url to movies

Revision ID: 071de1a657a2
Revises: f25fb7bf7d23
Create Date: 2026-09-24 13:19:48.082554

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '071de1a657a2'
down_revision: Union[str, None] = 'f25fb7bf7d23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column("movies", sa.Column("banner_url", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("movies", "banner_url")
