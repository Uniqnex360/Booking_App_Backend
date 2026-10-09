"""add screen experience fields

Revision ID: 72bf0f8d9225
Revises: 700dfebe6799
Create Date: 2026-09-30 14:04:44.289862

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '72bf0f8d9225'
down_revision: Union[str, None] = '700dfebe6799'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade():
    op.add_column(
        "screens",
        sa.Column("first_row_distance_m", sa.Numeric(4, 1), nullable=True),
    )
    op.add_column(
        "screens",
        sa.Column("row_pitch_m", sa.Numeric(3, 2), nullable=True),
    )
    op.add_column(
        "screens", sa.Column("panorama_url", sa.Text(), nullable=True)
    )
    op.create_check_constraint(
        "ck_screens_first_row_distance",
        "screens",
        "first_row_distance_m IS NULL OR first_row_distance_m > 0",
    )
    op.create_check_constraint(
        "ck_screens_row_pitch",
        "screens",
        "row_pitch_m IS NULL OR row_pitch_m > 0",
    )


def downgrade():
    op.drop_constraint("ck_screens_row_pitch", "screens", type_="check")
    op.drop_constraint("ck_screens_first_row_distance", "screens", type_="check")
    op.drop_column("screens", "panorama_url")
    op.drop_column("screens", "row_pitch_m")
    op.drop_column("screens", "first_row_distance_m")