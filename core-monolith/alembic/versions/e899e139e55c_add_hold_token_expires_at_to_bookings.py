"""add hold_token_expires_at to bookings

Revision ID: e899e139e55c
Revises: 72bf0f8d9225
Create Date: 2026-09-30 17:51:02.311439

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e899e139e55c'
down_revision: Union[str, None] = '72bf0f8d9225'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade():
    op.add_column(
        "bookings",
        sa.Column("hold_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("bookings", "hold_token_expires_at")