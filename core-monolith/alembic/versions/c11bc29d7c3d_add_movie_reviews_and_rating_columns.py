"""add movie_reviews and rating columns

Revision ID: c11bc29d7c3d
Revises: 071de1a657a2
Create Date: 2026-09-24 15:06:48.289458

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c11bc29d7c3d'
down_revision: Union[str, None] = '071de1a657a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade():
    op.add_column("movies", sa.Column("rating", sa.Numeric(3, 1), nullable=True))
    op.add_column(
        "movies",
        sa.Column("rating_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "movie_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "movie_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("movies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.Numeric(3, 1), nullable=False),
        sa.Column("hashtags", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "movie_id", name="ux_movie_reviews_user_movie"),
    )
    op.create_index("ix_movie_reviews_movie_id", "movie_reviews", ["movie_id"])


def downgrade():
    op.drop_index("ix_movie_reviews_movie_id", table_name="movie_reviews")
    op.drop_table("movie_reviews")
    op.drop_column("movies", "rating_count")
    op.drop_column("movies", "rating")