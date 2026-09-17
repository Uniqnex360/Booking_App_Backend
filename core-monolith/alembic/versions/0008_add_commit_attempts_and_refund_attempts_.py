"""add commit_attempts and refund_attempts to payments

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-17 15:38:19.466572

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('payments', sa.Column('commit_attempts', sa.Integer(), server_default='0', nullable=False))
    op.add_column('payments', sa.Column('refund_attempts', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('payments', 'refund_attempts')
    op.drop_column('payments', 'commit_attempts')
