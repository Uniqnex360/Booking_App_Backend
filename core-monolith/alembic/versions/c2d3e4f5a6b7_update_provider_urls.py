"""update provider urls for cinepolis, shenoys, and vanitha

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-10-12 13:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c2d3e4f5a6b7'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE provider_registry "
        "SET base_url = 'https://cinepolis-kochi-app-1.onrender.com' "
        "WHERE base_url = 'https://kochi-app-1.onrender.com' OR name = 'Cinepolis Centre Square'"
    ))
    conn.execute(sa.text(
        "UPDATE provider_registry "
        "SET base_url = 'https://shenoys-w13i.onrender.com' "
        "WHERE base_url = 'https://shenoys.onrender.com' OR name = 'Shenoys'"
    ))
    conn.execute(sa.text(
        "UPDATE provider_registry "
        "SET base_url = 'https://vanitha-kochi-app-2-u5ww.onrender.com' "
        "WHERE base_url = 'https://vanitha-kochi-app-2.onrender.com' OR name = 'Vanitha Vineetha'"
    ))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE provider_registry "
        "SET base_url = 'https://kochi-app-1.onrender.com' "
        "WHERE base_url = 'https://cinepolis-kochi-app-1.onrender.com' OR name = 'Cinepolis Centre Square'"
    ))
    conn.execute(sa.text(
        "UPDATE provider_registry "
        "SET base_url = 'https://shenoys.onrender.com' "
        "WHERE base_url = 'https://shenoys-w13i.onrender.com' OR name = 'Shenoys'"
    ))
    conn.execute(sa.text(
        "UPDATE provider_registry "
        "SET base_url = 'https://vanitha-kochi-app-2.onrender.com' "
        "WHERE base_url = 'https://vanitha-kochi-app-2-u5ww.onrender.com' OR name = 'Vanitha Vineetha'"
    ))

