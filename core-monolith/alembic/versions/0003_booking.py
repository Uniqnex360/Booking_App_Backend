"""booking — bookings and ticket_sold_counts"""

from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.alter_column('bookings', 'unit_price_cents', new_column_name='unit_price_paise')
    op.alter_column('bookings', 'total_paise', new_column_name='total_paise')
    
    # Drop old constraints and create new ones
    op.drop_constraint('ck_bookings_unit_price_cents', 'bookings', type_='check') # Adjust name if different
    op.create_check_constraint('ck_bookings_unit_price_paise', 'bookings', 'unit_price_paise >= 0')
    
    op.drop_constraint('ck_bookings_total_paise', 'bookings', type_='check')
    op.create_check_constraint('ck_bookings_total_paise', 'bookings', 'total_paise >= 0')

def downgrade() -> None:
    op.alter_column('bookings', 'unit_price_paise', new_column_name='unit_price_cents')
    op.alter_column('bookings', 'total_paise', new_column_name='total_paise')
    
    op.drop_constraint('ck_bookings_unit_price_paise', 'bookings', type_='check')
    op.create_check_constraint('ck_bookings_unit_price_cents', 'bookings', 'unit_price_cents > 0')
    
    op.drop_constraint('ck_bookings_total_paise', 'bookings', type_='check')
    op.create_check_constraint('ck_bookings_total_paise', 'bookings', 'total_paise >= 0')