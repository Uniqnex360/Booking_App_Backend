"""booking — bookings and ticket_sold_counts"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. create bookings table
    op.create_table(
        "bookings",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", PG_UUID(as_uuid=True), sa.ForeignKey("events.id"), nullable=True),
        sa.Column("tier_id", PG_UUID(as_uuid=True), sa.ForeignKey("event_ticket_categories.id"), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("unit_price_cents", sa.Integer(), nullable=True),
        sa.Column("total_cents", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="CONFIRMED"),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("user_id", "idempotency_key", name="ux_user_idempotency"),
    )
    op.create_index("ix_bookings_user_id", "bookings", ["user_id"])
    op.create_index("ix_bookings_event_id", "bookings", ["event_id"])
    op.create_index("ix_bookings_tier_id", "bookings", ["tier_id"])

    # 2. create ticket_sold_counts table
    op.create_table(
        "ticket_sold_counts",
        sa.Column("tier_id", PG_UUID(as_uuid=True), sa.ForeignKey("event_ticket_categories.id"), primary_key=True),
        sa.Column("sold", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.CheckConstraint("sold >= 0", name="ck_ticket_sold_counts_sold"),
    )


def downgrade() -> None:
    op.drop_table("ticket_sold_counts")
    op.drop_table("bookings")
