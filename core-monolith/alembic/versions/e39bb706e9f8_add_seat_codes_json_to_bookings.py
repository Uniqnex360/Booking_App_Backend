"""add seat_codes_json to bookings

Revision ID: e39bb706e9f8
Revises: 6098bce2d0f5
Create Date: 2026-09-18 14:32:43.538594

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e39bb706e9f8'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("seat_codes_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bookings", "seat_codes_json")   