"""add external rating fields to movies

Revision ID: d0242ed287f4
Revises: 5b8d86afa4f5
Create Date: 2026-09-24 21:20:31.746801

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0242ed287f4'
down_revision: Union[str, None] = '5b8d86afa4f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column("movies", sa.Column("external_rating", sa.Numeric(3, 1), nullable=True))
    op.add_column("movies", sa.Column("external_id", sa.String(), nullable=True))
    op.add_column("movies", sa.Column("external_rating_fetched_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_movies_external_id", "movies", ["external_id"])


def downgrade():
    op.drop_index("ix_movies_external_id", table_name="movies")
    op.drop_column("movies", "external_rating_fetched_at")
    op.drop_column("movies", "external_id")
    op.drop_column("movies", "external_rating")