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
    conn = op.get_bind()
    dups = conn.execute(sa.text(
        "SELECT payment_id, COUNT(*) as cnt FROM payments WHERE payment_id IS NOT NULL GROUP BY payment_id HAVING COUNT(*) > 1"
    )).fetchall()
    if dups:
        dup_list = ", ".join([f"{r[0]} ({r[1]} occurrences)" for r in dups])
        raise RuntimeError(
            f"Cannot apply unique constraint uq_payments_payment_id: duplicate payment_ids exist in payments table: {dup_list}"
        )

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

