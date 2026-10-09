"""add barcode and seat_refs_json to bookings

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("barcode", sa.String(255), nullable=True))
    op.add_column("bookings", sa.Column("seat_refs_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("bookings", "seat_refs_json")
    op.drop_column("bookings", "barcode")
