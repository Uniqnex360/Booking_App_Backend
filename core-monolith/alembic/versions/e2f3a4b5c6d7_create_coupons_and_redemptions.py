"""create coupons and redemptions

Revision ID: e2f3a4b5c6d7
Revises: c1d2e3f4a5b6
Create Date: 2026-10-07 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        "coupons",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("partner_id", UUID(as_uuid=True), sa.ForeignKey("partners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_id", UUID(as_uuid=True), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=True),
        sa.Column("discount_type", sa.Text(), nullable=False),
        sa.Column("discount_value", sa.Integer(), nullable=False),
        sa.Column("min_order_paise", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_discount_paise", sa.Integer(), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_usage_limit", sa.Integer(), nullable=True),
        sa.Column("per_user_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_coupons_code"),
        sa.CheckConstraint("discount_type IN ('PERCENT', 'FLAT')", name="ck_discount_type"),
        sa.CheckConstraint("discount_value > 0", name="ck_discount_value_positive"),
    )
    op.create_index("ix_coupons_partner", "coupons", ["partner_id"])
    op.create_index("ix_coupons_event", "coupons", ["event_id"])
    op.create_index("ix_coupons_active", "coupons", ["is_active"])

    op.create_table(
        "coupon_redemptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("coupon_id", UUID(as_uuid=True), sa.ForeignKey("coupons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("booking_id", UUID(as_uuid=True), sa.ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("discount_paise", sa.Integer(), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("coupon_id", "booking_id", name="uq_coupon_booking"),
    )
    op.create_index("ix_redemptions_user", "coupon_redemptions", ["coupon_id", "user_id"])
    op.create_index("ix_redemptions_coupon", "coupon_redemptions", ["coupon_id"])


def downgrade():
    op.drop_table("coupon_redemptions")
    op.drop_table("coupons")

