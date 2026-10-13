"""create user_notifications and user_device_tokens tables

Revision ID: d4e5f6a7b8c9
Revises: c2d3e4f5a6b7
Create Date: 2026-10-13 10:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c2d3e4f5a6b7'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_notifications (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            description TEXT NOT NULL,
            type VARCHAR(32) NOT NULL DEFAULT 'booking',
            link VARCHAR(512),
            is_read BOOLEAN NOT NULL DEFAULT false,
            reference_key VARCHAR(128),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_notifications_user_id ON user_notifications(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_notifications_reference_key ON user_notifications(reference_key)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_device_tokens (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            fcm_token VARCHAR(512) NOT NULL UNIQUE,
            platform VARCHAR(32) NOT NULL DEFAULT 'web',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_device_tokens_user_id ON user_device_tokens(user_id)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_user_device_tokens_user_id")
    op.execute("DROP TABLE IF EXISTS user_device_tokens")
    op.execute("DROP INDEX IF EXISTS ix_user_notifications_reference_key")
    op.execute("DROP INDEX IF EXISTS ix_user_notifications_user_id")
    op.execute("DROP TABLE IF EXISTS user_notifications")

