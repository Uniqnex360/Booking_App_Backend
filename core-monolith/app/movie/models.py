from __future__ import annotations
import enum
import uuid
from sqlalchemy.dialects.postgresql import JSONB
import sqlalchemy as sa
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Numeric,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.shared.timeutil import TZDateTime, utcnow
from app.movie.interfaces import MovieStatus  
class ShowtimeStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"
class SeatStateStatus(str, enum.Enum):
    BOOKED = "BOOKED"
    BLOCKED = "BLOCKED"
class ShowtimeFormat(str, enum.Enum):
    FORMAT_2D = "2D"
    FORMAT_3D = "3D"
    IMAX = "IMAX"
    DOLBY = "DOLBY"
class Venue(Base):
    __tablename__ = "venues"
    id = Column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    city = Column(String, nullable=False, index=True)
    address = Column(Text, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    timezone = Column(
        String, nullable=False, server_default=sa.text("'Asia/Kolkata'")
    )
    partner_id = Column(sa.Uuid, nullable=True, index=True)
    created_at = Column(TZDateTime, nullable=False, default=utcnow)
    screens = relationship("Screen", back_populates="venue", cascade="all, delete-orphan")
class Screen(Base):
    __tablename__ = "screens"
    id = Column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    venue_id = Column(sa.Uuid, ForeignKey("venues.id"), nullable=False)
    name = Column(String, nullable=False)
    total_seats = Column(Integer, nullable=False, server_default=sa.text("0"))
    venue = relationship("Venue", back_populates="screens")
    rows = relationship("ScreenRow", back_populates="screen", cascade="all, delete-orphan")
    showtimes = relationship("Showtime", back_populates="screen", cascade="all, delete-orphan")
class ScreenRow(Base):
    __tablename__ = "screen_rows"
    id = Column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    screen_id = Column(sa.Uuid, ForeignKey("screens.id"), nullable=False)
    label = Column(String, nullable=False)
    section = Column(String, nullable=True)  
    seat_count = Column(Integer, nullable=False)
    price_paise = Column(Integer, nullable=False)
    screen = relationship("Screen", back_populates="rows")
    seats = relationship("Seat", back_populates="row", cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint("screen_id", "label", name="uq_screen_row_label"),
        CheckConstraint("seat_count > 0", name="ck_screen_row_seat_count"),
        CheckConstraint("price_paise >= 0", name="ck_screen_row_price_paise"),
    )
class Seat(Base):
    __tablename__ = "seats"
    id = Column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    row_id = Column(sa.Uuid, ForeignKey("screen_rows.id"), nullable=False)
    number = Column(Integer, nullable=False)
    code = Column(String, nullable=False)
    x = Column(Integer, nullable=False, server_default=sa.text("0"))
    label = Column(String, nullable=True)
    row = relationship("ScreenRow", back_populates="seats")
    __table_args__ = (
        UniqueConstraint("row_id", "number", name="uq_seat_row_number"),
        UniqueConstraint("row_id", "code", name="uq_seat_row_code"),
    )
class Movie(Base):
    __tablename__ = "movies"
    id = Column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False, index=True)
    original_title = Column(String, nullable=True)
    language = Column(String, nullable=False)
    duration_min = Column(Integer, nullable=False)
    certificate = Column(String, nullable=False)
    release_date = Column(DateTime(timezone=True), nullable=True)
    poster_url = Column(Text, nullable=True)
    banner_url = Column(Text, nullable=True)
    trailer_url = Column(Text, nullable=True)
    synopsis = Column(Text, nullable=True)
    genre = Column(String(120), nullable=True)    
    status = Column(
        String,
        nullable=False,
        server_default=sa.text("'DRAFT'"),
        index=True,
    )
    rating = Column(Numeric(3, 1), nullable=True)
    rating_count = Column(Integer, nullable=False, server_default="0")
    partner_id = Column(sa.Uuid, nullable=False, index=True)
    created_at = Column(TZDateTime, nullable=False, default=utcnow)
    updated_at = Column(
        TZDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
    showtimes = relationship("Showtime", back_populates="movie", cascade="all, delete-orphan")
class Showtime(Base):
    __tablename__ = "showtimes"
    id = Column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    screen_id = Column(sa.Uuid, ForeignKey("screens.id"), nullable=False)
    movie_id = Column(sa.Uuid, ForeignKey("movies.id"), nullable=False)
    starts_at = Column(DateTime(timezone=True), nullable=False, index=True)
    language = Column(
        String, nullable=False, server_default=sa.text("'Malayalam'")
    )
    format = Column(
        String, nullable=False, server_default=sa.text("'2D'")
    )
    status = Column(
        String, nullable=False, server_default=sa.text("'ACTIVE'")
    )
    partner_id = Column(sa.Uuid, nullable=False, index=True)
    provider_id = Column(sa.Uuid, ForeignKey("provider_registry.id"), nullable=True, index=True)
    provider_showtime_ref = Column(String, nullable=True)
    screen = relationship("Screen", back_populates="showtimes")
    movie = relationship("Movie", back_populates="showtimes")
class SeatState(Base):
    __tablename__ = "seat_states"
    showtime_id = Column(
        sa.Uuid, ForeignKey("showtimes.id"), primary_key=True
    )
    seat_id = Column(
        sa.Uuid, ForeignKey("seats.id"), primary_key=True
    )
    status = Column(String, nullable=False)  
    booking_id = Column(sa.Uuid, nullable=True)
    blocked_reason = Column(String, nullable=True)
    held_until = Column(TZDateTime, nullable=True)
    booked_at = Column(TZDateTime, nullable=False, default=utcnow)
    __table_args__ = (
        Index(
            "ux_showtime_active_seat",
            "showtime_id",
            "seat_id",
            unique=True,
            postgresql_where=text("status IN ('BOOKED', 'LOCKED')"),
            sqlite_where=text("status IN ('BOOKED', 'LOCKED')"),
        ),
    )
class MovieSoldCount(Base):
    __tablename__ = "movie_sold_counts"
    showtime_id = Column(
        sa.Uuid, ForeignKey("showtimes.id"), primary_key=True
    )
    row_id = Column(
        sa.Uuid, ForeignKey("screen_rows.id"), primary_key=True
    )
    sold_count = Column(Integer, nullable=False, server_default=sa.text("0"))
class MovieReview(Base):
    __tablename__ = "movie_reviews"
    id = Column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(
        sa.Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    movie_id = Column(
        sa.Uuid,
        ForeignKey("movies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rating = Column(Numeric(3, 1), nullable=False)
    hashtags = Column(JSONB, nullable=False, server_default="[]")
    created_at = Column(TZDateTime, nullable=False, default=utcnow)
    updated_at = Column(TZDateTime, nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        UniqueConstraint("user_id", "movie_id", name="ux_movie_reviews_user_movie"),
    )