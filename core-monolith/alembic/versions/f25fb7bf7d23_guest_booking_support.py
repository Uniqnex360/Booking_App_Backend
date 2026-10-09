"""guest booking support

Revision ID: f25fb7bf7d23
Revises: 3516f7e6b9cf
Create Date: 2026-09-24 10:33:47.384476

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f25fb7bf7d23'
down_revision: Union[str, None] = '3516f7e6b9cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade():
    op.alter_column(
        "bookings",
        "user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.add_column("bookings", sa.Column("contact_email", sa.String(255), nullable=True))
    op.add_column("bookings", sa.Column("contact_phone", sa.String(20), nullable=True))


def downgrade():
    op.drop_column("bookings", "contact_phone")
    op.drop_column("bookings", "contact_email")
    op.alter_column(
        "bookings",
        "user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )