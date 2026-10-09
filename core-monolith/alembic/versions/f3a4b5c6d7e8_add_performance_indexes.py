"""add performance indexes for showtimes, screens, and events

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-10-08 19:51:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3a4b5c6d7e8'
down_revision = 'e2f3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_showtimes_movie_id', 'showtimes', ['movie_id'], unique=False, if_not_exists=True)
    op.create_index('ix_showtimes_screen_id', 'showtimes', ['screen_id'], unique=False, if_not_exists=True)
    op.create_index('ix_screens_venue_id', 'screens', ['venue_id'], unique=False, if_not_exists=True)
    op.create_index('ix_events_status_city', 'events', ['status', 'city'], unique=False, if_not_exists=True)
    op.create_index('ix_events_starts_at', 'events', ['starts_at'], unique=False, if_not_exists=True)


def downgrade():
    op.drop_index('ix_events_starts_at', table_name='events', if_exists=True)
    op.drop_index('ix_events_status_city', table_name='events', if_exists=True)
    op.drop_index('ix_screens_venue_id', table_name='screens', if_exists=True)
    op.drop_index('ix_showtimes_screen_id', table_name='showtimes', if_exists=True)
    op.drop_index('ix_showtimes_movie_id', table_name='showtimes', if_exists=True)

