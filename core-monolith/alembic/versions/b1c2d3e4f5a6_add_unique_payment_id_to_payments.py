"""add unique constraint on payment_id in payments

Revision ID: b1c2d3e4f5a6
Revises: a2b3c4d5e6f7
Create Date: 2026-10-09 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = 'a2b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_payments_payment_id",
        "payments",
        ["payment_id"],
    )


def downgrade():
    op.drop_constraint(
        "uq_payments_payment_id",
        "payments",
        type_="unique",
    )

