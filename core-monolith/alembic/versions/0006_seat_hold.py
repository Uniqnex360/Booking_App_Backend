"""seat_states LOCKED status and partial index update

Revision ID: 0006
Revises: 0004
Create Date: 2026-09-16 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add held_until to seat_states for LOCKED rows
    op.add_column(
        "seat_states",
        sa.Column("held_until", sa.DateTime(timezone=True), nullable=True),
    )

    # Drop old partial index (BOOKED only)
    op.drop_index("ux_showtime_booked_seat", table_name="seat_states")

    # Recreate as partial index covering both BOOKED and LOCKED
    op.create_index(
        "ux_showtime_active_seat",
        "seat_states",
        ["showtime_id", "seat_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('BOOKED', 'LOCKED')"),
        sqlite_where=sa.text("status IN ('BOOKED', 'LOCKED')"),
    )


def downgrade() -> None:
    op.drop_index("ux_showtime_active_seat", table_name="seat_states")
    op.create_index(
        "ux_showtime_booked_seat",
        "seat_states",
        ["showtime_id", "seat_id"],
        unique=True,
        postgresql_where=sa.text("status = 'BOOKED'"),
        sqlite_where=sa.text("status = 'BOOKED'"),
    )
    op.drop_column("seat_states", "held_until")
