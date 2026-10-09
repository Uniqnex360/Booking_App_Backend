"""add used_phone_email_verifications table

Revision ID: a2b3c4d5e6f7
Revises: f3a4b5c6d7e8
Create Date: 2026-10-09 14:48:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2b3c4d5e6f7'
down_revision = 'f3a4b5c6d7e8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "used_phone_email_verifications",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("url_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", sa.Uuid, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_used_phone_email_verifications_url_hash",
        "used_phone_email_verifications",
        ["url_hash"],
        unique=True,
    )


def downgrade():
    op.drop_index(
        "ix_used_phone_email_verifications_url_hash",
        table_name="used_phone_email_verifications",
    )
    op.drop_table("used_phone_email_verifications")

