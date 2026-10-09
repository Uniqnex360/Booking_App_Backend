"""provider and booking extensions

Revision ID: 0004
Revises: fd0cdee50289
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, None] = "fd0cdee50289"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. create provider_registry table
    op.create_table(
        "provider_registry",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("base_url", sa.String(), nullable=False),
        sa.Column("auth_token_ref", sa.String(), nullable=True),
        sa.Column("hold_ttl_seconds", sa.Integer(), nullable=False, server_default=sa.text("600")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("partner_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # 2. add columns to showtimes
    op.add_column("showtimes", sa.Column("provider_id", sa.Uuid(), nullable=True))
    op.add_column("showtimes", sa.Column("provider_showtime_ref", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_showtimes_provider",
        "showtimes",
        "provider_registry",
        ["provider_id"],
        ["id"],
    )

    # 3. add columns to bookings
    op.add_column("bookings", sa.Column("provider_id", sa.Uuid(), nullable=True))
    op.add_column("bookings", sa.Column("provider_hold_id", sa.String(), nullable=True))
    op.add_column("bookings", sa.Column("provider_booking_id", sa.String(), nullable=True))
    op.add_column("bookings", sa.Column("held_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bookings", sa.Column("currency", sa.String(), nullable=False, server_default=sa.text("'INR'")))
    
    op.create_foreign_key(
        "fk_bookings_provider",
        "bookings",
        "provider_registry",
        ["provider_id"],
        ["id"],
    )

    # Add foreign key constraint to showtimes.id in bookings if not already present
    op.create_foreign_key(
        "fk_bookings_showtimes",
        "bookings",
        "showtimes",
        ["showtime_id"],
        ["id"],
    )

    # Add CHECK constraint for status
    op.create_check_constraint(
        "ck_bookings_status",
        "bookings",
        "status IN ('HELD', 'CONFIRMED', 'CANCELLED', 'EXPIRED', 'PENDING_CONFIRMATION')",
    )

    # Add CHECK constraint that exactly one of tier_id or showtime_id is present
    # We use num_nonnulls/num_nulls logic or simple IS NULL checks for portability:
    op.create_check_constraint(
        "ck_bookings_tier_or_showtime",
        "bookings",
        "((tier_id IS NOT NULL AND showtime_id IS NULL) OR (tier_id IS NULL AND showtime_id IS NOT NULL))",
    )


def downgrade() -> None:
    op.drop_constraint("ck_bookings_tier_or_showtime", "bookings")
    op.drop_constraint("ck_bookings_status", "bookings")
    op.drop_constraint("fk_bookings_showtimes", "bookings")
    op.drop_constraint("fk_bookings_provider", "bookings")
    op.drop_column("bookings", "currency")
    op.drop_column("bookings", "held_until")
    op.drop_column("bookings", "provider_booking_id")
    op.drop_column("bookings", "provider_hold_id")
    op.drop_column("bookings", "provider_id")
    
    op.drop_constraint("fk_showtimes_provider", "showtimes")
    op.drop_column("showtimes", "provider_showtime_ref")
    op.drop_column("showtimes", "provider_id")
    
    op.drop_table("provider_registry")