from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base
from app.shared.timeutil import TZDateTime, utcnow


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
    hashtags = Column(JSONB, nullable=False, server_default=sa.text("'[]'::jsonb"))
    created_at = Column(TZDateTime, nullable=False, default=utcnow)
    updated_at = Column(TZDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "movie_id", name="ux_movie_reviews_user_movie"),
    )