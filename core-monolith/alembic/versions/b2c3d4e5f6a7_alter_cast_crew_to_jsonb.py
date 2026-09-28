"""alter cast crew to jsonb

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-28 11:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE movies ALTER COLUMN cast_json TYPE JSONB USING cast_json::jsonb")
    op.execute("ALTER TABLE movies ALTER COLUMN crew_json TYPE JSONB USING crew_json::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE movies ALTER COLUMN cast_json TYPE JSON USING cast_json::json")
    op.execute("ALTER TABLE movies ALTER COLUMN crew_json TYPE JSON USING crew_json::json")
