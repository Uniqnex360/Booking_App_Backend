"""0002_movie_module — movie, venue, screen, showtime, and seat_states.

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-01 00:00:00.000000
"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision = "d8941e52706c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- venues ----
    op.create_table(
        "venues",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("city", sa.String(), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column(
            "timezone",
            sa.String(),
            nullable=False,
            server_default=sa.text("'Asia/Kolkata'"),
        ),
        sa.Column("partner_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_venues_city", "venues", ["city"])
    op.create_index("ix_venues_partner_id", "venues", ["partner_id"])

    # ---- screens ----
    op.create_table(
        "screens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "total_seats",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ---- screen_rows ----
    op.create_table(
        "screen_rows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("screen_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("section", sa.String(), nullable=True),
        sa.Column("seat_count", sa.Integer(), nullable=False),
        sa.Column("price_paise", sa.Integer(), nullable=False),
        sa.CheckConstraint("seat_count > 0", name="ck_screen_row_seat_count"),
        sa.CheckConstraint("price_paise >= 0", name="ck_screen_row_price_cents"),
        sa.ForeignKeyConstraint(["screen_id"], ["screens.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("screen_id", "label", name="uq_screen_row_label"),
    )

    # ---- seats ----
    op.create_table(
        "seats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("row_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column(
            "x", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("label", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["row_id"], ["screen_rows.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("row_id", "code", name="uq_seat_row_code"),
        sa.UniqueConstraint("row_id", "number", name="uq_seat_row_number"),
    )

    # ---- movies ----
    op.create_table(
        "movies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("original_title", sa.String(), nullable=True),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=False),
        sa.Column("certificate", sa.String(), nullable=False),
        sa.Column("release_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("poster_url", sa.Text(), nullable=True),
        sa.Column("trailer_url", sa.Text(), nullable=True),
        sa.Column("synopsis", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'DRAFT'"),
        ),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_movies_title", "movies", ["title"])
    op.create_index("ix_movies_status", "movies", ["status"])
    op.create_index("ix_movies_partner_id", "movies", ["partner_id"])

    # ---- showtimes ----
    op.create_table(
        "showtimes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("screen_id", sa.Uuid(), nullable=False),
        sa.Column("movie_id", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "language",
            sa.String(),
            nullable=False,
            server_default=sa.text("'Malayalam'"),
        ),
        sa.Column(
            "format",
            sa.String(),
            nullable=False,
            server_default=sa.text("'2D'"),
        ),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'ACTIVE'"),
        ),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"]),
        sa.ForeignKeyConstraint(["screen_id"], ["screens.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_showtimes_starts_at", "showtimes", ["starts_at"])
    op.create_index("ix_showtimes_partner_id", "showtimes", ["partner_id"])

    # ---- seat_states ----
    op.create_table(
        "seat_states",
        sa.Column("showtime_id", sa.Uuid(), nullable=False),
        sa.Column("seat_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=True),
        sa.Column("blocked_reason", sa.String(), nullable=True),
        sa.Column(
            "booked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["seat_id"], ["seats.id"]),
        sa.ForeignKeyConstraint(["showtime_id"], ["showtimes.id"]),
        sa.PrimaryKeyConstraint("showtime_id", "seat_id"),
    )
    op.create_index(
        "ux_showtime_booked_seat",
        "seat_states",
        ["showtime_id", "seat_id"],
        unique=True,
        postgresql_where=sa.text("status = 'BOOKED'"),
        sqlite_where=sa.text("status = 'BOOKED'"),
    )

    # ---- movie_sold_counts ----
    op.create_table(
        "movie_sold_counts",
        sa.Column("showtime_id", sa.Uuid(), nullable=False),
        sa.Column("row_id", sa.Uuid(), nullable=False),
        sa.Column(
            "sold_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.ForeignKeyConstraint(["row_id"], ["screen_rows.id"]),
        sa.ForeignKeyConstraint(["showtime_id"], ["showtimes.id"]),
        sa.PrimaryKeyConstraint("showtime_id", "row_id"),
    )


def downgrade() -> None:
    op.drop_table("movie_sold_counts")
    op.drop_index("ux_showtime_booked_seat", table_name="seat_states")
    op.drop_table("seat_states")
    op.drop_index("ix_showtimes_partner_id", table_name="showtimes")
    op.drop_index("ix_showtimes_starts_at", table_name="showtimes")
    op.drop_table("showtimes")
    op.drop_index("ix_movies_partner_id", table_name="movies")
    op.drop_index("ix_movies_status", table_name="movies")
    op.drop_index("ix_movies_title", table_name="movies")
    op.drop_table("movies")
    op.drop_table("seats")
    op.drop_table("screen_rows")
    op.drop_table("screens")
    op.drop_index("ix_venues_partner_id", table_name="venues")
    op.drop_index("ix_venues_city", table_name="venues")
    op.drop_table("venues")