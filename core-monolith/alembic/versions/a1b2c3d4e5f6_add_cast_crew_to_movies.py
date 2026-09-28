"""add cast crew to movies

Revision ID: a1b2c3d4e5f6
Revises: 1acd8982e862
Create Date: 2026-09-28 10:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '1acd8982e862'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE movies ADD COLUMN IF NOT EXISTS cast_json JSON")
    op.execute("ALTER TABLE movies ADD COLUMN IF NOT EXISTS crew_json JSON")


def downgrade() -> None:
    op.execute("ALTER TABLE movies DROP COLUMN IF EXISTS cast_json")
    op.execute("ALTER TABLE movies DROP COLUMN IF EXISTS crew_json")
