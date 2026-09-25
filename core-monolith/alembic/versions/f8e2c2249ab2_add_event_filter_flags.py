"""add event filter flags

Revision ID: f8e2c2249ab2
Revises: d0242ed287f4
Create Date: 2026-09-25 20:17:01.072524

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8e2c2249ab2'
down_revision: Union[str, None] = 'd0242ed287f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade():
    for col in [
        "is_outdoor",
        "is_fast_filling",
        "is_must_attend",
        "is_unmissable",
        "is_kids_allowed",
        "is_masterclass",
        "is_new_year_party",
    ]:
        op.add_column(
            "events",
            sa.Column(col, sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )


def downgrade():
    for col in [
        "is_outdoor",
        "is_fast_filling",
        "is_must_attend",
        "is_unmissable",
        "is_kids_allowed",
        "is_masterclass",
        "is_new_year_party",
    ]:
        op.drop_column("events", col)