"""add event artists gallery layout promoter faqs terms

Revision ID: e4f5a6b7c8d9
Revises: b2c3d4e5f6a7
Create Date: 2026-09-29 13:13:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS artists JSONB DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS gallery_images JSONB DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS layout_image_url VARCHAR(500)")
    op.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS offline_promoter JSONB")
    op.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS faqs JSONB DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS terms_and_conditions TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE events DROP COLUMN IF EXISTS terms_and_conditions")
    op.execute("ALTER TABLE events DROP COLUMN IF EXISTS faqs")
    op.execute("ALTER TABLE events DROP COLUMN IF EXISTS offline_promoter")
    op.execute("ALTER TABLE events DROP COLUMN IF EXISTS layout_image_url")
    op.execute("ALTER TABLE events DROP COLUMN IF EXISTS gallery_images")
    op.execute("ALTER TABLE events DROP COLUMN IF EXISTS artists")
