"""create movie_reviews table if missing"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '<keep>'
down_revision: Union[str, None] = '3b6c676422f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Idempotent — only create if missing (Neon's DB lost it, but rating columns exist).
    op.execute("""
        CREATE TABLE IF NOT EXISTS movie_reviews (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            movie_id UUID NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
            rating NUMERIC(3,1) NOT NULL,
            hashtags JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ux_movie_reviews_user_movie UNIQUE (user_id, movie_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_movie_reviews_movie_id ON movie_reviews(movie_id)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_movie_reviews_movie_id")
    op.execute("DROP TABLE IF EXISTS movie_reviews")