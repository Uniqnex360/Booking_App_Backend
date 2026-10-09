"""add price breakdown and hold token to bookings

Revision ID: 700dfebe6799
Revises: efea16363c96
Create Date: 2026-09-30 14:04:43.605042

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '700dfebe6799'
down_revision: Union[str, None] = 'efea16363c96'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade():
    op.add_column(
        "bookings", sa.Column("ticket_paise", sa.Integer(), nullable=True)
    )
    op.add_column(
        "bookings",
        sa.Column("fnb_paise", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "bookings",
        sa.Column(
            "convenience_fee_paise",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "bookings",
        sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bookings", sa.Column("hold_token_hash", sa.Text(), nullable=True)
    )
    op.create_index("ix_bookings_hold_token_hash", "bookings", ["hold_token_hash"])

    # Backfill ticket_paise from total_paise for existing movie bookings
    op.execute("""
        UPDATE bookings
        SET ticket_paise = total_paise
        WHERE ticket_paise IS NULL
          AND showtime_id IS NOT NULL
          AND status != 'CANCELLED'
    """)


def downgrade():
    op.drop_index("ix_bookings_hold_token_hash", table_name="bookings")
    op.drop_column("bookings", "hold_token_hash")
    op.drop_column("bookings", "terms_accepted_at")
    op.drop_column("bookings", "convenience_fee_paise")
    op.drop_column("bookings", "fnb_paise")
    op.drop_column("bookings", "ticket_paise")