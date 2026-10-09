"""add adapter to provider_registry

Revision ID: 3516f7e6b9cf
Revises: f86481dc3be8
Create Date: 2026-09-21 10:52:00.334053

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3516f7e6b9cf'
down_revision: Union[str, None] = 'f86481dc3be8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        "provider_registry",
        sa.Column(
            "adapter",
            sa.String(20),
            nullable=False,
            server_default="pvr",
        ),
    )


def downgrade() -> None:
    op.drop_column("provider_registry", "adapter")