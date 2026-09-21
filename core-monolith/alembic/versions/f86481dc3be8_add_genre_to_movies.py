"""add genre to movies

Revision ID: f86481dc3be8
Revises: d2a6e735ce95
Create Date: 2026-09-18 ...

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f86481dc3be8'
down_revision: Union[str, None] = 'd2a6e735ce95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent — the previous migration (d2a6e735ce95) already added this
    # column on databases that were migrated cleanly. On any fresh DB, both
    # ran in sequence; this one is a no-op to avoid a duplicate-column error.
    op.execute("ALTER TABLE movies ADD COLUMN IF NOT EXISTS genre VARCHAR(120)")


def downgrade() -> None:
    pass