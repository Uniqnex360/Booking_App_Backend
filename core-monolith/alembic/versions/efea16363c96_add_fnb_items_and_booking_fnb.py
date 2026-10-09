"""add fnb_items and booking_fnb

Revision ID: efea16363c96
Revises: <keep>
Create Date: 2026-09-30 14:03:49.100094

"""
from typing import Sequence, Union
from sqlalchemy.dialects import postgresql

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'efea16363c96'
down_revision: Union[str, None] = '<keep>'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade():
    op.create_table(
        "fnb_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "venue_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("venues.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("price_paise", sa.Integer(), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("is_veg", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("price_paise >= 0", name="ck_fnb_items_price_paise"),
        sa.CheckConstraint(
            "category IN ('Popcorn','Beverages','Snacks','Combos','Desserts')",
            name="ck_fnb_items_category",
        ),
    )
    op.create_index("ix_fnb_items_venue_id", "fnb_items", ["venue_id"])
    op.create_index(
        "ix_fnb_items_venue_active", "fnb_items", ["venue_id", "is_active"]
    )

    op.create_table(
        "booking_fnb",
        sa.Column(
            "booking_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bookings.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fnb_items.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_paise", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "quantity >= 1 AND quantity <= 10", name="ck_booking_fnb_quantity"
        ),
        sa.CheckConstraint(
            "unit_price_paise >= 0", name="ck_booking_fnb_unit_price_paise"
        ),
    )


def downgrade():
    op.drop_table("booking_fnb")
    op.drop_index("ix_fnb_items_venue_active", table_name="fnb_items")
    op.drop_index("ix_fnb_items_venue_id", table_name="fnb_items")
    op.drop_table("fnb_items")