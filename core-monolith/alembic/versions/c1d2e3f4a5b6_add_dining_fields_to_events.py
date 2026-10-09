"""add dining fields to events

Revision ID: c1d2e3f4a5b6
Revises: e899e139e55c
Create Date: 2026-10-07 10:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "e899e139e55c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "events",
        sa.Column("cuisine", sa.JSON(), nullable=True, server_default="[]"),
    )
    op.add_column(
        "events",
        sa.Column("price_range", sa.Integer(), nullable=True),
    )
    op.add_column(
        "events",
        sa.Column("what_included", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("events", "what_included")
    op.drop_column("events", "price_range")
    op.drop_column("events", "cuisine")

