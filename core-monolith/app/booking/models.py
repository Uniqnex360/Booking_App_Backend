"""SQLAlchemy models for Bookings."""

from __future__ import annotations

import uuid
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.core.database import Base
from app.shared.timeutil import utcnow


class BookingModel(Base):
    __tablename__ = "bookings"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    booking_type = Column(Text, nullable=False, server_default="EVENT")
    event_id = Column(PG_UUID(as_uuid=True), nullable=True, index=True)
    tier_id = Column(PG_UUID(as_uuid=True), nullable=True, index=True)
    showtime_id = Column(PG_UUID(as_uuid=True), ForeignKey("showtimes.id"), nullable=True, index=True)
    provider_id = Column(PG_UUID(as_uuid=True), ForeignKey("provider_registry.id"), nullable=True, index=True)
    provider_hold_id = Column(String(255), nullable=True)
    provider_booking_id = Column(String(255), nullable=True)
    held_until = Column(DateTime(timezone=True), nullable=True)
    currency = Column(String(10), nullable=False, default="INR", server_default="INR")

    ref_code = Column(String(64), nullable=True, unique=True, index=True)
    quantity = Column(Integer, nullable=True)
    unit_price_paise = Column(Integer, nullable=True)
    total_paise = Column(Integer, CheckConstraint("total_paise >= 0"), nullable=False)
    status = Column(Text, nullable=False, default="CONFIRMED")
    idempotency_key = Column(String(255), index=True, nullable=True)
    barcode = Column(String(255), nullable=True)
    seat_refs_json = Column(Text, nullable=True)
    seat_codes_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="ux_user_idempotency"),
    )


class TicketSoldCountModel(Base):
    __tablename__ = "ticket_sold_counts"

    tier_id = Column(PG_UUID(as_uuid=True), primary_key=True)
    sold = Column(Integer, CheckConstraint("sold >= 0"), nullable=False, default=0)