"""add language and tags to events

Revision ID: 1acd8982e862
Revises: f8e2c2249ab2
Create Date: 2026-09-25 20:27:32.380411

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1acd8982e862'
down_revision: Union[str, None] = 'f8e2c2249ab2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
def upgrade():
    op.add_column("events", sa.Column("language", sa.String(50), nullable=True))
    op.add_column(
        "events",
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String(50)),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade():
    op.drop_column("events", "tags")
    op.drop_column("events", "language")